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
- **★표시값(disp) = 인용 data-value 정합 (추적성 계약, 어기면 드로어 클릭 시 화면과 다른 숫자):**
  화면에 쓴 숫자는 그 토큰이 resolve하는 값과 **같은 기간·같은 정의**여야 한다. 흔한 위반과 교정:
  - **분기 단독값**을 쓰면 `item=..._Q|period=<분기말>`로 인용. 예: 26Q1 영업이익률 42.75%는
    `{{h|item=DRV_OP_MARGIN_Q|period=2026-03-31|consol=1|disp=42.75%}}` — 일반 `DRV_OP_MARGIN`은
    **TTM/연간(24.24%)**으로 resolve돼 불일치. 분기 매출·영업이익·순이익도 `IS_REV_Q`/`IS_OPR_Q`/`IS_NET_Q`.
  - **정상화·재계산 값**(자체 조정 PER·정상화 이익 등)은 hyean 토큰이 raw값으로 열려 불일치 → 반드시
    `{{e|name=…|value=<표시값>|disp=…}}`로. Hyean 데이터를 est로 위장 금지지만, **재계산한 값**은 est가 정답.
  - assemble 실행 시 **"⚠ 표시값≠data-value 의심 N건"** 경고가 뜨면 전건 토큰(기간/종류)을 교정하고 재조립 —
    **0건**을 확인한다(미해결 토큰 0과 동급 게이트).
- **★기준 정합 (as-of·연결/별도·fwd/trailing) — 무라벨 혼용 금지** (블랙박스 채점 최다 감점): 한 표·행·KPI에 배수·시총·수익률·순차입을 나란히 실을 때 **서로 다른 시점·정의를 라벨 없이 섞지 말 것**. 흔한 위반:
  - **현재가/시총은 실시간인데 PER·EV/EBITDA·배당수익률은 결산일 종가 기준**(peer 표) → 같은 행이면 **동일 price-date로 통일**하거나 각 배수 열에 기준일 표기(엔터·조선 peer 표에서 EV배수만 결산일이라 대형주 ~65% 과대·저평가 은폐).
  - **Forward PER ↔ Trailing PER 무라벨 혼용** → `(fwd)`/`(현재가)` 접미 필수(같은 종목 PER이 8.8과 11.8로 갈리면 즉시 자기모순).
  - **순차입(net_debt) 협의(현금성만)/광의(전체 금융자산)·FY24/FY25 혼동** → 정의·as-of 명시, **순현금 서술과 순차입 KPI가 함께 나오면 부호 일치 확인 + 1줄 reconciliation**.
  - **ROE·EPS 연결↔지배 기준** → 적자연도엔 총·지배 괴리가 커 표 순이익/자본으로 재현 불가 → 지배 순이익 행 병기 또는 각주.
  - **Beta·통계가 창 무관 단일값**이면 "3Y Beta"로 특정하지 말고 "정적 Beta(창 무관)"로 + R² 부재 고지.
  - 원칙: **파생 KPI는 원천 데이터의 as-of·정의를 승계**한다(기준일 배너의 시점과도 정합).

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
  <div class="verdict-grid">
    <div class="verdict-opinion hold"><span class="verdict-label">투자의견</span><span class="verdict-value">HOLD</span></div>
    <div class="verdict-metric"><span class="verdict-label">적정가</span><span class="verdict-value">298,800원</span></div>
    <div class="verdict-metric"><span class="verdict-label">기대수익률</span><span class="verdict-value negative">-15%</span></div>
    <div class="verdict-metric"><span class="verdict-label">리스크</span><span class="verdict-detail">중</span></div>
  </div>
  <div class="confidence-meter"><span class="meter-label">Confidence</span><div class="meter-track"><div class="meter-fill" style="width:70%"></div></div><span class="meter-value">70%</span></div>
