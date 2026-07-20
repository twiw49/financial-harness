# Changelog

규약: 변경 요약을 최신순으로 기록. 동작 변경은 **[BREAKING]**, 문서는 **[DOC]**, 수정은 **[FIX]**.

## v3.3.0 (2026-07-20) — 13 리포트 gap 분석 + 실제 렌더 감사 기반 스타일·추적성 근본수정

financial-harness 13 request_type을 실제 배치 실행→요청 기준(블랙박스) 기대치 대조로 gap을 찾고, 이어 13 리포트를 **Chrome 헤드리스로 실제 렌더**해 여백/패딩/마진/가독성을 시각 감사. 발견된 결함을 전부 **생성기(design-kit·cheatsheet·assemble·expand_citations)** 에서 근본수정 — 개별 리포트는 미수정, 모든 미래 리포트에 자동 적용.

- **[FIX] citation 추적성 게이트** (`expand_citations.py`) — 화면 표시값(disp)과 인용 토큰이 resolve하는 data-value가 어긋나면(드로어 클릭 시 다른 숫자) assemble 시 경고. 분기값을 TTM 토큰에·정상화값을 raw 토큰에 걸던 배선 불일치를 10의거듭제곱 정합으로 판정(단위 표기차는 통과). 5리포트 회귀 실측 17건 포착·오탐 0.
- **[NEW] 분기 단독 실적 `_Q` 인덱싱** — `summary.quarterly`의 각 항목을 `{ITEM}_Q`(예 `DRV_OP_MARGIN_Q`)로 citable하게. 분기값을 화면에 쓰고도 TTM 토큰밖에 못 걸어 표시값≠data-value가 강제되던 근본 결함 해소.
- **[NEW] assemble 인라인 `<script>` 문법 검사** (`assemble_report.py`) — `node --check`로 본문 차트 스크립트의 SyntaxError를 조립 시 포착(오타→init 실패→**빈 캔버스**가 되던 클래스, 013 weightDonut). citation 토큰은 치환해 오탐 방지·node 미설치 시 생략.
- **[FIX] callout 문장 파편화** — `.callout`의 `display:flex`(안 쓰이는 아이콘용) 제거. 문장 속 텍스트·cited 스팬이 개별 flex item으로 조각나 ~87개 callout이 세로 컬럼으로 산산조각 나던 것 → 정상 문단 흐름.
- **[FIX] verdict-hero 클래스 불일치** — 치트시트 예시가 쓰던 `.vmetric/.vlabel/.vval/.verdict-metrics`가 CSS에 미정의라 라벨/값이 붙던 것(007·013). CSS 별칭 추가 + 치트시트 예시를 정본(`.verdict-grid/.verdict-opinion/.verdict-metric/.verdict-label/.verdict-value`)으로 교체.
- **[FIX] timeline·heatmap 클래스 배선** — `.tl-*`↔`.timeline-*` 듀얼셀렉터, heatmap grid를 `div.heatmap`로 스코프+`.heatmap.X` 표셀 색(td 왜곡·색 미적용 해소).
- **[FIX] 반응형·가독성** — 모바일 wide 테이블 가로 스크롤(`@media table`), theme-toggle이 좁은 폭서 h1 가림(→h1 우측 여백), muted 캡션 대비 상향(`--text3`), kpi-grid 고정4열 trailing 빈칸(→auto-fit), next-actions 박스 상단 여백(→first-child margin 리셋), feo-badge 경량화.
- **[NEW] 시각화 프리미티브** — football-field/밸류에이션 레인지(현재가·목표가 마커, PER/PBR 밴드 겸용)·value-chain 다이어그램(산업 가치사슬). scatter·상관히트맵·이중축·스택 워크드 예시도 cheatsheet 추가.
- **[DOC] cheatsheet** — 표시값=data-value 정합 규칙(분기 `_Q`·재계산값 `{{e}}`)·유형별 밀도 가이드(scaffold-bleed 방지)·결론(열거형) 카드/리스트 구조 예시·FEO 배지 간결 가이드.
- 서버 플랜 배선(별도 hyean 리포): single_stock 배당·듀폰, watchlist 수급(웹), screening market 필터, quant 섹터/규모 노출.

## v3.2.0 (2026-07-18) — forward_vintage 패널 소비 (forward 팩터 백테스트의 유일한 합법 입구)

백테스트 스캐폴드가 신규 `forward_vintage.parquet`(datasets 6번째)을 소비 — **forward 팩터를 모드 B에서 look-ahead 없이 검증하는 유일한 합법 경로**. 패널의 **행 자체가 vintage**라(anchor_date = 그 값이 알려진 시점: A=연간보고서 제출일·P=잠정공시일·E=업종평균 공표일) known_from/법정 lag 판정이 불필요하다. `scripts/backtest_scaffold.py`만 변경. factor_zoo 경로·기존 게이트는 전부 무변경(회귀 결과 byte-동일, 신규 키 1개만 추가).

- **[NEW] config `signals[].source`** — `"factor_zoo"`(기본, 종전 동작 무변경) · `"forward_vintage"` 신설. 미지 source는 명확한 에러.
- **[NEW] forward_vintage 시그널 판정** — item_id `FWD_EPS_ENS`(권장 기본)·`FWD_EPS_B/T/R/S` → 각 `fwd_eps_*` 컬럼. 리밸런스일 t에 `anchor_date ≤ t` 중 **최신 anchor_date 행**(동률이면 최신 target_fy) 값 채택(consol 필터). 값 NULL이면 그 시그널 없음 처리(선택된 최신 anchor 기준 — 더 과거 앵커로 폴백 안 함). known_ts=anchor_date라 기존 look-ahead 자기검증(`known > t0`)이 곧 "`anchor_date > t` 채택 없음" 검증이 되어 `lookahead_violations`에 합산.
- **[NEW] `gates.forward_vintage_cells`** — 채택된 vintage 셀 수. 기존 게이트 필드·factor_zoo 경로 로직은 전부 무변경(`anchor_coverage_pct`는 factor_zoo known_from 비율 그대로 — vintage 셀 미포함). `forward_signal_rows_dropped`(factor_zoo forward 행 드롭)도 유지 — **vintage 경로만이 forward의 합법 입구**.
- **[NEW] 데이터 로드·에러** — `00_raw/datasets/forward_vintage.parquet` 로드. forward_vintage 시그널이 있는데 파일 부재 시 명확한 에러(+25cr 다운로드 안내). 미지 item_id·미지 source·consol 미스매치도 명확한 에러.
- **[COMPAT] factor_zoo 전용 런 무변경** — `source` 미지정 config는 종전과 byte-동일 결과(회귀 픽스처 diff-0, 추가는 `forward_vintage_cells: 0` 키 뿐). factor_zoo 시그널이 없는 순수 vintage 런은 factor_zoo 다운로드 불필요.
- **[검증]** 실물 forward_vintage.parquet(15,493행) + 합성 가격/유니버스 E2E(vintage=4,005·lookahead=0)·회귀 diff-0·혼합 런(known_from=4,005·vintage=4,005 동시 집계·forward_dropped=45)·선택 로직 유닛(최신 anchor·tie-break·NULL-latest 드롭·future-anchor 필터·consol 필터) 전부 통과.

