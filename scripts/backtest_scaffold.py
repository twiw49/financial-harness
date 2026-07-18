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

PPY = {"M": 12, "Q": 4}  # 리밸런스 빈도별 연간 기간 수
# 앵커(원본 제출일) 부재 시 period_type별 법정 lag 폴백(일). 미지 유형=90.
LEGAL_LAG = {"annual": 90, "quarterly": 45, "ttm": 45, "declared": 45}
DEFAULTS = {"consol": 1, "rebalance": "M", "quantiles": 5, "cost_bps": 30, "period_type": "annual",
            "period": {}, "trials_note": "", "exclude_restated": False}
# forward_vintage 패널(datasets 6번째) 시그널 item_id → fwd_eps_* 컬럼. 행 자체가 vintage(anchor_date=known-시점).
FWD_VINTAGE_COLS = {"FWD_EPS_ENS": "fwd_eps_ens", "FWD_EPS_B": "fwd_eps_b", "FWD_EPS_T": "fwd_eps_t",
                    "FWD_EPS_R": "fwd_eps_r", "FWD_EPS_S": "fwd_eps_s"}


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
            for k in ("factor_zoo", "survivorship_free_universe", "restatement_events", "forward_vintage")}


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


# ── 시그널 (look-ahead 게이트) ─────────────────────────────────────────────────
def build_restated_set(restatement_events):
    """restatement_events → 정정 리스크셋 {(corp, period_end_str)}.
    restatement_events.parquet은 전 행이 non-original 정정 이벤트(value_change/preliminary/restatement/
    sign_only — 'original' revision_type 없음)라 별도 필터 없이 corp×period_end 집합이 곧 리스크셋.
    factor_zoo는 최신 세대 값이므로, 값이 정정된 (corp,기간)의 셀을 원본 제출일에 쓰면 미세 누출 →
    정직 고지용 카운트(config exclude_restated로 제외 가능)."""
    if restatement_events is None:
        return set()
    pe = pd.to_datetime(restatement_events["period_end"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = pd.DataFrame({"corp": restatement_events["corp_code"].values, "pe": pe.values})
    df = df[df["pe"].notna()]
    return set(zip(df["corp"], df["pe"]))


def build_signal_index(factor_zoo, restated_set, item_ids, consol, period_type):
    """시그널 항목별: corp→[(pe, pe_str, value, known_ts, source, is_restated)] pe desc. + forward 드롭 수.
    known_ts 2단계: ① 팩터 행 known_from 컬럼(factor_zoo v2, 원본 정기보고서 제출일, 1순위)
    ③ 부재/null이면 period_type 법정 lag 폴백. (v3.1.3: ② pit original 앵커 삭제 — known_from이 97.5~99.9%를
    커버하고 null 셀은 같은 원천의 pit에도 대부분 부재라 ②의 실질 기여 ≈ 0 → pit 의존 소멸.)
    ★③ 유지: known_from null 셀을 드롭하면 보고서 미수집 기업(상폐 계열 편중)이 조용히 빠져 생존편향이
    뒷문으로 재유입 — 보수적 lag가 정직.
    forward(모델 최신 산출=vintage 아님)는 컬럼이 NULL이어도 1차 드롭."""
    sig = factor_zoo[(factor_zoo["item_id"].isin(item_ids)) & (factor_zoo["consol"] == consol)].copy()
    forward_dropped = int((sig["period_type"] == "forward").sum())
    sig = sig[(sig["period_type"] != "forward") & (sig["period_type"] == period_type)].copy()
    sig["pe"] = pd.to_datetime(sig["period_end"], errors="coerce")
    has_kf = "known_from" in sig.columns
    if has_kf:
        sig["kf"] = pd.to_datetime(sig["known_from"], errors="coerce")
    else:                                          # 구버전 8컬럼 parquet 지원 종료 — 침묵 금지
        print("⚠️  factor_zoo에 known_from 컬럼 없음 (구버전 8컬럼 parquet, 지원 종료). "
              "known-시점을 전량 법정 lag(③)로 처리 — 부정확·보수적입니다. "
              "최신 factor_zoo(v2)를 재다운로드하세요: /api/datasets/factor_zoo/download",
              file=sys.stderr)
    lag = pd.Timedelta(days=LEGAL_LAG.get(period_type, 90))
    idx = {}
    for item in item_ids:
        sub = sig[sig["item_id"] == item].sort_values("pe", ascending=False)
        if sub.empty:
            sys.exit(f"signal '{item}' 행 0 (period_type={period_type} · forward 드롭 후) — "
                     "forward 팩터는 모드 B 사용 불가 (모델 최신 산출, vintage 아님)")
        by_corp = {}
        for cc, g in sub.groupby("corp_code"):
            cells = []
            kfs = g["kf"] if has_kf else [pd.NaT] * len(g)
            for pe, val, kf in zip(g["pe"], g["value"].astype(float), kfs):
                if pd.isna(pe):
                    continue
                ps = pe.strftime("%Y-%m-%d")
                if pd.notna(kf):                              # ① 팩터 행 known_from (1순위)
                    kt, source = kf, "known_from"
                else:                                         # ③ 법정 lag
                    kt, source = pe + lag, "lag"
                cells.append((pe, ps, val, kt, source, (cc, ps) in restated_set))
            by_corp[cc] = cells
        idx[item] = by_corp
    return idx, forward_dropped


def build_vintage_index(fv, item_ids, consol):
    """forward_vintage 패널 → 시그널 항목별 corp→[(anchor, label, value, anchor, 'vintage', False)] anchor 내림차순.
    ★행 자체가 vintage — anchor_date가 그 값이 알려진 시점(A=연간보고서 제출·P=잠정공시·E=업종평균 공표)이므로
    known_from/법정 lag가 불필요하다(anchor_date가 곧 판정 기준). 리밸런스일 t에 anchor_date ≤ t 중 최신 anchor
    행(동률이면 최신 target_fy) 채택 — signal_at이 anchor 내림차순 셀의 첫 kt≤t를 반환하므로 그 규약을 그대로 재사용.
    known_ts=anchor라 signal_at→main의 자기검증(known>t0)이 곧 'anchor_date > t 채택 없음' 검증(lookahead_violations).
    값 NULL이면 그 시그널 없음 처리(선택된 최신 anchor 행 기준 — 더 과거 앵커로 폴백하지 않음, 기존 규약과 동일)."""
    sub = fv[fv["consol"] == consol].copy()
    if sub.empty:
        sys.exit(f"forward_vintage: consol={consol} 행 0 — 패널은 consol=1(연결) 기준")
    sub["anchor"] = pd.to_datetime(sub["anchor_date"], errors="coerce")
    sub = sub.sort_values(["anchor", "target_fy"], ascending=False)   # 최신 anchor·동률 최신 target_fy 우선
    idx = {}
    for item in item_ids:
        col = FWD_VINTAGE_COLS.get(item)
        if col is None:
            sys.exit(f"forward_vintage signal '{item}' 미지 item_id — 지원: {', '.join(FWD_VINTAGE_COLS)}")
        by_corp = {}
        for cc, g in sub.assign(_v=pd.to_numeric(sub[col], errors="coerce")).groupby("corp_code", sort=False):
            cells = []
            for anchor, val in zip(g["anchor"], g["_v"]):
                if pd.isna(anchor):
                    continue
                cells.append((anchor, anchor.strftime("%Y-%m-%d"), None if pd.isna(val) else float(val),
                              anchor, "vintage", False))
            by_corp[cc] = cells
        idx[item] = by_corp
    return idx


def signal_at(cells, t, exclude_restated):
    """(corp cells, t) → t 시점 알려졌던 최신 period_end 값. exclude_restated면 정정 리스크 셀 드롭 후 다음 후보.
    → (value, known_ts, source, pe_str, is_restated, excluded_pes). source ∈ {known_from, lag, vintage}."""
    excluded = []
    for pe, ps, val, kt, source, is_rest in cells:   # pe 내림차순
        if kt > t:
            continue                              # 아직 안 알려짐 (제외 아님)
        if exclude_restated and is_rest:
            excluded.append(ps)                   # 알려졌으나 정정 리스크 → 드롭, 다음 후보로
            continue
        return val, kt, source, ps, is_rest, excluded
    return None, None, None, None, False, excluded


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
    if not prices:
        sys.exit("prices_bulk_*.json 누락 — /prices/bulk 수집 확인")

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
    exclude_restated = bool(cfg["exclude_restated"])
    restated_available = ds["restatement_events"] is not None
    if not restated_available:
        print("⚠️ restatement_events 미제공 — 정정 리스크 게이트 측정 안 함(보고서에 null로 기록). "
              "다운로드(+25cr) 시 restated_value_risk_cells 활성.", file=sys.stderr)
    restated_set = build_restated_set(ds["restatement_events"])
    fz_items, fv_items = [], []                     # 시그널 소스 분리: factor_zoo(기본) vs forward_vintage
    for s in signals:
        src = s.get("source", "factor_zoo")
        if src == "factor_zoo":
            fz_items.append(s["item_id"])
        elif src == "forward_vintage":
            fv_items.append(s["item_id"])
        else:
            sys.exit(f"signal '{s['item_id']}' 미지 source='{src}' — 지원: factor_zoo, forward_vintage")
    sig_idx: dict = {}
    forward_dropped = 0
    if fz_items:
        if ds["factor_zoo"] is None:
            sys.exit("factor_zoo.parquet 누락 — /api/datasets/factor_zoo/download(25cr) 수집 확인")
        idx_fz, forward_dropped = build_signal_index(ds["factor_zoo"], restated_set,
                                                     fz_items, consol, cfg["period_type"])
        sig_idx.update(idx_fz)
    if fv_items:                                     # forward 팩터의 유일한 합법 입구(factor_zoo forward 행은 계속 드롭)
        if ds["forward_vintage"] is None:
            sys.exit("forward_vintage.parquet 누락 — forward 팩터 백테스트는 이 패널이 유일한 합법 입구. "
                     "/api/datasets/forward_vintage/download(+25cr) 수집 확인")
        sig_idx.update(build_vintage_index(ds["forward_vintage"], fv_items, consol))
    fixed_codes = set(cfg["universe"].get("codes", [])) if cfg["universe"].get("type") == "codes" else None

    lookahead_violations = known_from_cells = fallback_cells = forward_vintage_cells = liquidations = skipped_periods = 0
    used_restated: set = set()      # (corp, item, pe) 실제 사용된 정정 리스크 셀
    excluded_restated: set = set()  # (corp, item, pe) exclude_restated로 드롭된 셀
    prev_members: dict = {}         # quantile → set(corp)  (회전율 계산)
    periods = []                    # [{form, realize, gross{q}, turnover{q}}]

    for i in range(len(reb) - 1):
        t0, t1 = reb[i], reb[i + 1]
        corps = fixed_codes if fixed_codes is not None else universe_at(surv, cfg["universe"].get("index_name", ""), t0)

        recs = []   # 시그널 크로스섹션 (look-ahead 게이트 적용)
        for cc in corps:
            vals, ok = {}, True
            for s in signals:
                item = s["item_id"]
                v, known, source, ps, is_rest, excl = signal_at(sig_idx[item].get(cc, ()), t0, exclude_restated)
                for ep in excl:
                    excluded_restated.add((cc, item, ep))
                if v is None:
                    ok = False
                    break
                if known > t0:                           # 안전 자기검증 — 발생하면 안 됨
                    lookahead_violations += 1
                if source == "known_from":               # ① 팩터 행 제출일
                    known_from_cells += 1
                elif source == "vintage":                # forward_vintage 앵커 셀(anchor_date=known-시점)
                    forward_vintage_cells += 1
                else:                                    # ③ 법정 lag
                    fallback_cells += 1
                if is_rest:
                    used_restated.add((cc, item, ps))
                vals[item] = v
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

    date_anchored = known_from_cells                  # ① known_from = 실제 날짜 앵커 (anchor_coverage_pct 분자)
    total_known = date_anchored + fallback_cells       # ①+③ 전체 채택 셀
    out = run_dir / "_workspace" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    results = {
        "config_echo": cfg,
        "gates": {
            "lookahead_violations": lookahead_violations,
            "fallback_lag_cells": fallback_cells,
            "known_from_cells": known_from_cells,
            "forward_vintage_cells": forward_vintage_cells,
            "anchor_coverage_pct": _r(date_anchored / total_known * 100, 2) if total_known else None,
            # None = restatement_events 미제공(+25cr 패널) — "측정 안 함"을 0("리스크 없음")과 구분
            "restated_value_risk_cells": len(used_restated) if restated_available else None,
            "restated_cells_excluded": len(excluded_restated) if restated_available else None,
            "forward_signal_rows_dropped": forward_dropped,
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

    cov = _r(date_anchored / total_known * 100, 1) if total_known else None
    print(f"✓ backtest 완료 — periods={len(periods)} lookahead_violations={lookahead_violations} "
          f"anchor_coverage={cov}% (known_from={known_from_cells}/lag={fallback_cells}) "
          f"vintage={forward_vintage_cells} "
          f"restated_risk={len(used_restated)} excluded={len(excluded_restated)} "
          f"forward_dropped={forward_dropped} liquidations={liquidations}")
    print(f"  results.json + timeseries.csv → {out}")


if __name__ == "__main__":
    main()
