# Design Cheatsheet — report-writer 전용 (design-kit.html 압축본)

> **이 치트시트만 읽으면 된다.** 111KB `design-kit.html`을 통째로 읽지 말 것 — CSS/JS 보일러플레이트는
> `assemble_report.py`가 자동으로 감싼다. report-writer는 **본문 콘텐츠(body.html)** 와 **MD**만 작성한다.

## ★ 분담 빌드 (scaffolder ∥ analyst 병렬 — 속도 최적화)

데이터 결정적 섹션은 **scaffolder**가 analyst와 **동시에** 빌드하고, 서술 섹션은 placeholder로 남긴다. analyst 완료 후 **report-writer**가 placeholder만 채운다. → analyst의 추론 시간과 표/차트 빌드가 겹쳐 전체 단축. 표/차트는 결정적이라 품질 무손실.

**scaffolder 산출 = `_workspace/body.html`** (수집 직후, analyst와 병렬):
- `report-container` 열기 → `hero-title` → `report-date-banner`
- `<!--FILL:verdict-hero-->`  ← writer가 채움
- `<!--FILL:exec-summary-->`  ← writer (3 Key Questions 포함)
- **기업개요**: 회사 팩트 표(시장/업종/시총/주식수) + `<!--FILL:overview-strategy-->`(MD&A 전략 서술은 writer)
- **재무분석(데이터부)**: `kpi-grid`(ROE/PER/PBR/부채비율/영업이익률 등, citation 토큰) + 5년 손익·재무상태·현금흐름 표(토큰) + 추이 차트(canvas+Chart.js) + `<!--FILL:financial-commentary-->`
- **Peer Comparison 표**(summary.peers, 토큰) + `<!--FILL:peer-commentary-->`
- 주가 차트(price.json) + price_stats KPI
- `<!--FILL:valuation-->` (3법+민감도+judge panel) · `<!--FILL:scenarios-->` (scenario-bar) · `<!--FILL:counter-thesis-->` · `<!--FILL:market-disconnect-->` · `<!--FILL:risk-->` (4×4 매트릭스) · `<!--FILL:action-guide-->`
- `next-actions`(정적) → `disclaimer`(정적) → `report-container` 닫기

**report-writer (analyst 완료 후)**: `analysis.md`를 읽고 `body.html`의 **각 `<!--FILL:x-->`를 서술 HTML로 치환**(데이터 섹션은 손대지 않음). 이어서 MD 작성 + 조립기 실행. FILL 마커가 남아있으면 누락 — 0개 확인.

> scaffolder는 분석 결론(밸류에이션/시나리오/의견)을 **추측하지 않는다** — 그 부분은 FILL 마커로 비우고 writer가 analyst 결과로만 채운다(품질 보존).

### ⚠️ scaffolder item 코드 규칙 (rework 방지 — 중요)
hyean 토큰의 `item=`은 **00_raw에 실재하는 canonical_id만** 사용한다(없는 코드는 assemble에서 "미해결 토큰" → writer rework 유발). 작성 전 `CONSOL_DIGEST.md`/`summary.json`의 실제 키를 확인할 것.
- 자주 틀리는 코드: 부채총계는 **`BS_LIA_TOT`**(BS_LIAB_TOT 아님), 자본 **`BS_EQT_TOT`**, 지배지분 **`BS_EQT_CTL`**, 영업이익 `IS_OPR`, 순이익 `IS_NET`, 매출 `IS_REV`, 비율 `DRV_ROE`/`DRV_PER`/`DRV_PBR`/`DRV_EV_EBITDA`/`DRV_OP_MARGIN`/`DRV_DEBT_RATIO`.
- **시가총액·상장주식수·현재가·목표가는 Hyean 재무 item이 아니다** → `DRV_MKTCAP`/`SHARES_OUT` 같은 코드 금지. **출처에 맞는 토큰**으로:
  - 현재가·목표가·시총이 **웹/네이버/FnGuide 출처면 `{{w|...}}`(URL 포함)** — est 쓰지 말 것(URL 추적성 손실, citation diversity↓).
  - **Hyean 모델 적정가·시나리오·Forward EPS는 `{{h|item=VAL_*|...}}`** — expand가 valuation.json에서 자동 합성(period 생략 가능): 방법별 `VAL_{METHOD}`(예: VAL_DCF·VAL_REL_EV_EBIT), `VAL_RANGE_{LOW|MID|HIGH}`, `VAL_SCENARIO_{BEAR|BASE|BULL}`, `VAL_FWD_EPS_{LOW|MID|HIGH}`.
  - **주가통계(Sharpe/CAGR/MDD/베타 등)는 `{{h|item=PS_{1Y|3Y|5Y}_{FIELD}|...}}`** — summary price_stats에서 자동 합성(period 생략 가능, 예: PS_1Y_SHARPE).
  - `{{e|...}}`는 **그 밖의 모델/추정치**(자체 가중 계산, 정상화 이익 등)에만 — Hyean 데이터를 est로 위장 금지(원문 링크 소실).
  - summary.json `market_cap`은 공시 시점 값이므로 web(네이버 실시간)과 다를 수 있음 — 보고서 현재가는 web 토큰 우선.