## v3.1.3 (2026-07-18) — 백테스트 known-시점 2단계 간소화 + 정정 리스크셋 restatement_events 전환 (pit 의존 소멸)

known-시점 판정에서 **② pit original 앵커를 삭제**해 ①`known_from` → ③법정 lag **2단계**로 축소하고, 정정 리스크셋 소스를 pit `generation='restated'`에서 `restatement_events.parquet`으로 전환. 데이터 의존이 `pit_universe_snapshot`을 잃어 **factor_zoo·survivorship_free·restatement_events·prices 4종**으로 정리(look-ahead 판정에 pit 불필요 → 모드 B 기본 다운로드 25cr 절감). `scripts/backtest_scaffold.py`만 변경.

- **[BREAKING] known-시점 2단계 판정** — ① 팩터 행 `known_from`(1순위) → ③ 부재/null 셀만 period_type 법정 lag. 종전(v3.1.2)의 ② pit original 앵커 제거. 근거(실측): `known_from`이 annual 97.5%·ttm 99.9%·quarterly 99.7%를 커버하고, `known_from` null 셀(=collect.reports에 원본 부재)은 같은 원천의 pit에도 대부분 부재 → ②의 실질 기여 ≈ 0. **③ 유지 근거**: 잔여 null 셀을 드롭하면 보고서 미수집 기업(상폐 계열 편중)이 조용히 빠져 생존편향이 뒷문으로 재유입 — 보수적 lag가 정직.
- **[BREAKING] 정정 리스크셋 = restatement_events.parquet** — `restated_value_risk_cells`의 소스를 pit `generation='restated'`에서 `restatement_events`(전 행이 non-original 정정 이벤트 — value_change/preliminary/restatement/sign_only, 'original' revision_type 부재)의 corp×period_end 집합으로 전환. **교차확인(실물 datasets)**: pit-restated (corp,pe) 집합 10,736이 restatement_events 집합 66,513의 **완전 부분집합**(누락 0) — v3.1.3은 v3.1.2 리스크 셀을 하나도 잃지 않으면서 더 보수적(over-flag = 안전 방향). 차이 55,777은 value_change/sign_only 재제출 정정 + preliminary(pit이 별도 세대로 분리하던 것).
- **[BREAKING] 구버전 8컬럼 factor_zoo 지원 종료** — `known_from` 컬럼 부재 시 침묵 하위호환 대신 **경고(stderr) + 전량 ③ 법정 lag 처리** + 재다운로드 안내. ② 폴백 경로가 사라져 known-시점이 전량 보수적 lag가 됨을 명시(침묵 금지).
- **[COMPAT] gates 필드명 전부 유지** — `known_from_cells`(①)·`fallback_lag_cells`(③)·`anchor_coverage_pct`(분자=① `known_from`)·`restated_value_risk_cells`(restatement_events 기준)·`lookahead_violations`(=0 의무)·`forward_signal_rows_dropped`. 제거는 ② 내부 카운터(`anchor_cells`)·pit 로드/앵커 코드·콘솔 출력의 `anchor=` 토큰뿐.
- forward 드롭(`period_type=='forward'`)·정정 리스크 게이트(`exclude_restated`)·상폐 청산·look-ahead 자기검증(=0) 유지. config 스키마·results.json 게이트 키 불변.
- **[검수 보강] restated 게이트 null semantics** — `restatement_events` 미제공 런(+25cr 패널 미다운로드, 기본 50cr 플로우)은 `restated_value_risk_cells`/`restated_cells_excluded`를 **null(측정 안 함)**로 기록 + stderr 경고. 0("리스크 없음")과의 오독 차단 — 픽스처 2종(유/무) 재검증, lookahead=0.

## v3.1.2 (2026-07-18) — 백테스트 known_from 컬럼 1순위 소비 (factor_zoo v2)

파이프라인 근본수정 반영: `factor_zoo.parquet`에 `known_from`(원본 정기보고서 제출일, string 'YYYY-MM-DD'/null) 컬럼 내장(실측 커버리지 annual 97.5%·ttm 99.9%·quarterly 99.7%·forward=의도적 NULL). `scripts/backtest_scaffold.py`만 변경.

- **[FIX] known-시점 3단계 판정** — ① 팩터 행 `known_from` 컬럼(non-null이면 그 날짜, **1순위**) ② 부재/null이면 pit `original` 앵커 ③ 둘 다 없으면 period_type 법정 lag. 종전(v3.1.1)은 ②③만 — 겹침 1종(DRV_DPS)이라 폴백 지배적이던 것을 팩터 내장 제출일로 해소.
- **[COMPAT] 구버전 8컬럼 parquet 하위호환** — `known_from` 컬럼 존재 여부로 분기(`has_kf`). 컬럼 없으면 종전 ②/③ 경로로 동일 동작(known_from_cells=0).
- **[NEW] `gates.known_from_cells`** — ①로 판정된 셀 수. `anchor_coverage_pct` 분자를 **①+②**(실제 날짜 앵커) 합으로 갱신 — ①/②/③ 구성이 보이도록. 기존 `lookahead_violations`(=0 의무)·`fallback_lag_cells`(=③) 필드명 유지.
- forward 드롭(`period_type=='forward'`, `known_from` NULL이어도 1차 방어)·정정 리스크 게이트(`exclude_restated`)·look-ahead 자기검증(=0) 유지.

## v3.1.1 (2026-07-18) — 백테스트 PIT 앵커 정밀화 (제출일 앵커·법정 lag·정정 리스크·forward 금지)

`scripts/backtest_scaffold.py`만 변경. 근거 실측: pit↔factor_zoo canonical 겹침이 1종(DRV_DPS)뿐이라 종전 90d 단일 폴백이 지배적 → known-시점 판정을 "원본 제출일 앵커"로 교체.

- **[FIX] 원본 제출일 앵커** — 팩터 셀 known-시점 = ① pit `generation=='original'`의 `(corp,period_end)→min(as_of_from)` 앵커 ② 부재 시 period_type별 법정 lag 폴백(annual 90 · quarterly/ttm/declared 45 · 미지 90). ★`preliminary` 세대는 앵커로 쓰지 않는다(잠정값≠최종 팩터 입력 — 이른 날짜 차용=미세 look-ahead). 종전 `as_of_until` 윈도우 판정 대체.
- **[NEW] 정정 리스크 게이트** — pit `generation=='restated'`가 존재하는 `(corp,period_end)`를 리스크셋으로. 백테스트에 실제 사용된 팩터 셀 중 리스크 셀 수를 `gates.restated_value_risk_cells`로 카운트(factor_zoo=최신 세대 값이라 정정 기간을 원본 제출일에 쓰면 미세 누출 — 정직 고지). config `exclude_restated`(기본 `false`) `true`면 해당 셀 드롭 + `gates.restated_cells_excluded`.
- **[NEW] forward 팩터 금지** — factor_zoo `period_type=='forward'`(모델 최신 산출=vintage 아님) 전량 드롭 + `gates.forward_signal_rows_dropped`. 드롭 후 signal 행 0이면 하드 에러로 중단.
- **[NEW] gates** — `anchor_coverage_pct`(앵커/(앵커+폴백)) 추가. 기존 `lookahead_violations`(=0 의무)·`fallback_lag_cells` 필드명 유지.

