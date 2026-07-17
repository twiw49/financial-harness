#!/usr/bin/env python3
"""
expand_citations.py — Citation Drawer 마크업 자동 확장기
══════════════════════════════════════════════════════════
report-writer가 본문에 간단한 토큰만 쓰면, 00_raw/의 원시 JSON에서
출처 메타데이터(rcp_no, source_anchor, quality, n_sources, confidence,
description 등)를 조회해 report-template.md §4 규격의 완전한
<span class="cited" ...> 마크업으로 치환한다.

> 목적: report-writer가 data-* 속성 8~10개(이스케이프된 JSON 포함)를
>       손으로 복사하던 작업을 제거 → 속도↑, 휴먼에러↓. **출처 필드는
>       동일한 JSON에서 그대로 가져오므로 품질은 1:1 보존된다.**

사용법:
  python3 expand_citations.py <RUN_DIR> [html_file]
  # html_file 미지정 시 <RUN_DIR>/index.html

토큰 문법 (파이프 구분 key=value; disp=화면 표시 텍스트):
  Hyean 원본/파생 지표 (★ 자동조회 핵심):
    {{h|item=IS_OPR|period=2025-12-31|consol=1|label=영업이익|disp=43.6조원}}
      · item/period/consol로 00_raw JSON에서 레코드를 찾아
        rcp_no·source_anchor·quality·n_sources·confidence·value·description·statement 자동 주입.
      · consol 생략 시 1(연결) 우선, 없으면 아무 거나 매칭.
      · label/disp 생략 시 label_ko/포맷값 사용.
  웹:      {{w|name=...|url=...|type=commercial|label=...|value=...|disp=...}}
  추정:    {{e|name=...|label=...|value=...|disp=...}}
  감사:    {{a|rcp=...|corp=...|label=...|value=...|disp=...}}
  인사이트:{{i|cat=insight_mda|text=...|corp=...|label=...|value=...|disp=...}}
  Deep:   {{d|dtype=compensation|rcp=...|corp=...|label=...|value=...|disp=...}}

종료코드: 미해결 hyean 토큰(JSON 미스)이 있으면 1, 전부 성공이면 0.
미스는 절대 조용히 삭제하지 않는다 — best-effort span + 경고 출력.
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

STMT_BY_PREFIX = {"IS": "IS", "BS": "BS", "CF": "CF", "CIS": "CIS", "DRV": "RATIO",
                  "PS": "MARKET",   # 주가통계 — rcp_no 없는 시장데이터 클래스
                  "VAL": "MODEL"}   # 밸류에이션 모델값 — valuation.json 합성 (rcp_no 부재, formula+inputs 추적)
_RUN_DATE = datetime.date.today().isoformat()  # web citation fetched-at 기본값


def statement_of(item_id: str) -> str:
    pre = item_id.split("_", 1)[0]
    return STMT_BY_PREFIX.get(pre, "")


def esc(v) -> str:
    """속성값 HTML 이스케이프 (큰따옴표 → &quot;)."""
    return html.escape(str(v), quote=True)


def esc_json(obj) -> str:
    """dict/list/str을 JSON 직렬화 후 HTML 이스케이프. 이미 str이면 그대로 escape."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        s = obj
    else:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return html.escape(s, quote=True)