- **PER/PBR/EV-EBITDA/배당수익률 등 비율은 hyean 토큰으로 해결됨**(summary.ratios 단일 dict도 인덱싱) — `{{h|item=DRV_PER|period=...|consol=1|corp=...|...}}`. est로 내리지 말 것.
- peer 비율은 summary.peers에서 오며 **별도/연결 혼용** 가능 → 표 caption에 기준 명시, 가능하면 est 토큰.
- 확신 없으면 그 수치는 토큰 대신 일반 텍스트로 두고 writer가 보완하도록 FILL 인접에 메모.

## 워크플로우 (속도 최적화 — 매번 이 순서)

1. `RUN_DIR/_workspace/body.html` 작성 — `<body>` **안에 들어갈 콘텐츠만**. DOCTYPE/head/`<style>`/`<script src>`/`</body>` 쓰지 말 것. 아래 컴포넌트 클래스 + citation 토큰 사용. **서술 포함 전체 내용을 여기에 담는다** (별도 `{기업명}_보고서.md` 작성 금지 — 2026-07-17 폐지, HTML 단일 산출물).
2. 조립 + citation 확장 (한 번에):
   ```bash
   python3 .claude/skills/financial-harness/scripts/assemble_report.py <RUN_DIR> --title "<기업명> 투자분석 보고서"
   ```
   → `RUN_DIR/index.html` 생성 (CSS/JS 자동 래핑 + 토큰 확장). "미해결 토큰 0" 확인.

(품질 점검 report_quality_check.py는 writer가 돌리지 않는다 — 오케스트레이터가 §5.7에서 1회. SKILL "writer 1-pass" 규정.)

## Citation 토큰 (수치 100%에 적용 — report-template.md §4 상세)

```
Hyean 원본/파생: {{h|item=IS_OPR|period=2025-12-31|consol=1|label=영업이익|disp=43.6조원}}
웹:             {{w|name=FnGuide|url=https://...|type=commercial|label=평균 목표주가|value=415200|disp=415,200원}}
추정:           {{e|name=3법 가중|label=적정가|value=298800|disp=약 298,800원}}
감사:           {{a|rcp=20260310002820|corp=00126380|label=핵심감사사항|disp=건설중 자산}}
인사이트:        {{i|cat=insight_mda|corp=00126380|text=원문 일부…|label=사업 전략|disp=메모리 선도}}
```
- hyean은 `item`+`period`(+`consol`)만 주면 rcp_no/anchor/quality/value/description 자동 주입. **disp/label은 한국어**(canonical_id 금지).
- **다기업(비교/섹터/포트폴리오)**: 토큰에 `corp=<corp_code>` 추가로 기업 지정 — `{{h|item=IS_REV|period=2025-12-31|consol=1|corp=00126380|label=삼성 매출|disp=333.6조}}`. 단일기업은 `corp=` 생략 가능. (다기업 수집 시 각 기업 summary를 `{name}_summary.json`로 저장하면 자동 인덱싱.)
- `type`→confidence 자동: official→high, commercial/analyst→medium, news/blog→low.

## 핵심 컴포넌트 (복사용)

**레이아웃**: 최상위는 `<div class="report-container"> … </div>`.

**기준일 배너** (h1 바로 아래, 필수):
```html
<div class="report-date-banner">📅 분석 기준일 2026-06-05 · 재무 데이터 연결 2025-12-31(연간)/2026-03-31(분기) · 현재가 2026-06-04 종가</div>
```

**히어로 타이틀 / 한 줄 결론**:
```html
<h1 class="hero-title">삼성전자 <span>투자분석 보고서</span></h1>
<p class="key-takeaway">한 줄 결론: …</p>
```