## v3.1.0 (2026-07-18) — 5 카테고리 라우팅 정합 + 백테스트 로컬 실행 계층(Lv1)

설계 SSOT: hyean `docs/HARNESS_WORKAREAS_20260718.md` (5축 전수조사 — 단일/비교/섹터/스크리닝/백테스트). 로더·스크립트만 변경, 서버 방법론(`mcp_content`)·API는 hyean 리포.

- **[DOC] 요청 분류 결정표 (SKILL §2.3 신설)** — 44행 라우팅 힌트 3줄을 13종 판별 결정표로 확장(요청 신호 + 모호 시 판별 질문). `quant`는 "성과 통계=모드 A / 규칙·기간·리밸런스 명시=모드 B(백테스트)" 구분 명시.
- **[DOC] 체인 런 규정 (SKILL §2.3)** — 복합 요청("찾아서 비교"·"스크리닝 후 심층")은 선행 유형으로 런 시작 → 같은 RUN_DIR + `get_plan(다음 유형)` 재호출 + `00_raw` 재사용(동일 엔드포인트 재호출 금지) → 최종 index.html 1개, `log_run`/finalize는 최종 유형 1회(`agents`에 `chain:유형1>유형2`).
- **[NEW] `scripts/backtest_scaffold.py`** — 로컬 규칙 백테스트 실행기(pandas+pyarrow, 네트워크 0). `/datasets`(factor_zoo·pit_universe_snapshot·survivorship_free) + `/prices/bulk` 무가공 저장본을 읽어 **PIT look-ahead 게이트**(as_of_from ≤ 리밸런스일 < as_of_until, 미매칭 셀은 period_end+90일 보수 폴백)·분위 포트·비용 민감도(0/30/60bp)·상폐 청산(마지막 adj_close, −100% 강제 금지)·연도별 분해를 `results.json`+`timeseries.csv`로 산출. 서버는 백테스트를 실행하지 않는다(PRODUCT 정직고지 ②) — 실행 주체=로컬 하네스.
- **[NEW] 유형별 채점 루브릭 (`report_quality_check.py` TYPE_RUBRICS)** — compare(basis 표기·compare-grid·상대밸류)·sector(유니버스 정의·벤치마크 계열 라벨)·screening(위생 필터·레시피 언급)·backtest(게이트 4종·한계 고지·results.json) 필수 산출을 검사, 실패 시 보고서 품질 감점(항목당 −5, 최대 −15)·충족 시 현행 완화 유지(P5 측정 정합). **유형 감지=ledger `request_type` 우선, 없으면 파일 휴리스틱 폴백.** ★compare/sector/screening 페널티는 ledger request_type 있을 때만·backtest는 results.json 트리거라 **구 런 점수 회귀 0**(harness-dev 69런 전수 무회귀·크래시 0 실측).
- **[NEW] ledger `request_type` 기록 (`finalize_run.sh --request-type <type>`)** — 채점기 유형 감지의 정본. 인자 없으면 현행과 동일(하위호환).
- **[DOC] §0 백테스트 경계 갱신** — "자유 백테스트 미지원" → "**서버 실행** 미지원 — `quant` 유형이 `/datasets` 다운로드 + 로컬 실행(`backtest_scaffold.py`)으로 지원". STOP 게이트가 백테스트 요청을 차단하지 않도록(quant 라우팅).
- **[DOC] design-cheatsheet 비교 4섹션 순서** — 비교표(basis 표기)→각사 재무→상대 밸류에이션→의견.

## v3.0.6 (2026-07-17) — 공개 릴리스: MIT LICENSE + 히스토리 리셋

- **리포 public 전환** — v3 얇은 로더는 공개 배포 대상 (방법론·데이터는 Hyean MCP 서버가 OAuth·크레딧 뒤에서 서빙).
- **[DOC] MIT LICENSE 추가** — 로더·스크립트·design-kit에 한함. 서버 제공 콘텐츠는 hyean.io 약관.
- **히스토리 v3 기준 재시작** — v2 시절 커밋·태그는 공개 리포에서 제거 (전체 이력은 private 아카이브 보존). v2 클론은 `git pull` 불가 → README 재클론 안내.

## v3.0.5 (2026-07-17) — 가독성 개선: 한국어 keep-all·컨테이너 1100px·타이포 확대

- **[FIX] 글자 단위 줄바꿈** — `word-break: keep-all` 부재로 좁은 그리드/셀에서 "범위"→"범/위"로 꺾임 → body에 keep-all + overflow-wrap 폴백.
- **컨테이너 920→1100px, 본문 14→15px(1.75), h2 26px·h3 18px·표 14px** — 세로 스크롤 문서가 와이드 화면 공간을 여유롭게 쓰도록.
- **verdict-grid 고정 4열 → auto-fit minmax(170px)** — 열당 ~160px에서 지표가 파편화되던 것, 부족하면 줄바꿈.
- **[DOC] cheatsheet**: 경고·주의 문장을 표 셀로 쪼개지 말고 callout 한 단락으로 (002 "밸류에이션 기준가 주의" 파편화 사례).
- 기존 산출물 002 동일 패치, manifest kit_sha256 갱신.

## v3.0.4 (2026-07-17) — 보고서 가운데 정렬 수정 (와이드 화면 우측 쏠림)

- **[FIX] design-kit `.report-container` 우측 쏠림** — `@media(min-width:1200px)`의 고정 `margin-right: 240px`(우측 고정 TOC 자리)가 `margin: 0 auto`의 우측 auto를 덮어써 잔여 공간이 전부 좌측 여백으로 몰림(2000px 화면에서 좌측 840px — v2 시절부터 전 보고서 반복). → `margin-right: max(calc((100% - 920px)/2), 240px)`: 와이드에선 완전 중앙, TOC와 겹치는 1200~1400px에서만 좌측으로 비켜남. 기존 산출물 39건(test 2 + harness-dev 37) 일괄 패치, manifest kit_sha256 갱신.

## v3.0.3 (2026-07-17) — harness-review(002): 채점 팬텀 인용 제거

- **[FIX] 팬텀 인용 2건** — design-kit이 `<style>`/`<script>` 주석에 담은 예시 마크업(`data-source="hyean/web/deep/..."`)이 매 런 인용 수·소스 다양성 점수에 집계 → 본문만 스캔.

## v3.0.2 (2026-07-17) — 002 실런 회고(RETRO) 반영: 채점 크래시·인용 합성·스냅샷 규약

002_삼성전자 실런 회고의 하네스 측 이슈 일괄 수정 (서버 측 mcp_content·API는 hyean 리포).