def load_records(raw: Path):
    """00_raw의 모든 재무 JSON을 (corp_code, item_id, period_end) → record 인덱스로 적재.

    다중기업 지원: summary.json 외에 {name}_summary.json 등 financials/ratios를 가진
    모든 파일과 fin_*/financ* 파일을 corp_code별로 인덱싱한다. 멀티컴퍼니 수집을
    `00_raw/{corp_code}/summary.json` 서브폴더 구조로 둔 경우도 인덱싱한다(루트 복사 불필요).

    반환: index dict, corp_codes(list, 등장 순서), item_meta
    index key: (cc, iid, per, consol) / (cc, iid, per). 단일기업이면 corp 없는
              (iid, per, consol) / (iid, per) 도 등록(하위호환).
    """
    index = {}
    corp_codes = []
    item_meta = {}

    def add_cc(cc):
        if cc and cc not in corp_codes:
            corp_codes.append(cc)

    def put(rec, consol, cc):
        iid = rec.get("item_id")
        per = rec.get("period") or rec.get("period_end")
        if not iid or not per:
            return
        per = per[:10]
        norm = {
            "item_id": iid, "period_end": per, "corp_code": cc,
            "value": rec.get("value"), "confidence": rec.get("confidence"),
            "quality": rec.get("quality"), "n_sources": rec.get("n_sources"),
            "rcp_no": rec.get("rcp_no"), "source_url": rec.get("source_url"),
            "source_anchor": rec.get("source_anchor"),
            "primary_item_id": rec.get("primary_item_id"),
            "source_type": rec.get("source_type"), "label_ko": rec.get("label_ko"),
            "description": rec.get("description"), "is_derived": rec.get("is_derived"),
            "formula": rec.get("formula"), "inputs": rec.get("inputs"),
            "consol": consol if consol is not None else rec.get("consol"),
        }
        c = norm["consol"]
        # 더 풍부한 레코드 우선 보존: rcp_no(원본 출처) > formula(파생 추적) > 없음
        def _rich(r):
            return (2 if r.get("rcp_no") else 0) + (1 if r.get("formula") else 0)
        for key in [(cc, iid, per, c), (cc, iid, per)]:
            old = index.get(key)
            if old is None or _rich(norm) > _rich(old):
                index[key] = norm

    # summary-like: financials/ratios(dict) + corp_code 를 가진 모든 json
    # 루트(*.json) + 종목별 서브폴더(*/summary.json — 멀티컴퍼니 수집 표준)를 함께 스캔.
    # screen/summ_*.json·web/*.json 등 보조 산출물은 패턴 불일치로 자동 제외.
    for f in sorted(set(raw.glob("*.json")) | set(raw.glob("*/summary.json"))):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        nm = f.stem
        cc = d.get("corp_code")
        has_fin_blocks = isinstance(d.get("financials"), dict) or isinstance(d.get("ratios"), dict)
        is_fin_file = (nm.startswith("fin_") or nm.startswith("financ")) and isinstance(d.get("items"), list)
        if has_fin_blocks:
            add_cc(cc)
            if d.get("item_meta"):
                item_meta.update(d.get("item_meta"))
            consol_hint = d.get("consol")
            for sect in ("financials", "ratios"):
                blk = d.get(sect)
                if isinstance(blk, dict):
                    for iid, rows in blk.items():
                        # rows가 list(여러 기간) 또는 단일 dict(최신 1기간, summary.ratios 구조) 모두 처리
                        row_list = rows if isinstance(rows, list) else ([rows] if isinstance(rows, dict) else [])
                        for r in row_list:
                            if isinstance(r, dict):
                                r.setdefault("item_id", iid)
                                put(r, r.get("consol", consol_hint), cc)
        if is_fin_file:
            add_cc(cc)
            consol = d.get("consol")
            for r in d.get("items", []):
                if isinstance(r, dict):
                    put(r, consol, cc)

        # 주가통계 자동 합성 — summary include=price_stats / price_stats.json의
        # {period: {field: value}}를 PS_{PERIOD}_{FIELD} 레코드로. report-writer가
        # *_psupp.json을 수작업 합성하던 반복(054/055/056)을 제거한다.
        ps = d.get("price_stats") or (d.get("periods") if nm.startswith("price_stats") else None)
        if isinstance(ps, dict) and cc:
            as_of_default = d.get("market_cap_as_of") or d.get("as_of") or ""
            for per, stats in ps.items():
                if not isinstance(stats, dict):
                    continue
                as_of = stats.get("data_to") or as_of_default
                for field, val in stats.items():
                    if not isinstance(val, (int, float)):
                        continue
                    put({
                        "item_id": f"PS_{per}_{field.upper()}",
                        "period": str(as_of) or str(per),
                        "value": val,
                        "confidence": "high",
                        "label_ko": f"{per} {field}",
                        "source_anchor": {"dataset": f"price_stats_{per}",
                                          "field": field, "as_of": str(as_of)},
                    }, None, cc)

        # 밸류에이션 모델값 합성 — valuation.json의 방법별 적정가·범위·시나리오·Forward EPS를
        # VAL_* 레코드로. 플랜이 valuation을 적정가 '1차 출처'로 규정하는데 인용 id가 없어
        # 원문 링크 없는 estimate span으로 열화되던 갭 해소 (RETRO 002 C-3).
        if nm.startswith("valuation") and isinstance(d.get("methods"), list) and cc:
            v_per = (d.get("as_of") or "")[:10] or "model"
            v_anchor = {"dataset": "valuation", "as_of": d.get("as_of"),
                        "price_date": d.get("price_date")}

            def vput(iid, val, formula, inputs=None, label=None):
                if not isinstance(val, (int, float)):
                    return
                put({"item_id": iid, "period": v_per, "value": val,
                     "confidence": "medium", "label_ko": label or iid,
                     "formula": formula, "inputs": inputs or {"basis": d.get("basis") or "Hyean 모델"},
                     "source_anchor": v_anchor}, None, cc)

            for m in d["methods"]:
                if not isinstance(m, dict) or m.get("excluded") or not m.get("method"):
                    continue
                vput(f"VAL_{str(m['method']).upper()}", m.get("fair_value"),
                     m.get("label") or m["method"], m.get("key_inputs"),
                     f"적정가({m.get('label') or m['method']})")
            for k in ("low", "mid", "high"):
                vput(f"VAL_RANGE_{k.upper()}", (d.get("range") or {}).get(k),
                     "다방법 수렴 적정가 범위", None, f"적정가 범위({k})")
            for k in ("bear", "base", "bull"):
                vput(f"VAL_SCENARIO_{k.upper()}", (d.get("scenarios") or {}).get(k),
                     "시나리오 적정가", None, f"시나리오 적정가({k})")
            fe = d.get("forward_eps") or {}
            for k in ("low", "mid", "high"):
                vput(f"VAL_FWD_EPS_{k.upper()}", fe.get(k),
                     fe.get("label") or "다방법 Forward EPS", None, f"Forward EPS({k})")

    # 파생지표 provenance 합성: ratios는 최신 기간만 formula/inputs를 갖는다.
    # 같은 (corp, item)의 formula를 과거 기간 레코드에 전파하고, inputs는 해당
    # 기간의 입력 항목 값을 인덱스에서 직접 조회해 합성한다 (출처 URL 포함).
    formulas, input_keys = {}, {}
    for rec in index.values():
        if rec.get("formula"):
            k = (rec.get("corp_code"), rec["item_id"])
            formulas.setdefault(k, rec["formula"])
            if isinstance(rec.get("inputs"), dict):
                input_keys.setdefault(
                    k, [i for i in rec["inputs"] if not i.endswith("_url")])
    for rec in {id(r): r for r in index.values()}.values():  # 동일 객체 중복 제거 순회
        if rec.get("formula") or not str(rec.get("item_id", "")).startswith("DRV_"):
            continue
        k = (rec.get("corp_code"), rec["item_id"])
        f = formulas.get(k)
        if not f:
            continue
        per, cc, consol = rec["period_end"], rec.get("corp_code"), rec.get("consol")
        inp = {}
        for ik in input_keys.get(k, []):
            src = index.get((cc, ik, per, consol)) or index.get((cc, ik, per))
            if src and src.get("value") is not None:
                inp[ik] = src["value"]
                if src.get("source_url"):
                    inp[ik + "_url"] = src["source_url"]
        if inp:
            rec["formula"] = f
            rec["inputs"] = inp

    # 단일기업이면 corp 없는 키도 등록(하위호환 — corp= 미지정 토큰 지원)
    if len(corp_codes) == 1:
        for (cc, *rest), rec in list(index.items()):
            index[tuple(rest)] = rec

    return index, corp_codes, item_meta