**Verdict Hero** (투자의견 카드):
```html
<div class="verdict-hero">
  <div class="verdict-badge hold">HOLD</div>
  <div class="verdict-metrics">
    <div class="vmetric"><span class="vlabel">적정가</span><span class="vval">298,800원</span></div>
    <div class="vmetric"><span class="vlabel">기대수익률</span><span class="vval">-15%</span></div>
    <div class="vmetric"><span class="vlabel">리스크</span><span class="vval">중</span></div>
  </div>
  <div class="confidence-meter"><div class="cm-fill" style="width:70%"></div></div>
</div>
```
(badge 클래스: `buy`/`hold`/`sell`/`strong-buy`/`strong-sell`)

**KPI 그리드**:
```html
<div class="kpi-grid">
  <div class="kpi-tile"><div class="kpi-label">ROE</div><div class="kpi-value">{{h|item=DRV_ROE|period=2025-12-31|consol=1|label=ROE|disp=10.8%}}</div></div>
  …4~8개…
</div>
```

**Insight 카드** (강점/리스크/경고):
```html
<div class="card-grid">
  <div class="insight-card bullish"><h4>강점</h4><p>…</p></div>
  <div class="insight-card bearish"><h4>리스크</h4><p>…</p></div>
  <div class="insight-card warning"><h4>경고</h4><p>…</p></div>
</div>
```

**표** (숫자 우정렬 `.num`):
```html
<table><thead><tr><th>항목</th><th class="num">2024</th><th class="num">2025</th></tr></thead>
<tbody><tr><td>매출액</td><td class="num">{{h|item=IS_REV|period=2024-12-31|consol=1|label=매출액|disp=300.9조}}</td>
<td class="num">{{h|item=IS_REV|period=2025-12-31|consol=1|label=매출액|disp=333.6조}}</td></tr></tbody></table>
```

**차트** (Chart.js — canvas + 인라인 script):
```html
<div class="chart-wrap"><div class="chart-title">매출·영업이익 추이</div><canvas id="revChart"></canvas></div>
<script>new Chart(document.getElementById('revChart'),{type:'bar',data:{labels:['2021','2022','2023','2024','2025'],
  datasets:[{label:'매출(조)',data:[279.6,302.2,258.9,300.9,333.6]}]},options:{responsive:true}});</script>
```

**OHLCV 주가 차트** (`00_raw/price.json` 데이터로 인라인 — ★canvas만 만들고 init 스크립트를 빠뜨리면 빈 박스가 된다):
```html
<div class="chart-wrap"><div class="chart-title">종가 추이 (최근 1년)</div><canvas id="ohlcv"></canvas></div>
<script>(function(){
  var p=[{d:'2025-07-01',c:61000},{d:'2025-07-08',c:62300}/* …price.json 종가, 주 1~2포인트 샘플링 */];
  new Chart(document.getElementById('ohlcv'),{type:'line',
    data:{labels:p.map(function(x){return x.d;}),datasets:[{label:'종가(원)',data:p.map(function(x){return x.c;}),borderColor:'rgba(0,194,255,0.9)',pointRadius:0,tension:0.2,fill:false}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
})();</script>
```

**시나리오 바** (확률 합 100%, baseline+type 필수):
```html
<div class="scenario-bar" data-scenario-baseline="351500" data-scenario-type="목표주가(원)">
  <div class="scenario-item bull" style="flex:30">Bull 30%<br>420,000</div>
  <div class="scenario-item base" style="flex:45">Base 45%<br>350,000</div>
  <div class="scenario-item bear" style="flex:25">Bear 25%<br>260,000</div>
</div>
```

**Callout**: `<div class="callout info|warn|success|danger"><b>제목</b> 내용</div>`
- ★경고·주의·해설 **문장은 callout 한 단락으로** — 문장을 표 셀·그리드 칸으로 쪼개지 말 것 (좁은 셀에서 글자 단위 줄바꿈 → 가독성 붕괴. 002 "밸류에이션 기준가 주의"가 표 셀 분할로 파편화된 사례).

**F/E/O 뱃지** (cited span 옆): `<span class="feo-badge fact">[F 공시]</span>` / `estimate` `[E 추정]` / `opinion` `[O 의견]`.

**신뢰도**: `<span class="conf verified|high|medium|low">검증완료|높음|보통|주의</span>`

**리스크 뱃지**: `<span class="risk-badge low|medium|high|critical">중</span>`

**종목 대시보드 링크** (모든 한국 상장기업명): 
```html
<a class="stock-link" href="https://hyean.io/company/00126380" target="_blank" rel="noopener">삼성전자</a>
```

**민감도 매트릭스**: `<table class="sensitivity-matrix">…</table>` (heatmap 셀 클래스 `.cell-hot/.cell-warm/.cell-cool`).

**용어 범례/사전** (접기): `<details class="feo-legend">…</details>`, `<details class="glossary">…</details>`.