</div>
```
- **★클래스 정확히**: `.verdict-grid > (.verdict-opinion + .verdict-metric×N)`, 각 안에 `.verdict-label` + `.verdict-value`(수치, `.positive`/`.negative` 색). 서술값은 `.verdict-detail`.
  `.verdict-opinion`에 `buy`/`hold`/`sell` 클래스로 색. (구버전 `.vmetric/.vlabel/.vval`도 별칭으로 렌더되나 정본 클래스를 쓸 것.)

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

**유형별 권장 차트** (막대·선만 반복하지 말 것 — 요청 유형이 요구하는 문법을 골라 쓴다):

> ⚠️ **이질 스케일/단위를 한 축에 얹지 말 것**(V3): PER(배)·마진(%)·금액(조)처럼 자릿수·단위가 다른 지표를 한 막대축·멀티라인에 함께 두면 큰 값이 축을 지배해 나머지가 판독 불가(예: 그룹막대에 PER 47과 배당수익률 0.13%를 같이 → PER만 보임). 스케일차 >5배면 ①정규화(z-score/min-max/백분위) ②지표별 분리 패널(small multiples) ③보조축(막대=금액 + 선=%) 중 하나. **매출·이익 이중축은 이익을 마진%(선)로** — 동일 단위(조원)를 좌우 두 축에 나누면 변동이 시각적으로 과장된다.

- **밸류-퀄리티 산점 / 버블**(비교·섹터·심층스크린 — 저평가+우량 사분면을 한 화면에. 규모 이질이면 버블=시총):
  ```html
  <div class="chart-wrap"><div class="chart-title">PBR-ROE 산점 · 버블=시총</div><canvas id="vqScatter"></canvas></div>
  <script>new Chart(document.getElementById('vqScatter'),{type:'bubble',data:{datasets:[
    {label:'삼성전자',data:[{x:1.2,y:10.8,r:24}]},{label:'SK하이닉스',data:[{x:1.9,y:17.6,r:14}]},
    {label:'한미반도체',data:[{x:8.1,y:23.1,r:5}]}]},options:{responsive:true,scales:{
    x:{title:{display:true,text:'PBR(배) — 낮을수록 저평가 →'}},
    y:{title:{display:true,text:'ROE(%) — 높을수록 우량 ↑'}}}}});</script>
  ```
  ※ 축 제목에 **우수 방향**을 명시(V7). 저평가+우량 사분면(좌상단)을 결론에서 지목.

- **재무추이 이중축**(단일종목·심층 — 막대(금액)+선(마진%)을 좌우 축 분리):
  ```html
  <script>new Chart(document.getElementById('revMargin'),{data:{labels:['2021','2022','2023','2024','2025'],
    datasets:[{type:'bar',label:'매출(조)',data:[279.6,302.2,258.9,300.9,333.6],yAxisID:'y'},
    {type:'line',label:'영업이익률(%)',data:[18.5,14.3,2.5,10.9,13.1],yAxisID:'y1',borderColor:'rgba(251,191,36,0.9)'}]},
    options:{responsive:true,scales:{y:{position:'left',title:{display:true,text:'조원'}},
    y1:{position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'%'}}}}});</script>
  ```

- **상관 히트맵**(포트폴리오·실사 — 표 셀 채색. `td.heatmap`은 grid 미적용, `hot`≥0.7·`warm`0.4~0.7·`cool`<0.4):
  ```html
  <table><thead><tr><th></th><th>삼성</th><th>현대차</th><th>NAVER</th></tr></thead><tbody>
    <tr><th>삼성</th><td class="heatmap hot">1.00</td><td class="heatmap warm">0.47</td><td class="heatmap cool">0.21</td></tr>
    <tr><th>현대차</th><td class="heatmap warm">0.47</td><td class="heatmap hot">1.00</td><td class="heatmap cool">0.18</td></tr>
  </tbody></table>
  ```

- **스택 막대**(검증·환원 — 구성 기여 분해, 예 총환원율=배당+소각):
  ```html
  <script>new Chart(document.getElementById('payoutStack'),{type:'bar',data:{labels:['KB금융','신한','하나'],
    datasets:[{label:'배당(%)',data:[26,24,28],stack:'s'},{label:'소각(%)',data:[12,8,5],stack:'s'}]},
    options:{responsive:true,scales:{x:{stacked:true},y:{stacked:true,title:{display:true,text:'순이익 대비(%)'}}}}});</script>
  ```

- **밸류에이션 football-field / PER·PBR 밴드**(단일종목·심층 — 방법별 적정가 범위 + 현재가·목표가 마커. CSS, Chart.js 아님):
  ```html
  <div class="football-field" style="--min:0;--max:500000;--cur:255000;--tgt:369000">
    <div class="ff-row"><span class="ff-name">DCF</span><span class="ff-track"><span class="ff-bar" style="--lo:320000;--hi:400000"><b>32~40만</b></span></span></div>
    <div class="ff-row"><span class="ff-name">PER</span><span class="ff-track"><span class="ff-bar" style="--lo:280000;--hi:360000"><b>28~36만</b></span></span></div>
    <span class="ff-marker ff-cur" data-label="현재 255,000"></span><span class="ff-marker ff-tgt" data-label="목표 369,000"></span>
  </div>
  ```
  ※ **PER/PBR 밴드**도 같은 컴포넌트: ff-row 하나에 `--lo/--hi`=역사적 밴드, `--cur`=현재 배수. 값은 전부 unitless.

- **가치사슬 다이어그램**(산업보고서 — 소재→부품→장비→IDM 구조. 개별사 아닌 산업 흐름):
  ```html
  <div class="value-chain">
    <div class="vc-stage"><div class="vc-title">소재</div><div class="vc-body">동진쎄미켐·솔브레인</div></div>
    <div class="vc-arrow"></div>
    <div class="vc-stage"><div class="vc-title">부품</div><div class="vc-body">…</div></div>
    <div class="vc-arrow"></div>
    <div class="vc-stage"><div class="vc-title">장비</div><div class="vc-body">…</div></div>
  </div>
  ```

- **드로다운/언더워터 곡선**(퀀트·성과분해 — MDD를 0 기준 아래로 채워진 곡선으로. MDD가 명시 지표면 수치+이 시각 최소 하나):
  ```html
  <div class="chart-wrap"><div class="chart-title">드로다운 (전고점 대비 %)</div><canvas id="ddChart"></canvas></div>
  <script>new Chart(document.getElementById('ddChart'),{type:'line',data:{labels:['2023-01','2023-07','2024-01','2024-07','2025-01','2025-07'],
    datasets:[{label:'삼성바이오(%)',data:[0,-12.4,-32.8,-18.1,-5.2,-9.0],borderColor:'rgba(248,113,113,0.9)',backgroundColor:'rgba(248,113,113,0.15)',fill:'origin',pointRadius:0,tension:0.2}]},
    options:{responsive:true,maintainAspectRatio:false,scales:{y:{max:0,title:{display:true,text:'전고점 대비 낙폭(%)'}}}}});</script>
  ```
  ※ 여러 종목이면 dataset 추가(색 구분). **equity curve는 벤치마크(KOSPI 등)를 같은 base=100으로 오버레이** — 벤치 3Y가 없으면 보유한 1Y 구간만이라도 오버레이·초과수익 산출(전면 생략 금지). 조밀 샘플로 daily 저점을 놓치면 MDD가 시각상 얕게 보이니 저점 시점을 포인트로 포함.

- **시나리오 팬차트**(매크로·전망 — 공통 시점에서 Bull/Base/Bear 경로 발산):
  ```html
  <script>new Chart(document.getElementById('fan'),{type:'line',data:{labels:['현재','+3M','+6M','+12M'],
    datasets:[{label:'Bull',data:[3000,3120,3260,3450],borderColor:'rgba(0,227,140,0.8)'},
    {label:'Base',data:[3000,3020,3050,3100],borderColor:'rgba(160,160,160,0.9)'},
    {label:'Bear',data:[3000,2900,2820,2700],borderColor:'rgba(248,113,113,0.8)'}]},
    options:{responsive:true,plugins:{legend:{position:'bottom'}}}});</script>
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
- ★**callout은 짧은 핵심 박스** — ①②③로 여러 항목을 열거하는 결론(예 Top Pick 2~3개 + 강등/재분류 + 대조군)을 **callout 한 문단에 몰아넣지 말 것**(밀도 붕괴·구조 안 읽힘). 항목이 3개+면 **`<ul>` 리스트 또는 `card-grid`**로 분리하고, callout은 한 줄 요지에만 쓴다.