- **[FIX] 채점기 크래시 + finalize 은폐 (A-1)** — `data_gate`가 문자열이면 `.get()` AttributeError → str/dict{passed}/dict{status} 3변형 허용. finalize의 `| grep` 파이프가 채점 크래시를 무음 통과시키던 것 → exit code·traceback 노출로 loud-fail.
- **[FIX] insight 오탐 (C-1)** — 채점기가 파일명(`insight_mda.json`)만 탐색해 통합 `insight.json`(items[].category) 수집을 "누락"으로 오탐 → 내용 기반 인식 추가.
- **[FIX] 에이전트 스냅샷 (A-2)** — SKILL §2.3 brief Write를 fast-path 포함 의무로 격상. 채점기는 스냅샷 부재 시 ledger agents[]로 폴백 평가(F→D, 재현성 감점만).
- **[FIX] PS_ 주가통계 토큰 전건 미해결 (C-2)** — 합성 레코드가 as_of 날짜로 키가 잡혀 writer가 매칭 불가 → PS_/MKT_/VAL_는 기간 무관 매칭 폴백.
- **[NEW] 밸류에이션 모델값 인용 (C-3)** — valuation.json에서 `VAL_{METHOD}`·`VAL_RANGE_*`·`VAL_SCENARIO_*`·`VAL_FWD_EPS_*` 자동 합성 (27종, formula+inputs 추적) — 적정가가 원문 링크 없는 estimate span으로 열화되던 갭 해소. 채점기 data-statement="MODEL" 면제 클래스 추가.
- **[DOC] 서브에이전트 md 산출물 = heredoc-first (D-1)** — 플랫폼이 보고서형 md Write를 차단("return findings as text") → Write 시도·차단·재시도 마찰 제거 (cheatsheet·서버 brief 22종 동기).
- **[DOC] 동일 대상·동일 날짜 중복 런 확인 (D-2)** — SKILL §2.2 런 격리에 재사용 확인 1줄.

## v3.0.1 (2026-07-17) — 보고서 품질 회귀 수정 (report-template 배선 누락)

첫 v3 실런(삼성전자)에서 v2 대비 품질 전면 후퇴: 섹션 14→5(리스크·KAM·부문·시그널 등 선택 섹션 전멸), 라이브 차트 4→1(OHLCV 빈 canvas), Hyean 수치 125건이 원문 링크 없는 수기 `estimate` span으로 열화. **근본 원인 = v3.0.0이 로컬 `references/report-template.md`(46KB — 선택 섹션 11종 판단기준·필수 컴포넌트·citation 상세)를 제거했는데 report-writer brief는 여전히 로컬 경로를 참조 → Read "File does not exist"를 무시하고 강행.** 다이어트(v2.8.0)는 원인 아님(references 전부 보존했음).

- **[FIX] design-cheatsheet OHLCV 차트** — "design-kit 패턴 참조" 한 줄 → 실제 인라인 init 예시 코드로 교체 (canvas만 만들고 스크립트 누락 → 빈 박스 방지).
- **[FIX] (서버 mcp_content)** report-writer brief 참조를 `get_reference("report-template")` **필수 선행 + 실패 시 중단·보고**로 재배선. plans/_base.md §E 조립기 워크플로우 동기화. _validation.md에 회귀 가드 3종(선택 섹션 판단 수행·죽은 canvas 0·수기 estimate 위장 span 0).

## v3.0.0 (2026-07-17) — MCP 완전 이전: 얇은 로더 + 원격 방법론 서빙 + OAuth 2.1

롤백 앵커: 태그 `v2-final-clone`. 설계·서버 구현: hyean 모노레포 `hyean-api/server/mcpsrv/` + `server/mcp_content/`.

- **[BREAKING] 방법론 서버 이관** — `agents/`(31종)·`references/`(방법론 9종)·`workflows/`(2종)·SKILL §1~§9 판단규약을 Hyean MCP 서버(`get_plan`/`get_reference`)로 이전. v2.8.0 다이어트(fast-path·T1~T6·md 폐지·검증캡 1)는 서버 콘텐츠에 흡수됨. 로더 잔류 = SKILL.md(로더)·scripts/·design-kit·design-cheatsheet.
- **[BREAKING] 인증 OAuth 2.1** — `.env` 평문 `HYEAN_API_KEY` 폐지. `claude mcp add --transport http hyean https://api.hyean.io/mcp` + 브라우저 로그인. 데이터 호출은 bash curl → `mcp__hyean__call_api(_batch)` (응답 무가공 저장 계약으로 citation 파이프라인 유지). CI는 `--header` raw 키 폴백.
- **[BREAKING] settings.template.json** — `Bash(curl/source)` 제거, `mcp__hyean__*` allowlist + `MAX_MCP_OUTPUT_TOKENS=60000` (대용량 응답 절단 방지).
- finalize_run.sh: 에이전트 스냅샷 소스 = `reports/NNN/agents/`(로더가 get_plan 시 Write) — 스킬 라이브러리 복사는 v2 폴백.
- harness-references/(하네스 제작 메타 7종)는 서비스 저장소 `docs/harness-references/`로 이동 (제품 배포 대상 아님).

## v2.8.0 (2026-07-17) — 다이어트: HTML 단일 산출물 + 필수 턴 시퀀스 (런 15~50% 단축)

근거 실측·설계 SSOT: hyean `docs/HARNESS_DIET_20260717.md` (reports/064~069 6런 단계별 타이밍).

- **[BREAKING] 보고서.md 산출물 폐지 — writer는 index.html 단일 산출물** — md 소비자는 채점 1곳뿐(서비스 표면·회고 전부 HTML만 사용)인데 이중 집필이 writer 최대 병목(6.9~17.3분 중 −2~5분). 058 절삭 카나리아 의도는 채점의 HTML 가시 본문 검사(FEO 밀도 + `visible_text_size` 15KB+)가 승계. `report_quality_check.py`: md 페널티(−15/−10)·`md_score` 제거 — **구버전 채점으로 신규 런을 채점하면 부당 감점되니 채점은 반드시 v2.8.0+ 사용**.
- **[BREAKING] 실행 순서를 필수 턴 시퀀스 T1~T6으로 격상** — DA 발동 시 [DA ∥ writer(비밸류 FILL)] **한 메시지 동시 발사 의무** (068 직렬 21분=전체 47%, 069 재발 실측 — 산문 규정이 반복 누락). scaffolder ∥ analyst 전 런 유형 명시. 검증층(DA·reconcile·Validation)은 유지 — 발동 런 3/3에서 실질 교정(067 thesis 3건 파기·069 적정가 −49%→−35%)이라 제거 대신 병렬 은폐(잔여 비용 ~3분).
- **[BREAKING] Validation 수정 라운드 캡 3→1** — writer self-check(068 후 도입)가 1차 방어. 남는 이슈는 한계 고지+사용자 보고 (재작업 루프 금지).
- **표준 유형 fast-path** — 표준 요청은 에이전트 템플릿 직채택이 기본값, 즉석 설계·Judge Panel(§1.5)은 비표준·복합만 (−1~2분).
- writer self-check에 `SELF-CHECK: PASS(3/3)` 선언 의무 추가. design-cheatsheet 워크플로우에서 md 작성 스텝·writer의 QC 실행 스텝 제거(후자는 SKILL "writer 1-pass" 규정과 모순이었음).