def fmt_value(v):
    """원시 숫자를 화면 표시용으로 포맷 (disp 미지정 시 fallback)."""
    if v is None:
        return ""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    a = abs(n)
    if a >= 1e12:
        return f"{n/1e12:.2f}조원"
    if a >= 1e8:
        return f"{n/1e8:.1f}억원"
    if a < 10 and a != 0:  # 비율 추정
        return f"{n*100:.1f}%" if a < 1 else f"{n:.2f}"
    return f"{n:,.0f}"


def parse_token(body: str) -> dict:
    """'item=IS_OPR|period=...|disp=...' → dict. disp/text는 마지막에 와도 됨."""
    out = {}
    for part in body.split("|"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
        elif part.strip() and "_kind" not in out:
            out["_kind"] = part.strip()
    return out


def build_hyean(tok, index, corp_codes, item_meta, misses):
    iid = tok.get("item")
    per = (tok.get("period") or "")[:10]
    consol = tok.get("consol")
    consol = {"c1": "1", "1": "1", "c0": "0", "0": "0"}.get(consol, consol)
    tok_cc = tok.get("corp")
    # 조회 대상 기업: 토큰 지정 → 그 기업, 단일기업 → 그 기업, 다기업+미지정 → 전체 시도(최후)
    if tok_cc:
        cc_list = [tok_cc]
    elif len(corp_codes) == 1:
        cc_list = [corp_codes[0]]
    else:
        cc_list = [None] + corp_codes  # None=하위호환 bare 키(다기업이면 없음) → 그다음 각 기업
    rec = None
    if iid:
        for c in cc_list:
            keys = ([(c, iid, per, consol)] if consol is not None else []) + \
                   [(c, iid, per, "1"), (c, iid, per, 1), (c, iid, per, "0"), (c, iid, per, 0), (c, iid, per)]
            # 단일기업 하위호환: c is None이면 corp 없는 키로 변환
            if c is None:
                keys = [k[1:] for k in keys]
            for key in keys:
                if key in index:
                    rec = index[key]
                    break
            if rec:
                break
    if rec is None and iid and iid.split("_", 1)[0] in ("PS", "MKT", "VAL"):
        # 시장통계·모델값은 as_of 스냅샷 1개뿐 — 합성 레코드의 기간 키(as_of/data_to)를
        # writer가 알 수 없으므로 (corp, item)만으로 최신 레코드 매칭 (RETRO 002 C-2: PS_ 전건 미해결)
        allowed = {c for c in cc_list if c}
        best = None
        for r in index.values():
            if r.get("item_id") != iid:
                continue
            if allowed and r.get("corp_code") not in allowed:
                continue
            if best is None or str(r.get("period_end") or "") > str(best.get("period_end") or ""):
                best = r
        rec = best
    label = tok.get("label") or (item_meta.get(iid, {}) or {}).get("label_ko") or (rec or {}).get("label_ko") or iid
    desc = (rec or {}).get("description") or (item_meta.get(iid, {}) or {}).get("description") or ""
    val = (rec or {}).get("value")
    disp = tok.get("disp") or fmt_value(val)
    cc = tok_cc or (rec or {}).get("corp_code") or (corp_codes[0] if len(corp_codes) == 1 else "")
    stmt = statement_of(iid or "")
    a = ['<span class="cited" data-source="hyean"']
    if cc:
        a.append(f'data-corp-code="{esc(cc)}"')
    if iid:
        a.append(f'data-item-id="{esc(iid)}"')
    if per:
        a.append(f'data-period-end="{esc(per)}"')
    if rec is None:
        misses.append(f"{iid}@{per}(consol={consol})")
        # best-effort: 토큰 정보만으로 span 생성 (citation 절대 삭제 안 함)
        if tok.get("value"):
            a.append(f'data-value="{esc(tok["value"])}"')
        a.append('data-confidence="low" data-citation-fallback="json-miss"')
        a.append(f'data-label="{esc(label)}">{html.escape(disp)}</span>')
        return " ".join(a)
    if rec.get("rcp_no"):
        a.append(f'data-rcp-no="{esc(rec["rcp_no"])}"')
    if rec.get("source_url"):
        a.append(f'data-source-url="{esc(rec["source_url"])}"')
    if rec.get("source_anchor"):
        a.append(f'data-source-anchor="{esc_json(rec["source_anchor"])}"')
    if rec.get("confidence"):
        a.append(f'data-confidence="{esc(rec["confidence"])}"')
    if rec.get("quality"):
        a.append(f'data-quality="{esc_json(rec["quality"])}"')
    if stmt:
        a.append(f'data-statement="{esc(stmt)}"')
    if rec.get("consol") is not None:
        a.append(f'data-consol="{esc(rec["consol"])}"')
    if rec.get("n_sources") is not None:
        a.append(f'data-n-sources="{esc(rec["n_sources"])}"')
    if rec.get("primary_item_id"):
        a.append(f'data-primary-item-id="{esc(rec["primary_item_id"])}"')
    # formula/inputs가 있으면 그 자체로 파생지표 — is_derived 필드 부재(summary.ratios)에도 주입
    if rec.get("formula"):
        a.append(f'data-formula="{esc(rec["formula"])}"')
    if rec.get("inputs"):
        a.append(f'data-inputs="{esc_json(rec["inputs"])}"')
    if val is not None:
        a.append(f'data-value="{esc(val)}"')
    a.append(f'data-label="{esc(label)}"')
    if desc:
        a.append(f'data-description="{esc(desc)}"')
    return " ".join(a) + f">{html.escape(disp)}</span>"


def build_web(tok):
    t = tok.get("type", "")
    conf = {"official": "high", "commercial": "medium", "analyst": "medium",
            "news": "low", "blog": "low"}.get(t, tok.get("confidence", "medium"))
    # fetched-at 미지정 시 오늘 날짜 자동 채움 (WEB_MUST 충족 — 조회일 = 실행일)
    tok.setdefault("fetched", _RUN_DATE)
    a = ['<span class="cited" data-source="web"']
    for attr, key in [("data-source-name", "name"), ("data-source-url", "url"),
                      ("data-source-type", "type"), ("data-fetched-at", "fetched"),
                      ("data-label", "label"), ("data-value", "value")]:
        if tok.get(key):
            a.append(f'{attr}="{esc(tok[key])}"')
    a.append(f'data-confidence="{esc(conf)}"')
    disp = tok.get("disp") or tok.get("value") or ""
    return " ".join(a) + f">{html.escape(str(disp))}</span>"


def build_simple(tok, source, attrmap):
    a = [f'<span class="cited" data-source="{source}"']
    for attr, key in attrmap:
        if tok.get(key):
            a.append(f'{attr}="{esc(tok[key])}"')
    disp = tok.get("disp") or tok.get("value") or ""
    return " ".join(a) + f">{html.escape(str(disp))}</span>"


KIND = {
    "h": "hyean", "w": "web", "e": "estimate", "a": "audit", "i": "insight", "d": "deep",
}
TOKEN_RE = re.compile(r"\{\{\s*([hwiead])\s*\|(.*?)\}\}", re.S)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    run_dir = Path(sys.argv[1])
    html_file = Path(sys.argv[2]) if len(sys.argv) > 2 else run_dir / "index.html"
    raw = run_dir / "_workspace" / "00_raw"
    if not html_file.exists():
        print(f"✗ HTML 없음: {html_file}")
        sys.exit(2)
    index, corp_codes, item_meta = load_records(raw)
    text = html_file.read_text()
    misses, counts = [], {k: 0 for k in KIND}

    def repl(m):
        kind = m.group(1)
        tok = parse_token(m.group(2))
        counts[kind] += 1
        if kind == "h":
            return build_hyean(tok, index, corp_codes, item_meta, misses)
        if kind == "w":
            return build_web(tok)
        if kind == "e":
            return build_simple(tok, "estimate", [("data-source-name", "name"),
                                ("data-label", "label"), ("data-value", "value")])
        if kind == "a":
            return build_simple(tok, "audit", [("data-rcp-no", "rcp"), ("data-corp-code", "corp"),
                                ("data-label", "label"), ("data-value", "value")])
        if kind == "i":
            return build_simple(tok, "insight", [("data-corp-code", "corp"),
                                ("data-context-category", "cat"), ("data-context-text", "text"),
                                ("data-label", "label"), ("data-value", "value")])
        if kind == "d":
            return build_simple(tok, "deep", [("data-deep-type", "dtype"), ("data-rcp-no", "rcp"),
                                ("data-corp-code", "corp"), ("data-label", "label"), ("data-value", "value")])
        return m.group(0)

    new_text, n = TOKEN_RE.subn(repl, text)
    html_file.write_text(new_text)
    total = sum(counts.values())
    print(f"✓ 토큰 확장: {total}개 (hyean {counts['h']} / web {counts['w']} / "
          f"estimate {counts['e']} / audit {counts['a']} / insight {counts['i']} / deep {counts['d']})")
    print(f"  인덱스 적재 레코드: {len(index)} | corp_codes: {', '.join(corp_codes) if corp_codes else '(없음)'}")
    if misses:
        print(f"  ⚠ hyean JSON 미스 {len(misses)}건 (fallback span 생성, 삭제 안 됨):")
        for x in misses[:20]:
            print(f"     - {x}")
        sys.exit(1)
    print("  미해결 토큰 0 — 전부 JSON 매칭 성공")
    sys.exit(0)


if __name__ == "__main__":
    main()