**열거형 결론(Top Pick 등) — GOOD 구조** (callout 떡칠 ✗ → 한 줄 요지 callout + 카드/리스트 ✓):
```html
<div class="callout success"><strong>결론</strong> 교과서적 저평가주는 부재 — "생존력 ∩ 회복 순번" 교집합에서 2종만 선별.</div>
<div class="card-grid">
  <div class="insight-card bullish"><h4>① 롯데에너지머티리얼즈</h4>
    <p>"저평가 자산주"가 아니라 <b>재무 최강 생존자 + ESS/AI회로박 성장 옵션</b>. 순현금·부채 23%로 사이클 버팀. 상방은 테마 성장 조건부.</p></div>
  <div class="insight-card bullish"><h4>② 코스모신소재</h4>
    <p><b>방어형 회복 베타</b> — 다운턴 흑자 방어 + MLCC 이형필름 완충(자산 저평가 아님, risk low).</p></div>
</div>
<ul>
  <li><b>강등/재분류</b>: 천보→Watch, 더블유씨피→고위험 반등 옵션, SKIET→밸류트랩 유지, 솔브레인→제외.</li>
  <li><b>대조군</b>: 에코프로비엠·포스코퓨처엠(고PER·안전마진 부재).</li>
</ul>
```

**F/E/O 뱃지** (cited span 옆): `<span class="feo-badge fact">[F 공시]</span>` / `estimate` `[E 추정]` / `opinion` `[O 의견]`.
- ★**뱃지 라벨은 간결하게** — `[F 공시]`/`[E 추정]`/`[O 의견]` 정도. **출처·근거(하나증권 잠정치·원문 미검증 등)는 뱃지에 넣지 말고 citation 토큰(드로어)에** 담는다. 긴 서브라벨을 인라인 뱃지에 붙이면 문장 흐름이 반복적으로 끊긴다(가독성 저하). 한 문장에 뱃지 3개 이상이면 과밀 — 대표 수치에만.

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