## v2.7.1 (2026-07-10) — governance member 라벨 canonical화

- **[BREAKING] `/shareholders`·`/treasury-holdings` member 라벨 표준화** — `관계`/`주식종류`/`취득방법` 값이 레벨보존 canonical로 통일됨(예: `계열사임원`·`계열회사임원`·`관계사임원`→`계열회사 임원`, `보통주식`·`의결권 있는 주식`→`보통주`, `기타 취득(c)`→`기타 취득`; 관계 계열 ~92K행). 라벨 문자열을 exact 매칭하던 클라이언트는 canonical 기준으로 갱신할 것. 표기변형으로 갈라졌던 궤적(dim 그룹)이 병합되어 시계열 연속성은 **개선**됨.

## v2.7.0 (2026-07-07) — API 전면 커버리지 (gap 배선)

- **[DOC] data-collector 조건부 심화 수집 규칙** — 정정 이력(`/revisions`·`/metric-revisions`, meta_state.confidence=revised 트리거), 시장조치(`/market-status`, risk_level high/critical 트리거), 자본구조·부외(`/debt-maturity`·`/convertibles`·`/guarantees`·`/derivatives`·`/fx-exposure`·`/sensitivity`), 거버넌스 5종, 배당(`/dividend-declared`·`/dividend-disclosures`).
- **[DOC] risk-analyst 부외·환·희석 리스크 수행 항목** — market_status/revisions/capital 상세 파일 소비 + 수집 갭 보고 규칙.
- **[DOC] quality-auditor 정정 이력 검증 수행 항목** — revisions.json으로 정정 전→후 실증, meta_state.confidence 정합 확인.
- **[DOC] screener `signal_survival`(시그널 IC·verdict 측정원장) + `/verified-consensus`(VCS 랭킹) 활용** 추가.
- **[DOC] segment-analyst L3 `/business-tables` ground truth 규칙**, dividend-analyst 확정배당 우선 규칙, macro-collector `/macro/glossary` 각주 활용.
- **[DOC] hyean-api-guide §15~17 신설** — 정정 이력&PIT / 자본·거버넌스 상세(트리거 표) / 시장조치·VCS·base-rates·용어사전·공시 리스트.
- **[DOC] api-reference.generated.md 재생성** — 신규 `/companies/{cc}/market-status`(1cr)·`/macro/glossary`(1cr), `/forward`의 `consensus_agreement`, `/screener/columns`의 `signal_survival` 반영.

## v2.6.0 (2026-06-19) — 상태 엔진 소비 (state engine Layer 5/6)

- **[DOC] data-collector `state.json` 수집** — `/companies/{CC}/state`(결정론 상태 엔진) 호출세트 추가. signals(지표 평면) 위에 *서사*: `states`(5축+composite_label 현재 국면)·`trajectory`(as_of 펀더 상태 시계열+전이, look-ahead 0)·`market_gap`(★state_gap 펀더↔시장 괴리: 양수=괴리기회·음수=선반영, gap_trend, fair_upside 교차확인)·`transition_drivers`(전이 유발 공시, 연결만). INDEX.md 다이제스트에 상태 엔진 요약 포함.
- **[DOC] financial-analyst 상태 엔진 국면 보강** — `state.json`으로 국면을 *시점·전이·시장괴리* 축으로 진단. composite_label로 국면 확정·transition+drivers로 전환점 서사화·**market_gap의 state_gap을 밸류에이션 괴리 자가검증(C-3-lite)에 직결**(valuation market_implied/expectation_risk와 합치/상충 규명). 라벨 `[Hyean 상태엔진, 결정론]`.
- **[DOC] hyean-api-guide `/state` 섹션 신설** — 5축 상태·trajectory·market_gap·transition_drivers 해석 전략 + screener state 컬럼(op_state/state_composite/state_gap/gap_label) 필터 활용.
- **[DOC] api-reference.generated.md 재생성** — `/companies/{cc}/state` 등 반영.

## v2.5.0 (2026-06-11) — 기업 상태 시그널 소비 (Screener)

- **[DOC] data-collector `signals.json` 수집** — `/companies/{CC}/signals`(원시 수치가 아닌 종합 시그널 ~60개 + `fired` 발화 리스트) 호출세트 추가. INDEX.md 다이제스트에 상태 시그널 요약 포함.
- **[DOC] report-template "상태 & 시그널" 선택 섹션** — `fired`를 헤드라인으로, streak⊕divergence⊕inflection으로 현재 국면(확장/과열/둔화/회복/부실) 진단 + 업종 상대순위 + 리스크 플래그. 모순 강조(외형성장 vs 이익질)가 핵심.
- **[DOC] financial-analyst 상태 시그널 국면 진단** — `signals.json` 기반, divergence로 외형성장의 질 검증, NULL=미보유 단정 금지, `[E 추정, Hyean 시그널]` 라벨.
- **[DOC] screener 에이전트 `/screener` 시그널 조건 스크리닝** — generic filter(col:op:val) + `/screener/columns`(70컬럼) 메타. 순수 forward 리더보드는 `/screening` 유지.
- **[DOC] api-reference.generated.md 재생성** — `/screener`·`/screener/columns`·`/companies/{cc}/signals` 신규 반영.

## v2.4.2 (2026-06-11) — 주석 citation·신규 테마 2종·만기 ladder·세그먼트 YoY

- **[DOC] data-collector 주석 수집 가이드 확장** — (1) 테마 응답의 원문 citation(rcp_no/source_url/report_url)·`sign_warning` 안내, (2) 추가 테마 2종 `related_party`(특수관계자 — 내부거래·KMP 보상)·`share_based_payment`(주식보상 — 희석 위험), (3) 고부채 기업 `/notes/maturity` 만기 ladder 수집, (4) 세그먼트는 `?full_year_only=true`+`yoy_pct`로 분기 오라벨 자동 회피. 근거: hyean-api 2026-06-11 원문추적 복구(api.notes_values denormalize)+신규 엔드포인트.
- **[DOC] financial-analyst 주석 depth 확장** — 만기절벽(12개월 내 도래 비중) 평가, related_party 테마⊕insight_related_party 텍스트 교차(거버넌스), `DRV_SEGMENT_HHI`(부문 집중도) 활용, 주석 수치 인용 시 rcp_no/report_url 출처 기록.
- **[DOC] api-reference.generated.md 재생성** — `/notes/maturity` 신규 + `/notes`·`/segments` 파라미터 반영.

## v2.4.1 (2026-06-11) — 주석 narrative insight 카테고리 수집

