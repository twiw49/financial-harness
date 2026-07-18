#!/usr/bin/env python3
"""backtest_scaffold.py — 로컬 규칙 백테스트 실행기 (financial-harness quant 모드 B).

서버는 백테스트를 실행하지 않는다(PRODUCT 정직고지 ②) — 실행 주체=로컬 하네스. /datasets를
받아 규칙을 검증하고, 하네스가 정직성 게이트·보고서를 표준화한다. 전략 검증 도구이지 알파 보장 아님.

사용법:  python3 scripts/backtest_scaffold.py --run-dir reports/NNN_전략_YYYYMMDD
입력  :  <RUN_DIR>/_workspace/backtest/config.json (스키마=README)
데이터:  <RUN_DIR>/_workspace/00_raw/datasets/*.parquet + prices_bulk_*.json (무가공 저장본)
출력  :  <RUN_DIR>/_workspace/backtest/results.json + timeseries.csv
의존  :  pandas + pyarrow + 표준 라이브러리. 네트워크 0.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FALLBACK_LAG_DAYS = 90   # pit 미매칭 셀의 보수 폴백: period_end + 90일 ≤ t
PPY = {"M": 12, "Q": 4}  # 리밸런스 빈도별 연간 기간 수
DEFAULTS = {"consol": 1, "rebalance": "M", "quantiles": 5, "cost_bps": 30,
            "period_type": "annual", "period": {}, "trials_note": ""}


# ── 입력 로드 ─────────────────────────────────────────────────────────────────
def load_config(run_dir: Path) -> dict:
    cfg = run_dir / "_workspace" / "backtest" / "config.json"
    if not cfg.exists():
        sys.exit(f"config 없음: {cfg}")
    c = json.loads(cfg.read_text())
    for k, v in DEFAULTS.items():
        c.setdefault(k, v)
    return c


def load_datasets(run_dir: Path) -> dict:
    base = run_dir / "_workspace" / "00_raw" / "datasets"
    return {k: (pd.read_parquet(base / f"{k}.parquet") if (base / f"{k}.parquet").exists() else None)
            for k in ("factor_zoo", "pit_universe_snapshot", "survivorship_free_universe")}


def load_prices(run_dir: Path) -> dict:
    """prices_bulk_*.json (여러 파일 가능, 50종목/콜 분할) → {stock_code: adj_close Series}."""
    raw_dir = run_dir / "_workspace" / "00_raw"
    files = glob.glob(str(raw_dir / "prices_bulk*.json")) + \
        glob.glob(str(raw_dir / "**" / "prices_bulk*.json"), recursive=True)
    series: dict[str, pd.Series] = {}
    for f in sorted(set(files)):
        raw = json.loads(Path(f).read_text())
        payload = raw.get("data", raw) if isinstance(raw, dict) else {}   # call_api 봉투 or 응답 본문
        for sc, obj in (payload.get("stocks") or {}).items():
            rows = obj.get("prices") if isinstance(obj, dict) else None
            if not rows:
                continue
            df = pd.DataFrame(rows)
            if "date" not in df or "adj_close" not in df:
                continue
            s = pd.Series(pd.to_numeric(df["adj_close"], errors="coerce").values,
                          index=pd.to_datetime(df["date"], errors="coerce")).dropna()
            if sc in series:
                s = pd.concat([series[sc], s])
            series[sc] = s[~s.index.duplicated(keep="last")].sort_index()
    return series


# ── 리밸런스 달력·유니버스 ─────────────────────────────────────────────────────
def rebalance_dates(prices: dict, freq: str, start, end) -> list:
    """가격 데이터의 월말(M)/분기말(Q) 거래일 → [start, end] 구간."""
    days = pd.DatetimeIndex(sorted({d for s in prices.values() for d in s.index}))
    days = days[(days >= start) & (days <= end)]
    if len(days) == 0:
        return []
    key = days.to_period("M") if freq == "M" else days.to_period("Q")
    return sorted(pd.Series(days, index=key).groupby(level=0).max().tolist())


def universe_at(surv: pd.DataFrame, index_name: str, t) -> set:
    """dataset형: index_name의 date ≤ t 최근 스냅샷 멤버(상폐 포함)."""
    idx = surv[(surv["index_name"] == index_name) & (pd.to_datetime(surv["date"]) <= t)]
    if idx.empty:
        return set()
    snap = idx[pd.to_datetime(idx["date"]) == pd.to_datetime(idx["date"]).max()]
    return set(snap["corp_code"].dropna())


# ── 시그널 (PIT look-ahead 게이트) ─────────────────────────────────────────────
def build_signal_index(factor_zoo, pit, item_ids, consol, period_type):
    """시그널 항목별: corp→[(period_end desc, value)] + pit 윈도우 맵. 사전 계산해 t별 조회를 가볍게."""
    fz = factor_zoo[(factor_zoo["item_id"].isin(item_ids)) & (factor_zoo["consol"] == consol)
                    & (factor_zoo["period_type"] == period_type)].copy()
    fz["pe"] = pd.to_datetime(fz["period_end"], errors="coerce")
    idx = {}
    for item in item_ids:
        sub = fz[fz["item_id"] == item].sort_values("pe", ascending=False)
        by_corp = {cc: list(zip(g["pe"], g["value"].astype(float))) for cc, g in sub.groupby("corp_code")}
        win: dict = {}   # (corp, period_end) → [(as_of_from, as_of_until)]  (canonical_id == item)
        if pit is not None:
            for _, r in pit[(pit["canonical_id"] == item) & (pit["consol"] == consol)].iterrows():
                win.setdefault((r["corp_code"], str(r["period_end"])), []).append(
                    (pd.to_datetime(r["as_of_from"], errors="coerce"), pd.to_datetime(r["as_of_until"], errors="coerce")))
        idx[item] = {"by_corp": by_corp, "win": win}
    return idx


def signal_at(sig, corp, t):
    """(corp, t) 시그널 = t 시점 알려졌던 최신 period_end 값. → (value, known_time, used_fallback)."""
    for pe, val in sig["by_corp"].get(corp, ()):   # period_end 내림차순
        if pd.isna(pe):
            continue
        windows = sig["win"].get((corp, pe.strftime("%Y-%m-%d")))
        if windows:                                # PIT 경로: as_of_from ≤ t < as_of_until
            for af, au in windows:
                if pd.notna(af) and af <= t and (pd.isna(au) or t < au):
                    return val, af, False
        elif pe + pd.Timedelta(days=FALLBACK_LAG_DAYS) <= t:   # 보수 폴백
            return val, pe + pd.Timedelta(days=FALLBACK_LAG_DAYS), True
    return None, None, False


# ── 수익률 ────────────────────────────────────────────────────────────────────
def period_return(series, t0, t1):
    """[t0, t1] adj_close 수익률. 상폐 종목은 마지막 adj_close로 청산(−100% 강제 금지)."""
    if series is None or series.empty:
        return None, False
    last = series.index.max()
    if last < t0:                       # t0 이전 상폐 → 매수 불가, 제외
        return None, False
    p0 = series.asof(t0)
    if pd.isna(p0) or p0 <= 0:
        return None, False
    if last < t1:                       # 보유 기간 중 상폐 → 마지막 종가 청산
        return float(series.iloc[-1]) / float(p0) - 1.0, True
    p1 = series.asof(t1)
    return (None, False) if pd.isna(p1) else (float(p1) / float(p0) - 1.0, False)


# ── 통계 ──────────────────────────────────────────────────────────────────────
def _r(x, n=4):
    return round(float(x), n) if x is not None and not pd.isna(x) else None


def perf_stats(returns, ppy):
    r = pd.Series([x for x in returns if x is not None], dtype=float)
    if len(r) == 0:
        return {"cagr": None, "vol": None, "sharpe": None, "mdd": None, "n_periods": 0}
    cum = (1 + r).cumprod()
    years = len(r) / ppy
    cagr = cum.iloc[-1] ** (1 / years) - 1 if years > 0 and cum.iloc[-1] > 0 else None
    sd = r.std(ddof=1) if len(r) > 1 else None
    vol = sd * np.sqrt(ppy) if sd is not None else None
    sharpe = r.mean() / sd * np.sqrt(ppy) if sd else None
    mdd = float((cum / cum.cummax() - 1).min())
    return {"cagr": _r(cagr), "vol": _r(vol), "sharpe": _r(sharpe), "mdd": _r(mdd), "n_periods": len(r)}


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="financial-harness 로컬 백테스트 실행기 (quant 모드 B)")
    ap.add_argument("--run-dir", required=True)
    run_dir = Path(ap.parse_args().run_dir)
    cfg = load_config(run_dir)
    ds = load_datasets(run_dir)
    prices = load_prices(run_dir)
    if ds["factor_zoo"] is None or not prices:
        sys.exit("factor_zoo.parquet 또는 prices_bulk_*.json 누락 — /datasets 다운로드·/prices/bulk 수집 확인")

    signals = cfg["signals"]
    consol, Q, freq = cfg["consol"], int(cfg["quantiles"]), cfg["rebalance"]
    ppy = PPY.get(freq, 12)
    start = pd.to_datetime(cfg["period"].get("start") or "2000-01-01")
    end = pd.to_datetime(cfg["period"].get("end") or "2100-01-01")

    surv = ds["survivorship_free_universe"]
    xwalk = {}   # corp ↔ stock 크로스워크 (survivorship_free가 두 키 모두 보유; 가격은 stock_code 키)
    if surv is not None:
        cw = surv.dropna(subset=["corp_code", "stock_code"])[["corp_code", "stock_code"]].drop_duplicates()
        xwalk = dict(zip(cw["corp_code"], cw["stock_code"]))

    reb = rebalance_dates(prices, freq, start, end)
    if len(reb) < 2:
        sys.exit("리밸런스 날짜 < 2 — 가격 데이터/기간 확인")
    sig_idx = build_signal_index(ds["factor_zoo"], ds["pit_universe_snapshot"],
                                 [s["item_id"] for s in signals], consol, cfg["period_type"])
    fixed_codes = set(cfg["universe"].get("codes", [])) if cfg["universe"].get("type") == "codes" else None

    lookahead_violations = fallback_cells = liquidations = skipped_periods = 0
    prev_members: dict = {}   # quantile → set(corp)  (회전율 계산)
    periods = []              # [{form, realize, gross{q}, turnover{q}}]

    for i in range(len(reb) - 1):
        t0, t1 = reb[i], reb[i + 1]
        corps = fixed_codes if fixed_codes is not None else universe_at(surv, cfg["universe"].get("index_name", ""), t0)

        recs = []   # 시그널 크로스섹션 (look-ahead 게이트 적용)
        for cc in corps:
            vals, ok = {}, True
            for s in signals:
                v, known, fb = signal_at(sig_idx[s["item_id"]], cc, t0)
                if v is None:
                    ok = False
                    break
                if known is not None and known > t0:     # 안전 자기검증 — 발생하면 안 됨
                    lookahead_violations += 1
                fallback_cells += int(fb)
                vals[s["item_id"]] = v
            if ok and period_return(prices.get(xwalk.get(cc, cc)), t0, t1)[0] is not None:
                recs.append({"corp": cc, **vals})
        if len(recs) < Q:
            skipped_periods += 1
            continue

        cs = pd.DataFrame(recs).set_index("corp")   # z-score 가중합 → 합성점수 (desc=높을수록 상위)
        comp = pd.Series(0.0, index=cs.index)
        for s in signals:
            col = cs[s["item_id"]].astype(float)
            z = (col - col.mean()) / col.std(ddof=0) if col.std(ddof=0) > 0 else col * 0
            comp += (z if s.get("direction", "desc") == "desc" else -z) * float(s.get("weight", 1.0))
        qlab = pd.qcut(comp.rank(method="first"), Q, labels=False)   # 0=최하위 … Q-1=최상위

        gross, turnover = {}, {}
        for q in range(Q):
            members = set(comp.index[qlab == q])
            rets = [period_return(prices.get(xwalk.get(cc, cc)), t0, t1) for cc in members]
            liquidations += sum(1 for _, liq in rets if liq)
            vals = [r for r, _ in rets if r is not None]
            gross[q] = float(np.mean(vals)) if vals else None
            prev = prev_members.get(q, set())
            if not prev:
                turnover[q] = 1.0                         # 최초 편입 = 전량 매수
            else:                                         # one-way 회전율 = 0.5·Σ|Δw| (동일가중, 드리프트 무시)
                nn, no = len(members), len(prev)
                turnover[q] = 0.5 * sum(abs((1 / nn if c in members else 0) - (1 / no if c in prev else 0))
                                        for c in members | prev)
            prev_members[q] = members
        periods.append({"form": t0, "realize": t1, "gross": gross, "turnover": turnover})

    if not periods:
        sys.exit("유효 리밸런스 기간 0 — 유니버스·시그널 커버리지 확인")

    # 비용 차감·통계 — cost_bps=round-trip을 one-way 회전율에 적용. 민감도 0/30/60bp 3점.
    top, bot = Q - 1, 0
    dates = [p["realize"] for p in periods]

    def net_series(cost):
        rows = {q: [None if p["gross"][q] is None else p["gross"][q] - p["turnover"][q] * cost / 1e4
                    for p in periods] for q in range(Q)}
        ls = [rows[top][i] - rows[bot][i] if rows[top][i] is not None and rows[bot][i] is not None else None
              for i in range(len(periods))]
        return rows, ls

    cost_sens = {}
    for c in (0, 30, 60):
        rw, lsc = net_series(c)
        cost_sens[str(c)] = {"long_short": perf_stats(lsc, ppy), "q_top": perf_stats(rw[top], ppy)}

    rows, ls = net_series(cfg["cost_bps"])
    quant_stats = {f"q{q+1}": {**perf_stats(rows[q], ppy),
                               "turnover": _r(np.mean([p["turnover"][q] for p in periods]))} for q in range(Q)}

    per_year: dict = {}   # 연도별 수익률 표
    yr = np.array([d.year for d in dates])
    for y in sorted(set(yr)):
        m = yr == y
        row = {f"q{q+1}": _r(np.prod([1 + rows[q][j] for j in range(len(dates)) if m[j] and rows[q][j] is not None]) - 1)
               for q in range(Q)}
        row["long_short"] = _r(sum(ls[j] for j in range(len(dates)) if m[j] and ls[j] is not None))
        per_year[str(int(y))] = row

    out = run_dir / "_workspace" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    results = {
        "config_echo": cfg,
        "gates": {
            "lookahead_violations": lookahead_violations,
            "fallback_lag_cells": fallback_cells,
            "delisted_included": bool(fixed_codes is None and surv is not None),
            "liquidation_assumption": f"상폐 종목은 상폐일 마지막 adj_close로 청산(−100% 강제 안 함). "
                                      f"보유기간 중 청산 {liquidations}건.",
            "cost_sensitivity": cost_sens,
            "trials_note": cfg.get("trials_note", ""),
        },
        "meta": {"rebalance_dates": len(reb), "periods_used": len(periods), "skipped_periods_sparse": skipped_periods,
                 "quantiles": Q, "rebalance": freq, "signals": signals, "period_type": cfg["period_type"]},
        "quantiles": quant_stats,
        "long_short": perf_stats(ls, ppy),
        "per_year": per_year,
    }
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    ts = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in dates]})   # timeseries.csv (기본 cost_bps 누적)
    for q in range(Q):
        ts[f"cum_q{q+1}"] = np.cumprod([1 + (x or 0) for x in rows[q]]) - 1
    ts["cum_long_short"] = np.cumsum([x or 0 for x in ls])
    ts.to_csv(out / "timeseries.csv", index=False)

    print(f"✓ backtest 완료 — periods={len(periods)} lookahead_violations={lookahead_violations} "
          f"fallback_cells={fallback_cells} liquidations={liquidations}")
    print(f"  results.json + timeseries.csv → {out}")


if __name__ == "__main__":
    main()
