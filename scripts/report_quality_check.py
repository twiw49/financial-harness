#!/usr/bin/env python3
"""
financial-harness report quality check
═══════════════════════════════════════
보고서 디렉토리를 분석하여 품질 점수를 산출한다.

사용법:
  python scripts/report_quality_check.py /path/to/reports/016_삼성전자_20260531
  python scripts/report_quality_check.py /path/to/reports/              # 전체 보고서
  python scripts/report_quality_check.py /path/to/reports/ --summary    # 요약만
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ═══════════════════════════════════════
# 1. Data Completeness (데이터 완전성)
# ═══════════════════════════════════════

CORE_FILES = {"summary", "discover", "fin_is_c1", "fin_bs_c1", "fin_cf_c1"}
IMPORTANT_FILES = {"audit", "risk", "events", "insight_mda", "insight_risk", "benchmark"}
OPTIONAL_FILES = {
    "fin_ratio_c1", "insight_capex", "insight_sales_detail", "insight_market",
    "insight_debt", "macro_context", "price", "price_stats", "quarterly", "peers",
    "deep_shareholders", "deep_executives", "deep_employees", "notes_segment",
}


def check_data_completeness(report_dir: Path) -> dict:
    """00_raw/ 디렉토리의 API 응답 파일 존재/비어있음 체크."""
    raw_dir = report_dir / "_workspace" / "00_raw"
    if not raw_dir.exists():
        return {"score": 0, "grade": "F", "detail": "00_raw/ 디렉토리 없음", "files": {}}

    files = {}
    # 00_raw 직속 + 종목별 하위폴더(00_raw/{corp}/*.json, 멀티컴퍼니 수집 표준) 모두 스캔.
    # 하위폴더 파일은 {폴더명}_{stem}으로 등록 → 아래 다기업 _summary 패턴이 인식(점수 0 버그 수정).
    raw_jsons = list(raw_dir.glob("*.json"))
    for sub in raw_dir.iterdir():
        if sub.is_dir():
            raw_jsons += list(sub.glob("*.json"))
    for f in raw_jsons:
        name = f"{f.parent.name}_{f.stem}" if f.parent != raw_dir else f.stem
        size = f.stat().st_size
        empty = size < 50
        # JSON 내부도 체크 (count=0, error 등)
        has_data = False
        if not empty:
            try:
                data = json.loads(f.read_text())
                if isinstance(data, dict):
                    if data.get("error"):
                        has_data = False
                    elif data.get("count", 1) == 0 and "values" not in data:
                        has_data = False
                    else:
                        has_data = True
                elif isinstance(data, list):
                    has_data = len(data) > 0
                else:
                    has_data = True
            except Exception:
                has_data = not empty
        files[name] = {"size": size, "empty": empty, "has_data": has_data}

    # 파일명 별칭 정규화 — 에이전트가 쓰는 다양한 명명을 표준 키로 인식 (반복 적용)
    #  · 연결 재무: fin_is_consol / financials_is_c1 등 → fin_is_c1
    #  · insight 서술: /context fallback 산출물 context_mda 등 → insight_mda
    #  · 다기업 prefix 제거: kakao_summary→summary, naver_context_mda→context_mda→insight_mda
    changed, rounds = True, 0
    while changed and rounds < 4:
        changed, rounds = False, rounds + 1
        for name in list(files.keys()):
            if not files[name]["has_data"]:
                continue
            cands = []
            if "_" in name:                       # 다기업 prefix 제거(첫 _ 이후)
                cands.append(name.split("_", 1)[1])
            m = re.match(r"^fin_(is|bs|cf|ratio)_(consol|c1|1)$", name) or \
                re.match(r"^financials?_(is|bs|cf|ratio)_(consol|c1|1)$", name)
            if m:
                cands.append(f"fin_{m.group(1)}_c1")
            if name.startswith("context_"):       # /context fallback → insight
                cands.append("insight_" + name[len("context_"):])
            for canon in cands:
                if canon and canon not in files:
                    files[canon] = files[name]
                    changed = True

    # insight 통합 파일 내용 기반 인식 — collector는 save_as="insight" 한 파일에 카테고리를
    # 합쳐 저장(items[].category="insight_mda" 등) → 파일명 탐색만으로는 오탐 (RETRO 002 C-1)
    for f in raw_jsons:
        stem = f"{f.parent.name}_{f.stem}" if f.parent != raw_dir else f.stem
        if not (stem == "insight" or stem.endswith("_insight") or stem == "insight_context"):
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        for it in (data.get("items") or []) if isinstance(data, dict) else []:
            cat = it.get("category") if isinstance(it, dict) else None
            if isinstance(cat, str) and cat:
                key = cat if cat.startswith("insight_") else f"insight_{cat}"
                files.setdefault(key, {"size": f.stat().st_size, "empty": False, "has_data": True})

    # 점수 계산
    core_present = sum(1 for f in CORE_FILES if f in files and files[f]["has_data"])
    important_present = sum(1 for f in IMPORTANT_FILES if f in files and files[f]["has_data"])
    total_files = len([f for f in files.values() if f["has_data"]])

    # /summary 패턴 인식: summary.json에 financials가 있으면 IS/BS/CF 대체
    core_embedded = set()  # summary에 내장되어 충족된 core 파일 (경고 표시에서 제외)
    if "summary" in files and files["summary"]["has_data"]:
        try:
            summary_data = json.loads((raw_dir / "summary.json").read_text())
            if isinstance(summary_data, dict) and summary_data.get("financials"):
                missing_fin = {"fin_is_c1", "fin_bs_c1", "fin_cf_c1"} - {
                    f for f in CORE_FILES if f in files and files[f]["has_data"]
                }
                core_present += len(missing_fin)
                core_embedded |= missing_fin
        except Exception:
            pass

    # /summary 패턴: summary에 risk/benchmark/events 포함 시 important 보완
    summary_embedded = set()
    if "summary" in files and files["summary"]["has_data"]:
        try:
            summary_data = json.loads((raw_dir / "summary.json").read_text())
            if isinstance(summary_data, dict):
                if summary_data.get("risk") and "risk" not in files:
                    important_present += 1
                    summary_embedded.add("risk")
                if summary_data.get("benchmark") and "benchmark" not in files:
                    important_present += 1
                    summary_embedded.add("benchmark")
                if (summary_data.get("recent_events") or summary_data.get("events")) and "events" not in files:
                    important_present += 1
                    summary_embedded.add("events")
        except Exception:
            pass

    # 런 유형 패턴 — 발동 시 core를 충족 처리하고 core_embedded에 기록해 경고에서도 제외
    # 다기업 패턴: {corp_code}_summary.json 파일이 2+ 있으면 비교/섹터 분석
    multi_summaries = [f for f in files if f.endswith("_summary") and files[f]["has_data"]]
    if len(multi_summaries) >= 2:
        # 다기업 summary → discover+summary+fin_is/bs/cf 모두 대체
        core_present = len(CORE_FILES)
        core_embedded |= set(CORE_FILES)
        # 섹터·비교 분석은 개별사 audit/insight를 다 받지 않는 게 정상(N사 summary로 비교).
        # 단일종목 기준 IMPORTANT 감점 방지 — 매크로·스크리닝과 동일 처리 (C-2)
        important_present = len(IMPORTANT_FILES)
        summary_embedded |= set(IMPORTANT_FILES)

    # 스크리닝 패턴: screen*.json이 있으면 개별 재무 불필요 (screening_/screen_ 모두 인정)
    screening_files = [f for f in files if f.startswith("screen") and files[f]["has_data"]]
    if screening_files:
        core_present = max(core_present, len(CORE_FILES) - 1)  # discover만 누락 가능
        core_embedded |= set(CORE_FILES) - {"discover"}
        # 스크리닝은 기업별 심층 파일(audit/insight 등) 불요 — N/A 처리
        important_present = len(IMPORTANT_FILES)
        summary_embedded |= set(IMPORTANT_FILES)

    # 매크로 패턴: macro_compact.json 또는 ts_ECOS_*.json이 3+ 있으면 매크로 분석
    macro_files = [f for f in files if (f.startswith("ts_ECOS_") or f == "macro_compact") and files[f]["has_data"]]
    if len(macro_files) >= 3:
        # 매크로는 재무 데이터 불필요 — 기업 중심 IMPORTANT(audit/insight 등)도 N/A 처리
        core_present = len(CORE_FILES)
        core_embedded |= set(CORE_FILES)
        important_present = len(IMPORTANT_FILES)
        summary_embedded |= set(IMPORTANT_FILES)

    core_present = min(core_present, len(CORE_FILES))
    core_score = core_present / len(CORE_FILES) * 40  # 40점
    important_score = important_present / len(IMPORTANT_FILES) * 30  # 30점
    volume_score = min(total_files / 15, 1.0) * 30  # 30점 (15개 이상이면 만점)
    score = round(core_score + important_score + volume_score)

    important_present = min(important_present, len(IMPORTANT_FILES))
    core_present = min(core_present, len(CORE_FILES))
    missing_core = [
        f for f in CORE_FILES
        if (f not in files or not files.get(f, {}).get("has_data")) and f not in core_embedded
    ]
    missing_important = [
        f for f in IMPORTANT_FILES
        if (f not in files or not files.get(f, {}).get("has_data")) and f not in summary_embedded
    ]

    return {
        "score": score,
        "grade": _grade(score),
        "core_present": core_present,
        "core_total": len(CORE_FILES),
        "missing_core": missing_core,
        "missing_important": missing_important,
        "total_files": total_files,
        "files": files,
    }


# ═══════════════════════════════════════
# 2. Citation Coverage (원문 출처 추적)
# ═══════════════════════════════════════

CITATION_RE = re.compile(r'<span[^>]*class="cited"[^>]*>', re.IGNORECASE)
DATA_SOURCE_RE = re.compile(r'data-source="([^"]*)"')
DATA_ATTR_RE = re.compile(r'data-([\w-]+)="([^"]*)"')

# Hyean 필수 속성
# 기본 식별 속성(항상 필요) + 출처 추적(둘 중 하나):
#   · 원본 지표: rcp-no + source-anchor
#   · 파생 지표(ROE/PBR 등): formula + inputs (입력 항목별 rcp_no가 inputs에 내장)
# report-template.md §4의 두 hyean 패턴과 일치. 파생지표에 가짜 rcp-no/anchor를 채우는
# 우회(placeholder-stuffing)보다 formula+inputs가 추적성이 높으므로 동등하게 인정한다.
HYEAN_BASE = {"source", "label", "value", "corp-code", "item-id", "period-end", "confidence", "quality"}
HYEAN_PROV_ORIGINAL = {"rcp-no", "source-anchor"}
HYEAN_PROV_DERIVED = {"formula", "inputs"}
WEB_MUST = {"source", "source-name", "source-url", "source-type", "fetched-at"}
DEEP_MUST = {"source", "deep-type", "rcp-no", "corp-code"}


def check_citation_coverage(report_dir: Path) -> dict:
    """index.html의 Citation 마크업 분석."""
    html_path = report_dir / "index.html"
    if not html_path.exists():
        return {"score": 0, "grade": "F", "detail": "index.html 없음"}

    html = html_path.read_text(errors="replace")
    # design-kit이 <style>/<script> 주석에 담은 예시 마크업이 매 런 팬텀 인용 2건으로 집계
    # (가짜 source 'hyean/web/deep/...'가 diversity 점수까지 인플레) → 본문만 스캔
    body_html = re.sub(r"<style>.*?</style>|<script>.*?</script>", "", html, flags=re.S)
    citations = CITATION_RE.findall(body_html)
    total = len(citations)

    if total == 0:
        return {"score": 0, "grade": "F", "detail": "Citation 마크업 0개", "total": 0}

    # 소스별 분류
    by_source = {}
    incomplete = []
    for span in citations:
        source_m = DATA_SOURCE_RE.search(span)
        source = source_m.group(1) if source_m else "unknown"
        by_source[source] = by_source.get(source, 0) + 1

        # 필수 속성 체크
        attrs = {m.group(1) for m in DATA_ATTR_RE.finditer(span)}
        if source == "hyean":
            missing = HYEAN_BASE - attrs
            # 시장데이터(주가통계 PS_*/MARKET)·모델값(VAL_*/MODEL)은 DART rcp_no가 구조적으로 부재 —
            # source-anchor(dataset/as_of) 또는 formula+inputs만으로 추적성 인정
            iid_m = re.search(r'data-item-id="(PS_|MKT_|VAL_)', span)
            stmt_m = 'data-statement="MARKET"' in span or 'data-statement="MODEL"' in span
            if iid_m or stmt_m:
                missing -= {"quality"}  # 시장데이터는 다중소스 품질등급 사전이 구조적으로 없음
            has_prov = (HYEAN_PROV_ORIGINAL <= attrs) or (HYEAN_PROV_DERIVED <= attrs) \
                or ((iid_m or stmt_m) and "source-anchor" in attrs)
            if missing or not has_prov:
                detail = list(missing)
                if not has_prov:
                    detail.append("provenance:(rcp-no+source-anchor) or (formula+inputs)")
                incomplete.append({"source": source, "missing": detail})
        elif source == "web":
            missing = WEB_MUST - attrs
            if missing:
                incomplete.append({"source": source, "missing": list(missing)})
        elif source == "deep":
            missing = DEEP_MUST - attrs
            if missing:
                incomplete.append({"source": source, "missing": list(missing)})

    # FEO 라벨 밀도 — HTML 가시 본문 기준 (구 보고서.md 동등성 검사의 승계.
    # 2026-07-17 다이어트: md 산출물 폐지 → HTML 단일. 058 카나리아(약식·FEO 소실 탐지) 의도는
    # 이 검사 + check_report_quality의 가시 본문 길이 검사가 담당)
    import re as _re
    visible = _re.sub(r"<style>.*?</style>|<script>.*?</script>", "", html, flags=_re.S)
    visible = _re.sub(r"<[^>]+>", "", visible)
    feo_visible = visible.count("[F") + visible.count("[E") + visible.count("[O")
    md_penalty = 10 if feo_visible < 10 else 0

    # Citation Drawer JS 존재 체크
    has_drawer = "citation-drawer" in html or "cDrawer" in html

    # 점수 계산
    completeness = max(0, 1 - len(incomplete) / max(total, 1))
    volume_score = min(total / 30, 1.0) * 30  # 30점 (30개 이상이면 만점)
    completeness_score = completeness * 40  # 40점
    diversity_score = min(len(by_source) / 3, 1.0) * 20  # 20점 (3종 이상)
    drawer_score = 10 if has_drawer else 0  # 10점
    score = round(volume_score + completeness_score + diversity_score + drawer_score) - md_penalty
    score = max(0, score)

    return {
        "score": score,
        "grade": _grade(score),
        "total_citations": total,
        "by_source": by_source,
        "incomplete_count": len(incomplete),
        "incomplete_samples": incomplete[:5],
        "has_drawer": has_drawer,
    }


# ═══════════════════════════════════════
# 2.5 Request-Type 감지 + TYPE_RUBRICS (유형별 필수 산출 루브릭)
# ═══════════════════════════════════════
# P5(측정 정합): 현행은 다기업·스크리닝 "감점 완화"만 있고 유형 필수 산출을 검사하지 않아
# 비교·섹터 런이 구조적 저평가. 루브릭은 유형별 필수 산출을 검사해 실패 시 보고서 품질에서
# 감점, 충족 시 현행 완화를 유지한다. ★구 런(ledger에 request_type 없음)에는 페널티 미적용 —
# compare/sector/screening 페널티는 ledger request_type가 있을 때(신규 런)만, backtest는
# results.json 존재가 트리거라 구 런에 절대 오탐하지 않음 → "구 런 점수 회귀 0" 보장.

def _raw_stems(report_dir: Path) -> list:
    """00_raw 직속 + 종목별 하위폴더 json stem 목록 (하위폴더는 {폴더}_{stem})."""
    raw_dir = report_dir / "_workspace" / "00_raw"
    if not raw_dir.exists():
        return []
    stems = [f.stem for f in raw_dir.glob("*.json")]
    stems += [f"{sub.name}_{f.stem}" for sub in raw_dir.iterdir() if sub.is_dir() for f in sub.glob("*.json")]
    return stems


def detect_request_type(report_dir: Path):
    """(request_type, source) 반환. ledger request_type 우선(과제 3 기록), 없으면 파일 휴리스틱 폴백.
    source ∈ {'ledger','heuristic','none'} — 페널티는 'ledger'일 때만 적용(구 런 회귀 0)."""
    ledger = report_dir / "_workspace" / "CHECKPOINT_LEDGER.json"
    if ledger.exists():
        try:
            rt = json.loads(ledger.read_text()).get("request_type")
            if isinstance(rt, str) and rt.strip():
                return rt.strip(), "ledger"
        except Exception:
            pass
    stems = _raw_stems(report_dir)
    if sum(1 for s in stems if s.endswith("_summary")) >= 2:
        return "compare", "heuristic"   # 다기업 — 섹터일 수도 있으나 휴리스틱은 구분 불가(보고용)
    if any(s.startswith("screen") for s in stems):
        return "screening", "heuristic"
    return None, "none"


def _has(html: str, *terms) -> bool:
    return any(t in html for t in terms)


# 유형별 필수 산출 체크 — 각 predicate(html, report_dir) -> bool (True=충족). 실패 항목당 −5(최대 −15).
TYPE_RUBRICS = {
    "compare": [
        ("compare_grid_or_table", lambda h, d: "compare-grid" in h or h.lower().count("<table") >= 2),
        ("basis_label", lambda h, d: _has(h, "연결 기준", "별도 기준", "연결기준", "별도기준",
                                          "연결·별도", "연결재무", "별도재무", "결산월", "결산기")),
        ("relative_valuation", lambda h, d: _has(h, "상대가치", "상대 밸류", "상대밸류", "밸류에이션 비교",
                                                "Peer", "peer", "백분위", "percentile", "멀티플 비교")),
    ],
    "sector": [
        ("universe_defined", lambda h, d: _has(h, "유니버스", "universe", "대상 종목", "편입 종목",
                                               "구성종목", "분석 대상", "모집단")),
        ("benchmark_series_label", lambda h, d: _has(h, "한국은행", "ECOS", "커버리지", "bottom-up",
                                                     "자사 집계", "보유 기업")),
    ],
    "screening": [
        ("hygiene_filter", lambda h, d: _has(h, "위생", "이상치", "극단값", "아웃라이어", "outlier",
                                             "밸류트랩", "value trap", "배제", "정합성", "null")),
        ("recipe_mention", lambda h, d: _has(h, "레시피", "recipe", "recipes", "검증 레시피")),
    ],
}
_RUBRIC_ALIAS = {"industry_report": "sector"}  # 상세 유형 → 상위 루브릭 (deep_screening은 2026-07-20 체인으로 통합·제거)


def _backtest_rubric(report_dir: Path, html: str):
    """quant 백테스트 모드(results.json 존재) 전용 — 게이트 결과 + 한계 고지 검사. 모드 A(results 없음)는 None."""
    res = report_dir / "_workspace" / "backtest" / "results.json"
    if not res.exists():
        return None
    checks = {"results_json": True}
    try:
        gates = json.loads(res.read_text()).get("gates", {})
        checks["lookahead_zero"] = (gates.get("lookahead_violations") == 0)
    except Exception:
        checks["lookahead_zero"] = False
    checks["limitation_notice"] = _has(html, "EOD", "PIT", "point-in-time", "point in time",
                                       "KIND", "일별 종가", "공시일", "look-ahead", "생존편향", "survivorship")
    fails = sum(1 for v in checks.values() if not v)
    return {"type": "backtest", "checks": checks, "penalty": min(fails * 5, 15)}


def apply_type_rubric(report_dir: Path, html: str):
    """유형별 루브릭 평가 → {type, checks, penalty} 또는 None. penalty는 보고서 품질에서 차감."""
    bt = _backtest_rubric(report_dir, html)   # results.json 트리거 — 구 런 오탐 없음
    if bt is not None:
        return bt
    rtype, source = detect_request_type(report_dir)
    if source != "ledger":                    # 구 런/휴리스틱 = 페널티 미적용 (회귀 0 보장)
        return None
    rubric = TYPE_RUBRICS.get(_RUBRIC_ALIAS.get(rtype, rtype))
    if not rubric:                            # quant(모드 A)·single·custom 등 = 페널티 없음
        return None
    checks = {name: bool(pred(html, report_dir)) for name, pred in rubric}
    fails = sum(1 for v in checks.values() if not v)
    return {"type": _RUBRIC_ALIAS.get(rtype, rtype), "checks": checks, "penalty": min(fails * 5, 15)}


# ═══════════════════════════════════════
# 3. Report Quality (보고서 품질)
# ═══════════════════════════════════════

def check_report_quality(report_dir: Path) -> dict:
    """보고서 완성도 체크 — HTML 크기·가시 본문, 섹션 수, 컴포넌트 사용."""
    html_path = report_dir / "index.html"

    result = {
        "html_exists": html_path.exists(),
        "html_size": html_path.stat().st_size if html_path.exists() else 0,
    }

    if not html_path.exists():
        result["score"] = 0
        result["grade"] = "F"
        result["detail"] = "index.html 없음"
        return result

    html = html_path.read_text(errors="replace")

    # 섹션 수 (h2 태그)
    sections = re.findall(r"<h2[^>]*>", html, re.IGNORECASE)
    result["section_count"] = len(sections)

    # 인터랙티브 컴포넌트 사용
    components = {
        "tabs": "tab-btn" in html or "tab-panel" in html,
        "accordion": "accordion-item" in html,
        "chart": "chart-wrap" in html or "<canvas" in html,
        "ohlcv": "ohlcv-wrap" in html,
        "scenario_bar": "scenario-bar" in html or "scenario-item" in html,
        "heatmap": "heatmap" in html,
        "callout": "callout" in html,
        "timeline": "timeline" in html,
        "compare_grid": "compare-grid" in html,
        "stat_card": "stat-card" in html,
    }
    result["components_used"] = [k for k, v in components.items() if v]
    result["component_count"] = sum(1 for v in components.values() if v)

    # 테이블 수
    result["table_count"] = html.lower().count("<table")

    # F/E/O 라벨링
    result["feo_f"] = html.count('class="feo f"') + html.count("[F,") + html.count("[F]")
    result["feo_e"] = html.count('class="feo e"') + html.count("[E,") + html.count("[E]")
    result["feo_o"] = html.count('class="feo o"') + html.count("[O,") + html.count("[O]")

    # 가시 본문 길이 — 서술 절삭 카나리아 (구 md 동등성 검사 승계, 2026-07-17 md 산출물 폐지)
    visible = re.sub(r"<style>.*?</style>|<script>.*?</script>", "", html, flags=re.S)
    visible = re.sub(r"<[^>]+>", "", visible)
    result["visible_text_size"] = len(visible)

    # 점수 계산
    size_score = min(result["html_size"] / 60000, 1.0) * 25  # 25점 (60KB 이상)
    section_score = min(len(sections) / 6, 1.0) * 20  # 20점 (6섹션 이상)
    component_score = min(result["component_count"] / 4, 1.0) * 20  # 20점 (4종 이상)
    table_score = min(result["table_count"] / 5, 1.0) * 15  # 15점 (5개 이상)
    narrative_score = 10 if result["visible_text_size"] >= 15000 else 0  # 10점 (가시 본문 15KB+, 구 md_score 대체)
    feo_score = 10 if (result["feo_f"] + result["feo_e"] + result["feo_o"]) > 5 else 0  # 10점
    score = round(size_score + section_score + component_score + table_score + narrative_score + feo_score)

    # 유형별 루브릭 — 필수 산출 실패 시 감점 (backtest=results.json 트리거, 그 외 ledger request_type 시).
    # 충족 시 감점 0 → 현행 완화 유지. 구 런(휴리스틱)은 apply_type_rubric에서 None 반환 → 회귀 0.
    rubric = apply_type_rubric(report_dir, html)
    if rubric:
        result["rubric_type"] = rubric["type"]
        result["rubric_checks"] = rubric["checks"]
        result["rubric_penalty"] = rubric["penalty"]
        score = max(0, score - rubric["penalty"])

    result["score"] = score
    result["grade"] = _grade(score)
    return result


# ═══════════════════════════════════════
# 4. API Efficiency (API 활용 효율)
# ═══════════════════════════════════════

def check_api_efficiency(report_dir: Path) -> dict:
    """API 호출 효율 — summary 사용 여부, 병렬 호출, 중복 호출."""
    raw_dir = report_dir / "_workspace" / "00_raw"
    if not raw_dir.exists():
        return {"score": 0, "grade": "F", "detail": "00_raw/ 없음"}

    # 직속 + 종목별 하위폴더(00_raw/{corp}/*.json) 모두 인식
    files = [f.stem for f in raw_dir.glob("*.json")]
    files += [f"{sub.name}_{f.stem}" for sub in raw_dir.iterdir() if sub.is_dir() for f in sub.glob("*.json")]

    # summary 사용 여부 (1회 호출로 10+ 개별 호출 대체)
    has_summary = "summary" in files or any(f.endswith("_summary") for f in files)
    # 다기업 패턴: {cc}_summary.json도 summary 사용으로 인정
    multi_summaries = [f for f in files if f.endswith("_summary")]
    if multi_summaries:
        has_summary = True
    # 매크로 패턴: macro_compact 또는 ts_ECOS_ 3+ 있으면 summary 대체
    macro_files = [f for f in files if f.startswith("ts_ECOS_") or f == "macro_compact"]
    if len(macro_files) >= 3:
        has_summary = True
    # 스크리닝 패턴
    screening_files = [f for f in files if f.startswith("screening") or f.startswith("screen_")]
    if screening_files:
        has_summary = True

    has_discover = "discover" in files
    # 다기업 discover: {cc}_discover.json도 인정
    multi_discovers = [f for f in files if f.endswith("_discover")]
    if multi_discovers:
        has_discover = True

    # 개별 financials 호출 수 (summary 있으면 불필요)
    individual_fin = sum(1 for f in files if f.startswith("fin_") or f.startswith("financials"))

    # insight 호출 수
    insight_calls = sum(1 for f in files if f.startswith("insight_"))

    # 총 API 호출 수 추정
    total_calls = len(files)

    # CHECKPOINT_LEDGER 체크
    ledger_path = report_dir / "_workspace" / "CHECKPOINT_LEDGER.json"
    has_ledger = ledger_path.exists()
    ledger_data = {}
    if has_ledger:
        try:
            ledger_data = json.loads(ledger_path.read_text())
        except Exception:
            pass

    # Data Gate 상태 — 스키마 3변형 허용: dict{passed}(정본)·dict{status}(구버전)·str("PASS — 사유")
    # (RETRO 002 A-1: 에이전트가 문자열로 쓴 ledger에 .get() → AttributeError 크래시)
    data_gate = ledger_data.get("data_gate", {})
    if isinstance(data_gate, str):
        s = data_gate.strip().lower()
        gate_status = "PASS" if s.startswith("pass") else ("FAIL" if s.startswith(("fail", "stop")) else "UNKNOWN")
        missing_or_empty = []
    elif isinstance(data_gate, dict):
        if "passed" in data_gate:
            gate_status = "PASS" if data_gate.get("passed") else "FAIL"
        else:
            gate_status = data_gate.get("status", "UNKNOWN")
        missing_or_empty = data_gate.get("missing") or data_gate.get("missing_or_empty", [])
    else:
        gate_status, missing_or_empty = "UNKNOWN", []

    # Stop Triggers — 리스트(SKILL.md 스키마) 또는 딕셔너리(구버전) 모두 허용
    triggers = ledger_data.get("stop_triggers", [])
    if isinstance(triggers, dict):
        any_trigger = bool(triggers.get("data_blackout") or triggers.get("turn_overrun"))
    else:
        any_trigger = bool(triggers)

    # 점수 계산
    summary_score = 25 if has_summary else 0  # 25점 (summary 사용)
    discover_score = 15 if has_discover else 0  # 15점 (discover 먼저 호출)
    efficiency = 1.0 if has_summary else max(0, 1 - individual_fin / 10)  # summary 없이 개별 10+회 = 비효율
    efficiency_score = efficiency * 20  # 20점
    ledger_score = 15 if has_ledger else 0  # 15점 (CHECKPOINT_LEDGER 생성)
    gate_score = 15 if gate_status == "PASS" else 5 if gate_status != "UNKNOWN" else 0  # 15점
    no_trigger_score = 10 if not any_trigger else 0  # 10점
    score = round(summary_score + discover_score + efficiency_score + ledger_score + gate_score + no_trigger_score)

    return {
        "score": score,
        "grade": _grade(score),
        "has_summary": has_summary,
        "has_discover": has_discover,
        "total_api_calls": total_calls,
        "individual_fin_calls": individual_fin,
        "insight_calls": insight_calls,
        "has_ledger": has_ledger,
        "data_gate_status": gate_status,
        "missing_or_empty": missing_or_empty,
        "stop_triggers_fired": bool(any_trigger),
    }


# ═══════════════════════════════════════
# 5. Agent Design (에이전트 설계)
# ═══════════════════════════════════════

def check_agent_design(report_dir: Path) -> dict:
    """에이전트 설계 품질 — 역할 분리, references 참조."""
    agents_dir = report_dir / "agents"
    if not agents_dir.exists():
        # .claude/agents/ 폴더 체크
        agents_dir = report_dir / ".claude" / "agents"

    agents = list(agents_dir.glob("*.md")) if agents_dir.exists() else []
    agent_names = [a.stem for a in agents]

    # v3 fast-path에서 brief 스냅샷이 누락되면 ledger agents[]로 폴백 평가 —
    # 설계 자체는 이름으로 검증하되 스냅샷 부재(ref/상세 미확인)만 감점, F 아님 (RETRO 002 A-2)
    snapshot_missing = False
    if not agents:
        try:
            ledger = json.loads((report_dir / "_workspace" / "CHECKPOINT_LEDGER.json").read_text())
            agent_names = [str(a.get("name", "")).split("(")[0].strip()
                           for a in ledger.get("agents", []) if isinstance(a, dict)]
            agent_names = [n for n in agent_names if n]
        except Exception:
            agent_names = []
        if not agent_names:
            return {"score": 0, "grade": "F", "detail": "agents/ 디렉토리·ledger agents[] 모두 없음"}
        snapshot_missing = True

    # 수집 충족: 별도 data-collector 에이전트 OR 오케스트레이터 통합수집(/summary)
    # SKILL.md는 수집을 오케스트레이터 1턴(00_raw/summary.json)으로 진화시킴 → 산출물로 인정
    raw_glob = list((report_dir / "_workspace" / "00_raw").glob("*.json")) \
        + list((report_dir / "_workspace" / "00_input").glob("*.json"))
    has_collection = (
        any("data" in n and "collect" in n for n in agent_names)
        or len(raw_glob) > 0
    )
    # 분석가: analyst/analysis 외 전문가 역할명도 인정 (quality-auditor, quant-strategist 등)
    _ANALYST_KW = ("analyst", "analysis", "auditor", "strateg", "research",
                   "screen", "quant", "valuat", "fundamental", "risk")
    has_analyst = any(any(k in n for k in _ANALYST_KW) for n in agent_names)
    has_writer = any("writer" in n or "report" in n for n in agent_names)

    # references 참조 체크 (압축 ref + 다기업/외부데이터 ref 포함)
    ref_mentions = {"hyean-api-guide": 0, "report-template": 0, "design-kit": 0,
                    "analysis-framework": 0, "web-search-strategy": 0,
                    "analysis-quickcard": 0, "design-cheatsheet": 0,
                    "multi-company-framework": 0, "external-data-sources": 0,
                    "devils-advocate-guide": 0}
    for agent_file in agents:
        content = agent_file.read_text(errors="replace")
        for ref in ref_mentions:
            if ref in content:
                ref_mentions[ref] += 1

    refs_used = sum(1 for v in ref_mentions.values() if v > 0)

    # 점수 — 작업규모 맞춤: 수집+분석+작성 역할이 갖춰지면 2에이전트도 만점(고정 로스터 X)
    roles_present = has_collection + has_analyst + has_writer
    n_agents = len(agent_names)
    if n_agents >= 2 and has_writer and has_analyst:
        count_score = 25  # 역할 완비한 well-scoped 설계 (집계 인플레 보상 안 함)
    else:
        count_score = min(n_agents / 3, 1.0) * 25
    role_score = roles_present / 3 * 30  # 30점 (수집은 오케스트레이터도 인정)
    ref_score = min(refs_used / 3, 1.0) * 25  # 25점 (3종 이상 참조 — 스냅샷 없으면 검증 불가 0)
    if snapshot_missing:
        detail_score = 0  # 스냅샷 누락 = 재현성 감점 (최대 55, F 아닌 D 근방)
    else:
        detail_score = 20 if all(a.stat().st_size > 200 for a in agents) else 10  # 20점
    score = round(count_score + role_score + ref_score + detail_score)

    return {
        "score": score,
        "grade": _grade(score),
        "agent_count": n_agents,
        "snapshot_missing": snapshot_missing,
        "agent_names": agent_names,
        "has_collection": has_collection,
        "has_analyst": has_analyst,
        "has_writer": has_writer,
        "references_used": {k: v for k, v in ref_mentions.items() if v > 0},
    }


# ═══════════════════════════════════════
# 종합
# ═══════════════════════════════════════

def _grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 60: return "C"
    if score >= 40: return "D"
    return "F"


def run_quality_check(report_dir: Path) -> dict:
    """전체 품질 체크 실행."""
    name = report_dir.name

    checks = {
        "data_completeness": check_data_completeness(report_dir),
        "citation_coverage": check_citation_coverage(report_dir),
        "report_quality": check_report_quality(report_dir),
        "api_efficiency": check_api_efficiency(report_dir),
        "agent_design": check_agent_design(report_dir),
    }

    # 가중 평균 (총점 100)
    weights = {
        "data_completeness": 0.25,
        "citation_coverage": 0.25,
        "report_quality": 0.20,
        "api_efficiency": 0.15,
        "agent_design": 0.15,
    }
    total = sum(checks[k]["score"] * weights[k] for k in weights)
    total = round(total)

    return {
        "report": name,
        "total_score": total,
        "total_grade": _grade(total),
        "checks": checks,
    }


def print_report(result: dict, verbose: bool = True):
    """품질 체크 결과 출력."""
    r = result
    print(f"\n{'═' * 60}")
    print(f"  {r['report']}")
    print(f"  Total: {r['total_score']}/100 ({r['total_grade']})")
    print(f"{'═' * 60}")

    labels = {
        "data_completeness": "데이터 완전성",
        "citation_coverage": "원문 출처 추적",
        "report_quality": "보고서 품질",
        "api_efficiency": "API 활용 효율",
        "agent_design": "에이전트 설계",
    }

    for key, label in labels.items():
        c = r["checks"][key]
        bar = "█" * (c["score"] // 5) + "░" * (20 - c["score"] // 5)
        print(f"  {label:12s}  {bar} {c['score']:3d} ({c['grade']})")

    if not verbose:
        return

    print()

    # 데이터 완전성 상세
    dc = r["checks"]["data_completeness"]
    if dc.get("missing_core"):
        print(f"  ⚠ 핵심 데이터 누락: {', '.join(dc['missing_core'])}")
    if dc.get("missing_important"):
        print(f"  △ 중요 데이터 누락: {', '.join(dc['missing_important'])}")
    print(f"  ○ 총 {dc.get('total_files', 0)}개 API 응답 파일")

    # Citation 상세
    cc = r["checks"]["citation_coverage"]
    if cc.get("total_citations", 0) > 0:
        parts = [f"{k}:{v}" for k, v in cc.get("by_source", {}).items()]
        print(f"  ○ Citation {cc['total_citations']}개 ({', '.join(parts)})")
        if cc.get("incomplete_count", 0) > 0:
            print(f"  ⚠ 필수 속성 누락 {cc['incomplete_count']}개")
        if not cc.get("has_drawer"):
            print(f"  ✗ Citation Drawer JS 없음")

    # 보고서 품질 상세
    rq = r["checks"]["report_quality"]
    if rq.get("html_exists"):
        size_kb = rq["html_size"] // 1024
        print(f"  ○ HTML {size_kb}KB, {rq.get('section_count', 0)}섹션, {rq.get('table_count', 0)}테이블")
        if rq.get("components_used"):
            print(f"  ○ 컴포넌트: {', '.join(rq['components_used'])}")
        feo = rq.get("feo_f", 0) + rq.get("feo_e", 0) + rq.get("feo_o", 0)
        if feo > 0:
            print(f"  ○ F/E/O 라벨: F={rq.get('feo_f',0)} E={rq.get('feo_e',0)} O={rq.get('feo_o',0)}")
        if rq.get("rubric_type"):
            fails = [k for k, v in rq.get("rubric_checks", {}).items() if not v]
            mark = "✓" if not fails else f"⚠ 미충족 {', '.join(fails)} (−{rq.get('rubric_penalty', 0)})"
            print(f"  ○ {rq['rubric_type']} 루브릭: {mark}")

    # API 효율 상세
    ae = r["checks"]["api_efficiency"]
    if ae.get("has_summary"):
        print(f"  ✓ /summary 사용 (효율적)")
    else:
        print(f"  ⚠ /summary 미사용 — 개별 호출 {ae.get('individual_fin_calls', 0)}회")
    if ae.get("data_gate_status") != "UNKNOWN":
        print(f"  ○ Data Gate: {ae['data_gate_status']}")
    if ae.get("missing_or_empty"):
        print(f"  △ Gate 누락: {', '.join(ae['missing_or_empty'][:5])}")

    # 에이전트 상세
    ad = r["checks"]["agent_design"]
    if ad.get("agent_names"):
        print(f"  ○ 에이전트 {ad['agent_count']}개: {', '.join(ad['agent_names'])}")
    if ad.get("references_used"):
        print(f"  ○ 참조 문서: {', '.join(ad['references_used'].keys())}")

    print()


def print_summary(results: list):
    """전체 보고서 요약 테이블."""
    print(f"\n{'═' * 80}")
    print(f"  Financial Harness — Report Quality Summary ({len(results)} reports)")
    print(f"{'═' * 80}")
    print(f"  {'Report':<40s} {'Total':>5s}  {'Data':>4s} {'Cite':>4s} {'Qual':>4s} {'API':>4s} {'Agnt':>4s}")
    print(f"  {'─' * 40} {'─' * 5}  {'─' * 4} {'─' * 4} {'─' * 4} {'─' * 4} {'─' * 4}")

    for r in sorted(results, key=lambda x: -x["total_score"]):
        c = r["checks"]
        print(f"  {r['report']:<40s} {r['total_score']:>3d}{r['total_grade']:>2s}"
              f"  {c['data_completeness']['score']:>3d}{c['data_completeness']['grade']}"
              f" {c['citation_coverage']['score']:>3d}{c['citation_coverage']['grade']}"
              f" {c['report_quality']['score']:>3d}{c['report_quality']['grade']}"
              f" {c['api_efficiency']['score']:>3d}{c['api_efficiency']['grade']}"
              f" {c['agent_design']['score']:>3d}{c['agent_design']['grade']}")

    scores = [r["total_score"] for r in results]
    if scores:
        avg = sum(scores) / len(scores)
        print(f"\n  Average: {avg:.0f}/100 | Best: {max(scores)} | Worst: {min(scores)}")
        grade_dist = {}
        for r in results:
            g = r["total_grade"]
            grade_dist[g] = grade_dist.get(g, 0) + 1
        print(f"  Grades: {' '.join(f'{g}:{n}' for g, n in sorted(grade_dist.items()))}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Financial Harness Report Quality Check")
    parser.add_argument("path", help="보고서 디렉토리 또는 reports/ 상위 디렉토리")
    parser.add_argument("--summary", action="store_true", help="요약 테이블만 출력")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    target = Path(args.path)

    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    # 단일 보고서 vs 전체
    if (target / "index.html").exists() or (target / "_workspace").exists():
        # 단일 보고서
        result = run_quality_check(target)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_report(result, verbose=not args.summary)
    else:
        # 전체 보고서 디렉토리
        results = []
        for d in sorted(target.iterdir()):
            if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
                continue
            if not (d / "index.html").exists() and not (d / "_workspace").exists():
                continue
            results.append(run_quality_check(d))

        if not results:
            print(f"No reports found in {target}")
            sys.exit(1)

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.summary:
            print_summary(results)
        else:
            for r in results:
                print_report(r, verbose=True)
            print_summary(results)


if __name__ == "__main__":
    main()