- **[DOC] data-collector insight 수집에 `insight_accounting`·`insight_related_party` 추가** — 신규 주석 narrative 카테고리(회계정책·핵심추정 / 특수관계자 거래, 별도 세션이 insight 파이프라인에 신설). data-collector의 `insight-context?category=...`에 2건 추가(파이프라인 재추출 전엔 빈값 = forward-compatible).
- **[DOC] financial-analyst 임무에 주석 narrative 활용 추가** — 회계정책 변경(전년 대비 수익인식·감가연수 변경 = "이익의 질" 적신호 → accruals 숫자와 교차), 특수관계자 거래 성격/조건(지배구조 리스크)을 분석에 반영, [F 공시]로 인용. hyean-api `DRV_EFFECTIVE_TAX_RATE`(유효세율) + 주석 텍스트의 "숫자+서술" 결합 분석 지향.

## v2.4.0 (2026-06-10) — 주석(notes) depth 기본 수집 승격

- **[FEAT] notes 테마 묶음을 data-collector 기본 수집으로 승격** — 그간 "필요 시"로 휴면이던 주석 depth(본표 BS/IS/CF에 안 드러나는 비용구조·리스·부문)를 단일종목 표준 수집에 포함. data-collector 병렬 호출 세트에 `/notes/themes`(카탈로그)+`/notes/themes/expense_by_nature`(인건비·감가·R&D)+`/notes/themes/lease`(IFRS16 레버리지) 3종 추가(`notes_themes.json`·`notes_expense.json`·`notes_lease.json`). 각 테마는 무차원 총계·(element·기간) dedup된 깔끔한 시계열이라 그대로 시계열화 가능. 더 필요 시 `borrowings`/`finance_income_cost`/`pension`/`segments` 가이드 추가 호출. 근거: hyean-api `/notes` 정제(period_start 노출·min_confidence·aggregate_only·dimensions_clean) + 신규 테마 번들 엔드포인트로 element_id 선지식 없이 묶음 조회 가능해짐(API 측 P0~P2 완료).
- **[DOC] 보고서에 "부문·비용구조" 분석 계약 추가** — report-template 선택섹션 + 실행 계약(비용구조=매출대비%·추세, 리스=실질 레버리지, 부문=연결 reconciliation 오차% 게이트·full-year 한정). financial-analyst 임무 2에 주석 depth 분석 1줄. 수집만 하고 분석 안 하던 공백 차단.
- **[DOC] hyean-api-guide notes 섹션 갱신** — 신규 파라미터(period_start 응답·min_confidence·aggregate_only·dimensions_clean) + 테마 번들 2엔드포인트(`/notes/themes`·`/notes/themes/{theme}`) + 크레딧 추정 갱신(포괄 26→35, 전체 35→41). api-reference.generated.md 재생성으로 신규 엔드포인트 반영.

## v2.3.0 (2026-06-10) — 스킬 층 첫 발화 (watchlist-brief 워크플로우)

- **[FEAT] `workflows/watchlist-brief.md` 신규 — 비어 있던 워크플로우 디렉토리의 첫 실제 스킬.** §1.4 "확장 자유 조항"의 스킬-생성 능력이 68런 동안 휴면이던 것을 실제로 발화. watchlist N종목의 "지난 브리핑 이후 무엇이 바뀌었나"를 delta로만 추려 짧은 다이제스트로 내는 **별도 작업 패밀리**(상태유지·반복·breadth-경량) — §1~§9 보고서 런(depth·1회)이 구조적으로 담지 못하는 *형태*. 상태(`watchlist/{listname}/_state.json`)는 스킬 폴더 밖 프로젝트 디렉토리에 둠(v2.2.0 read-only 원칙 준수). 실제 엔드포인트 사용: `summary?include=anomalies,price_stats`·`events?after=&category=`. 반복 발사는 Claude Code `loop`/`schedule`(cron)이 담당.
  - 의의: financial-harness의 적응성이 **두 축**임을 명확화 — 에이전트 층(상시, *내용* 변동 흡수) + 워크플로우 층(이제 1종, *형태* 변동 흡수). "동적 스킬 생성"이 주장→실증으로 전환.
- **[DOC] 자기소개 정직화** — 6개 표면 정직성 감사 후 README(인트로·"어떻게 작동하나요?" §2·디렉토리설명) + SKILL §1.4 헤드라인의 "에이전트와 스킬을 동적 생성" 과장을 실제대로 정정. 분석 방법론은 `references/`에 정적으로 있고 에이전트가 *읽는* 것(런마다 생성 X), 스킬(워크플로우)은 *형태*가 다른 요청에만 생성됨을 명시. 감사 결과 과장은 README에 국한(CLAUDE.md·harness-references·hyean-web 0건).

## v2.2.0 (2026-06-10) — 사용자 영역 파티션 폐기 (read-only 배포)

- **[BREAKING] `*-local/` 사용자 영역 제거** — `agents-local/`·`references-local/`·`workflows-local/` 디렉토리 + 동명 오버라이드 해석 삭제. 스킬 폴더는 이제 **읽기 전용 배포 산출물**로 취급한다(사용자 상태 `reports/`·`.env`는 폴더 밖 프로젝트 디렉토리에 있어 폴더는 무손실 재클론 가능). 근거: 커밋 권한 없이 in-place 커스터마이징하는 외부 사용자 페르소나가 부재 — 파티션이 보호하려던 자산이 존재하지 않음(3개 디렉토리 전부 빈 상태). 마이그레이션: 없음(빈 디렉토리 삭제, 핫패스에서 오버라이드 분기 제거).
  - 동반 제거: pre-flight #4 더티체크 + #5 업스트림 신호, §9 rebase 핸드셰이크(→ "git pull, 깨지면 재클론"으로 단순화), `CONTRIBUTING.md`(agents-local→PR 기여 파이프라인), finalize/assemble의 `-local` 탐색·버전힌트.
  - 보존(핵심): 중앙 `agents/`(31종)·`references/`·`workflows/`·`templates/` 라이브러리, §1 생애주기(설계→라이브러리 floor→인라인→`reports/NNN/agents/` 스냅샷), 금지선 원칙, 설치법, hyean-api 계약 가드.

## v2.1.10 (2026-06-09) — 업종 상대 위험조정성과 (price_stats_ranks)

- **[DOC] price_stats_ranks 신규 데이터 반영** — `/price-stats`와 `summary?include=price_stats`가 Sharpe/Sortino/CAGR/Calmar/MDD/변동성/VaR/베타 8지표의 **업종·시장·규모(industry/market/size) 그룹 내 상대 백분위·순위**를 함께 반환(추가 크레딧 없음). `percentile 100=업종 최우수`, "상위 N%"=`100−percentile`, 변동성·베타는 낮을수록 우수로 방향보정. quant-analyst가 업종 대비 위험조정성과를 **`price_stats_ranks` 1차 근거**로 [F] 서술(절대 임계치는 강세장 왜곡 주의→보조), 정성 맥락만 웹 보강. 반영: api-reference.generated.md(재생성)·hyean-api-guide.md(응답+해석)·analysis-quickcard.md §8·quant-analyst·data-collector(INDEX 다이제스트). 데이터 소스는 신규 `api.price_stats_ranks` 테이블(파이프라인 build_price_stats).

## v2.1.9 (2026-06-09) — 결과 보기 게이트 (finalize 후 브라우저 열기 선택)