**비교(compare) 4섹션 순서**: 비교표(compare-grid, **basis=연결/별도·결산기 표기 필수**) → 각사 재무(동일 축) → 상대 밸류에이션(peers 백분위) → 의견(우열·기준시점 통일 명시).

### ★유형별 밀도 (위 11섹션은 **단일종목 전용** — 다른 유형에 그대로 상속 금지 = scaffold-bleed)
- **경량·스캔** (screening·portfolio 브리핑 모드): 목록/표 중심. **verdict-hero·scenario-bar·종목 심층·투자행동가이드 넣지 말 것.**
  screening=조건충족 목록+지표값+산정정의+위생로그(장문 분석 금지). 브리핑=변동 종목 1줄 이유+안정 명단+수급 델타. (portfolio 진단 모드는 고중량 — 아래.)
- **중량·초점** (event·macro·industry): 핵심 차트 2~4, 초점 유지. event는 **선정한 1건에 한정**(참고 KPI·밸류 방향성 확장 금지).
- **고중량·종합** (single_stock·dd·compare·sector·portfolio·custom·quant): 표+차트 다층, 깊이 필요.
- ★**유형이 명시 배제한 것 금지**: dd·portfolio·industry·screening·**event**는 **목표가·매수의견 없음**(verdict-hero를 쓰면 목표가가 아니라 리스크등급·판정으로). **개별종목 fair value/상승여력·peer 밸류에이션 매트릭스·컨센 목표주가도 유출 금지** — 필요하면 산업 집계(중앙값/분포) **1개**로만(개별 3사 −25~−37% 나열은 disclaim해도 픽처럼 읽혀 위반). **event_interpretation은 선정 1건에 한정** — peer 밸류표·Forward PER·타깃가 대신 backdrop 지표(매출 분모·수주잔고 방향·부채비율) 인라인 1~2개까지만.

## 품질 불변식 (assemble 후 자동/수동 확인)
- canonical_id 본문 노출 0 (토큰의 `disp`/`label`은 한국어).
- 모든 수치 citation 토큰 → 확장 후 `data-*` 완비. "미해결 토큰 0".
- **표시값 = 인용 data-value 정합**: assemble의 "표시값≠data-value 의심 N건" 경고 **0건**(분기값은 `_Q`, 재계산값은 `{{e}}`).
- **본문 파생수치 ↔ 자기 차트/표 tie-out**: 헤드라인·KPI에 쓴 파생값(수익률·MDD·ROE·순차입 부호·성장률·구성비 합)이 같은 리포트의 원천 차트/표와 **부호·크기 일치**해야 한다(12M 수익률 KPI가 자기 주가 차트의 시작→종료가와 부호 반대면 오류). 재구성값과 CAGR-implied값이 **≥3%p** 벌어지면 "정합"이라 쓰지 말고 갭 원인(창 차이 등) 1줄. 불리시/베어리시 근거로 인용하는 수치일수록 이중확인.
- 기준일 배너 존재, 시나리오 확률 합 100%(+baseline+type), F/E/O·신뢰도 한글 병기.
- insight_mda 서술 반영(수치 나열 금지), 모든 한국 상장기업 stock-link.