**다음 추천 분석** (하단): `<div class="next-actions"><h3>다음 추천 분석</h3><ul><li>…</li></ul></div>`

**면책**: `<div class="disclaimer">…</div>` (마지막 섹션).

## 선택 컴포넌트 카탈로그 (강제 아님 — 적합할 때만 골라 쓰기)

> **원칙**: 내용이 그 구조로 **더 잘 읽히면** 쓰고, 애매하면 기본(섹션·표·callout)으로 둔다. 미관 위해 억지로 넣지 말 것.
> **⛔ 접어서 숨기는 컴포넌트(tabs·accordion·detail-collapse)는 "다 보여야 하는 것"에 쓰지 말 것** — 한 줄 결론·Verdict·필수 8섹션 본문·핵심 수치·결론. **부차/반복 구조에만.** (HTML=MD 동일내용·인쇄·linear 스캔을 깨지 않게.) JS는 assemble가 자동 주입(수기 불필요).

| 컴포넌트 | 쓰면 좋은 상황 ✅ | 피할 상황 ❌ | 클래스 |
|---|---|---|---|
| **tabs** | 비교/다종목 리포트의 **종목별 상세**, 시나리오 토글 등 반복구조 접어 길이↓ | 핵심결론·Verdict·필수본문 | `<div class="tabs"><div class="tab-nav"><button class="tab-btn active" data-tab="t1">삼성</button>…</div><div class="tab-panel active" id="t1">…</div></div>` |
| **compare-grid** | 2~3 대상 **나란히 비교**(vs 리포트 상단 한눈 비교) | 단일종목 | `<div class="compare-grid">…2~3열…</div>` |
| **timeline** | **시계열 이벤트**(급락 전개·실적/수주 히스토리·규제 연표) | 비-시간 데이터 | `<div class="timeline"><div class="tl-item"><div class="tl-date">2026.03</div><div class="tl-content">…</div></div></div>` |
| **accordion / detail-collapse** | **부차 상세** 접기(방법론 가정·민감도 보조표·Counter-thesis 근거 디테일) | 필수 8섹션 본문 | `<div class="accordion-item"><div class="accordion-header">제목</div><div class="accordion-body">…</div></div>` · `<div class="detail-collapse">…</div>` |
| **callout** info/warn/success/danger | 경고·주의·핵심 박스(밸류에이션 기준 주의, stale 컨센 등) | 남용(섹션마다) | `<div class="callout warn"><strong>제목</strong> 내용</div>` |
| **pull-quote** | thesis **핵심 한 문장** 강조 | 수치·표 | `<div class="pull-quote">"…"</div>` |
| **stat-highlight** | 인라인 **대형 수치** 강조(목표가·괴리율 등) | 표 안 셀 | `<span class="stat-highlight">+80%</span>` |
| **risk-badge** low/medium/high/critical | 리스크 **등급 뱃지** 시각화 | — | `<span class="risk-badge high">HIGH</span>` |
| **scenario-toggle** | Bull/Base/Bear **차트 토글**(scenario-bar 대안) | 단순 3행이면 scenario-bar로 | `<div class="scenario-toggle" data-chart="chartId">…</div>` |
| **progress-bar** | 점유율·확률·달성률 **시각 바** | 정밀 비교는 표 | `<div class="progress-bar"><div class="progress-fill" style="width:75%">75%</div></div>` |
| **heatmap** hot/warm/cool/cold | 일반 표 셀 **농도 시각화**(sensitivity-matrix 외) | 소표 | `<td class="heatmap warm">값</td>` |
| **priority** core/important/reference | 섹션 **정보 위계**(접지 않고 시각 강약) | — | `<section class="priority-core">…</section>` |

## 필수 섹션 순서 (단일 종목 11섹션 지향)
한 줄 결론 → Verdict Hero → 기준일 배너 → Executive Summary(3 Key Questions) → 기업개요 → 재무분석 → 밸류에이션(3법 교차검증) → Peer Comparison → 시나리오 → Counter-thesis → Market disconnect → 리스크 → 투자 행동 가이드 → 다음 추천 분석 → Disclaimer.

## 품질 불변식 (assemble 후 자동/수동 확인)
- canonical_id 본문 노출 0 (토큰의 `disp`/`label`은 한국어).
- 모든 수치 citation 토큰 → 확장 후 `data-*` 완비. "미해결 토큰 0".
- 기준일 배너 존재, 시나리오 확률 합 100%(+baseline+type), F/E/O·신뢰도 한글 병기.
- insight_mda 서술 반영(수치 나열 금지), 모든 한국 상장기업 stock-link.