- **[DOC] §8 결과 보기 게이트 추가** — finalize 직후 `AskUserQuestion`으로 [Chrome으로 열기(권장) / 안 열기] 제시. "열기" 시 `open -a "Google Chrome" <RUN_DIR>/index.html`(macOS, 실패 시 기본 브라우저 폴백). 배치는 마지막 1회만/headless는 생략(과잉 질문 방지). 시작 게이트(§0/§0.5)와 대칭. hyean.io 공유 업로드는 제외(웹세션 전용 설계 + 키유출 공개발행 리스크 — 추후 unlisted 강제 방식으로 별도 검토).

## v2.1.8 (2026-06-09) — 명확화 게이트 (모호한 요청만 구체 선택지로 정렬)

- **[DOC] §0.5 명확화 게이트 추가** — 스코프 안이지만 **모호한** 요청(깊이/초점 불명·다중해석·핵심 파라미터 결측·목적 불명)은 시작 전 `AskUserQuestion`으로 **구체 선택지** 제시(서술형 유도 금지). 모호한 채 시작→통째 재작업 방지. **두 안전장치 필수**: ① 명확하면 즉시 진행("바로 시작" 속도 유지) ② 합리적 기본값 추론 가능한 건 묻지 말고 기본값+가정 명시(과잉 질문=마찰). 1회·2~3질문·옵션에 "(권장)" 기본값.

## v2.1.7 (2026-06-09) — 스코프 게이트 (off-topic 요청 처리 명문화)

- **[DOC] §0 스코프 게이트 추가** — 요청이 한국 주식·재무 범위 밖이면(스포츠·일반상식·코딩 등) pre-flight 전에 멈추고 ① 파이프라인 강제 금지 ② 정직히 범위 고지 ③ 적합 도구(`/deep-research` 등) 안내 또는 금융 각도로 재해석 제안 ④ 추측 말고 확인. 그간 문서화 없이 모델 판단에만 의존하던 동작을 명문화(덜 신중한 런이 무관 요청에 파이프라인을 억지로 돌려 크레딧·시간 낭비하는 실패모드 차단). 보안이 아니라 UX 일관성·자원낭비 방지 규칙임을 명시(악의적 사용자는 서버측 책임).

## v2.1.6 (2026-06-09) — §4 zsh 스니펫 위치인자 충돌 수정

- **[FIX] §4 하위폴더 xargs 스니펫의 `sh -c '$0/$1/$2'` → named env(`RAW/H/BASE`)** — v2.1.2(D/E/F)에서 넣은 `sh -c` 위치인자가 `/financial-harness <인자>` 슬래시명령 보간과 충돌(숫자 위치인자 $0/$1/$2가 인자 단어로 치환돼 스니펫 깨짐). 실행 영향 없는 예시 문서지만 매 인자 있는 호출마다 재현. named 변수는 보간 안전(`$RAW` 등은 그대로 유지됨이 실증) → env-prefix로 sh -c에 전달. SKILL.md 내 숫자 위치인자 0건 확인(경고문도 `$N`으로 표기).

## v2.1.5 (2026-06-09) — 디자인 컴포넌트 가용성 (writer가 골라 쓸 수 있게)

- **[DOC] design-cheatsheet에 "선택 컴포넌트 카탈로그" 추가** — design-kit.html엔 있으나 cheatsheet에 없어 **report-writer가 존재를 몰라 한 번도 안 쓰던** 12종(tabs·compare-grid·timeline·accordion·detail-collapse·callout·pull-quote·stat-highlight·risk-badge·scenario-toggle·progress-bar·heatmap·priority)을 노출. 진단: 전 리포트 body.html 탭 사용 **0건**(data-tab은 조립기 보일러플레이트뿐) — 원인은 writer가 111KB design-kit 미통독, cheatsheet만 읽는데 거기 누락. **강제 아님** — 컴포넌트별 "쓸 상황 ✅ / 피할 상황 ❌" 가이드 + ⛔접어 숨기는 컴포넌트는 핵심·필수본문에 금지(HTML=MD·인쇄·스캔 보존).

068 복합런(매크로+2종목) 45분 병목 분석 결과 반영. 산출물 품질 불변, 직렬 21분(전체 47%) 압축 목표 ~28~30분.
- **[DOC] 병렬 규율을 전 런 유형에 강제** (§실행순서) — 헤더 "(단일종목)"→"(모든 런 유형)". scaffolder∥analysts·DA∥writer가 비교·다종목·매크로·복합 런에서 누락되기 쉬운 점 + 068 4대 병목(scaffolder/DA 미병렬·reconciler 별도·writer 후 재작업) 명시.
- **[DOC] reconcile 경량화** (§1.7) — 단순 2~3종목·명확한 2-way 수렴은 reconciler 에이전트(3.5분 스핀업) 대신 **오케스트레이터 인라인 수렴**. 전용 에이전트는 다중충돌·4사+·출처 재대조 복합 케이스만.
- **[DOC] report-writer 제출 전 self-check** (report-writer.md, §5.7) — assemble 직전 3종(가시텍스트 canonical 0·적정가 산술 정합·시나리오 합 100%) 자체 점검·수정 → §5.7 수정 라운드(068 +3분) 제거. §5.7은 §5.6과 1회 batched로 확인만, 수정 없이 종료가 기대값.

## v2.1.3 (2026-06-09) — 068 회고: 채점기 멀티컴퍼니 서브폴더 인식

- **[FIX] report_quality_check.py: `00_raw/{corp}/` 서브폴더 스캔** — `check_data_completeness`·`check_api_efficiency`가 `00_raw` 직속 `*.json`만 보고 종목별 하위폴더(멀티컴퍼니 수집 표준)는 무시 → 데이터완전성 0(F)·총점 폭락. 하위폴더 파일을 `{corp}_summary` 등으로 등록해 기존 다기업 `_summary` 패턴이 인식하도록 수정. expand_citations(v2.1.1)와 동일 glob 버그의 채점기 버전. 068 재채점 66→**97**, 단일종목(064)·기존 멀티(067) 100 무회귀 확인.

## v2.1.2 (2026-06-08) — 067 회고: 스크리닝 심층분석 워크플로우 공백 (D·E·F)

- **[FEAT] 심층 스크리닝(발굴+상세) 패턴 + 종목당 1에이전트 fan-out** (D) — §1 로스터·§5.1 예산표에 "발굴 후 Top-N 개별 상세분석" 변형 추가. N종목 상세분석은 종목당 1에이전트 병렬(몰빵 금지, 분석 wall=가장 느린 1종목) — 067에서 3종목 몰빵(14.7분) vs 2종목(7분) 불균형으로 +8분 손실한 실측 반영.
- **[DOC] 스크리닝 성장성 검증 서브스테이지** (E) — multi-company-framework §4에 추가: `/screening`은 시점 스냅샷만 제공 → 후보 풀 `/summary?years=5&consol=1` 배치로 CAGR+YoY 양전환 일관성 점수화 → base-effect·매출정체·이익plateau 함정 제거. 크레딧 가드(N 캡 + 402 선례) + 크레딧 효율 비용 반영.
- **[DOC] zsh 동적 corp 리스트 배치 스니펫** (F) — §4에 추가: zsh는 `$(...)`·변수확장 무분할 → 동적 후보는 `xargs -P`로 순회(consol=1 명시). 067 `for cc in $codes` 실패 선례 포함.
- 방식: design→adversarial-verify 워크플로우(6에이전트 pipeline)로 각 edit를 실제 파일 verbatim 대조·모순검사 후 적용.

## v2.1.1 (2026-06-08) — 067 런 회고 (멀티컴퍼니 심층 스크리닝)

- **[FIX] expand_citations: 멀티컴퍼니 글롭 재귀화** — `00_raw/{corp_code}/summary.json` 서브폴더 구조를 인덱싱(루트 `*.json` ∪ `*/summary.json`). 기존 top-level-only 글롭이 서브폴더를 못 읽어 report-writer가 파일을 루트로 수동 복사하던 silent workaround 제거. `screen/`·`web/` 보조 산출물은 패턴 불일치로 자동 제외.
- **[FIX] reconciler: 적정가 표기 정합 규칙** — 헤드라인 적정가=시나리오 가중 기대값, 상승여력%=(기대값/현재가−1) 산술일치, 방법론 범위는 "(참고)" 라벨 분리. 067 동성케미컬 "5,500~7,500 범위 vs +21%" 모순이 보고서로 박혀 수정 에이전트 재작업(+~9분) 유발한 선례 차단.
- **[FIX] §5.6/§5.7 검증: 적정가↔상승여력% 산술 정합 체크 추가** — 완전성 체크리스트 + 검증 루프가 `abs((적정가/현재가−1)*100 − 표기%) ≤ 1`을 batched python으로 점검. 위 reconciler 모순이 검증을 통과하던 공백 보완.

### 전체 정합성 감사 (4영역 병렬) — 확정 수정분
- **[FIX] consol 기본값 정정 (사실오류·고영향)** — SKILL.md §4·hyean-api-guide(§/financials·§/summary 경고)·multi-collector·sector-collector가 "`/summary`·`/financials` 기본값=별도(0)"라 단언했으나 **실제 기본값은 연결(1)**. 소스(`financials.py:152`·`enhanced.py:37` = `Query(1)`) + generated 정본(§2 precedence) + 실증(삼성 자산총계 미지정=566.9조=연결) 3중 확인. 별도/연결 차이 예시는 유지, false premise만 정정. "consol=1 명시" 습관은 유지(의도 명확화).
- **[FIX] SKILL.md §4 수집 크레딧** — "3회 12크레딧" → 실제 4 curl(discover 2+summary 5+insight 5+price 1) "4회 13크레딧"(price 추가 후 미갱신 잔재).
- **[FIX] report-writer.md frontmatter** — `model:` 누락(전 에이전트 중 유일) → `model: sonnet` 추가(scaffolder 등 writer류와 일관).
- **[FIX] README.md** — 디렉토리 트리의 `CLAUDE.md` 항목 제거(§1-3 "CLAUDE.md 생성 안 함"과 모순).
- **[FIX] CHANGELOG·HARNESS_VERSION** — 존재하지 않는 `docs/BATCH_FIXPLAN_20260608.md` 참조 제거; HARNESS_VERSION `2`→`2.1.1`(CHANGELOG semver·§9 점검과 일치).
- **[CLEANUP] 감사 후속 5건 처리**:
  - design-tokens.css **삭제**(design-kit.html :root와 드리프트: 24 vs 30 변수, `--sp-*`/`--radius-*` 불일치 → 잠재 깨진토큰). 정본 = design-kit.html :root, SKILL §2 행 제거.
  - settings.template.json: `Write(*)`/`Edit(*)` → `reports/**` + `.claude/skills/financial-harness/**`로 **최소권한 스코프**(홈·시스템 밖 쓰기 차단, 하네스 동작 100% 보존).
  - README: `revfactory/harness`·죽은 samsung-report 링크 정정(remote = twiw49/financial-harness).
  - harness-references: harness-workflow 상단에 **정본 헤더**(운영 정본=SKILL §1-9, 동적하네스는 .claude/agents 대신 템플릿 라이브러리) + agent-design-patterns·team-examples의 "반드시 .claude/agents" 무조건문 완화.
  - SKILL §5.4 결번 명시(재번호 시 §5.6/5.7 연쇄참조 파손 → 안정적 ID로 유지).

## v2.1 (2026-06-08) — 배치 회고 반영

- 채점기: 다기업(섹터·비교) audit/insight N/A 처리(C-2) — 방산섹터 90→96, 조선비교 93→98, 단일종목 무영향
- scaffolder: 부문/세그먼트 element sanity 체크(C-1) — Revenue 오선택 방지(064 계약부채 사고)
- report-template/analyst: 방법론 내부 3배+ 괴리 명시(C-3-lite, 트리거 아닌 규약) + 컨센 ±15%+ 괴리 사유 필수(C-4) + forward 웹인용 규약(H-3, B-2 저작권 대체)
- 배경: reports/_BATCH_RETRO_20260608.md

## v2 (2026-06-07)

- **라이브러리 v2 정합 패스**: 39→31종 정돈(중복·런특화 8종 _archive), 전 파일 schema:2·표준문구·quickcard-우선·generated-정본 참조 통일, 런특화 박제(종목 하드코딩) 일반화, 크레딧/엔드포인트 사실표기 제거. 오케스트레이터의 "런 컨텍스트 정정 문단"이 불필요해짐.

- **[BREAKING] 에이전트 = 스킬의 데이터 (①′)** — `.claude/agents/` 레지스트리 사용 중단, `agents/` 템플릿 라이브러리(37종) + general-purpose 인라인 주입으로 전환.
  - 마이그레이션: `.claude/agents/`에 직접 만든 정의가 있다면 `agents-local/`로 이동.
- **[BREAKING] API 사실관계 정본 = `references/api-reference.generated.md`** (②′-a) — hyean-api-guide.md는 전략 전담, 크레딧/파라미터는 generated 참조.
  - 마이그레이션: 자체 노트가 가이드의 구 크레딧 표기를 인용했다면 generated 기준으로 갱신.
- 사용자 영역 신설: `agents-local/`, `references-local/` — git pull과 충돌하지 않는 로컬 진화 공간. 동명 템플릿은 local 우선.
- pre-flight 확장: 중앙 영역 더티 체크 + 업스트림 업데이트 신호 + (localhost 시) API 서빙 rev 비교.
- 채점기: summary 통합수집 인정, 런 유형별(매크로/스크리닝/다기업) 기준, 시장데이터(PS_*) provenance 클래스, agent_design staleness 수정.
- expand_citations: 파생지표 과거 기간 inputs 합성.
- report-template: 테마별(신뢰도/퀀트/이상치/세그먼트) 필수 계약.
- design-kit: UX 9종(모바일/인터랙션/정렬/라이트모드/인쇄/링크/툴팁 등).

## v1 (2026-05 ~ 06-05)

- 초기 하네스: SKILL §1~§8, references 11종, 조립기/확장기/채점기, design-kit, `.claude/agents/` 작업대 방식.
