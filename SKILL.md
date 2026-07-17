---
name: financial-harness
description: "한국 상장기업 주식/기업 분석 + 하네스 구성을 수행하는 메타 스킬. (1) '주식 분석', '기업 분석', '재무 보고서', '투자 리서치', '종목 분석', '밸류에이션', '산업 분석', '매크로 전망', '비교 분석', '스크리닝', '포트폴리오 진단', '퀀트 전략', '백테스팅', '팩터 분석' 요청 시 — 전문 에이전트를 동적으로 설계·생성한 후 분석을 실행, (2) '하네스 구성', '하네스 설계' 요청 시 — 에이전트/스킬 아키텍처 설계, (3) 기존 하네스 점검/확장/유지보수 시. Hyean API + Citation Drawer 참조를 에이전트에 주입할 것."
---

# Financial Harness (MCP loader v3)

**방법론·데이터는 런타임에 `mcp__hyean__*` 툴이 제공한다.** 이 파일은 스코프 게이트, 런 격리,
페이즈 시퀀스, 파일 규율만 담당하는 얇은 로더다. (구 v2 git-clone 방식의 agents/·references/는
서버로 이관 — `get_plan`이 매 런 최신 방법론을 내려준다.)

## 0. 스코프 게이트 (요청 수신 직후 — 그 무엇보다 먼저, MCP 호출 전에)

이 하네스는 **한국 상장기업 주식·재무 분석 전용**이다. 범위 밖(스포츠·일반상식·코딩·외국기업만)이면 **어떤 툴도 부르기 전에 멈추고**:
1. 파이프라인 강제 진행 금지 (크레딧·시간 낭비 + 헛 보고서)
2. 정직하게 범위 밖 고지 — 날조·추측 금지
3. 적합한 도구 안내 (다출처 리서치는 /deep-research 등). 금융 각도가 실재하면 재해석 제안
4. 경계가 모호하면 1줄로 의도 확인

**커버리지 경계 (스코프 안이어도 먼저 고지):** ① 금융업(은행·보험·증권·금융지주) = 재무제표 미지원 — 지배구조·공시·주가·뉴스만 ② 자유 백테스트(시점별 유니버스·팩터 패널) = 미지원, `/prices/bulk`(≤50종목) 가격 규칙 검증만 ③ 실시간(장중 시세·호가) = 미지원, prices=일별 EOD.

## 0.5 명확화 게이트 (모호한 요청에만)

스코프 안인데 분석 방향이 갈리면 `AskUserQuestion` **1회**(질문 2~3개 이하, 첫 옵션에 "(권장)")로 확정. 명확하면 즉시 진행 · 합리적 기본값(기준일=오늘, consol=1, 보고서 1편)은 묻지 않고 가정 1줄 명시.

## 1. MCP 연결 확인 · 온보딩 self-heal

`mcp__hyean__preflight` 툴이 **보이지 않으면** STOP하고 안내:
```
claude mcp add --transport http hyean https://api.hyean.io/mcp
(Claude Code 재시작 후) /mcp → hyean → 브라우저에서 로그인·승인
```
CI/헤드리스: `claude mcp add --transport http hyean https://api.hyean.io/mcp --header "Authorization: Bearer $HYEAN_API_KEY"`
로컬 API 개발: 위 URL을 `http://localhost:8000/mcp`로 바꾼 `hyean-dev` 항목 별도 등록.

**버전 게이트**: `HARNESS_VERSION`(이 폴더) < `preflight.min_loader_version` → "이 폴더에서 git pull" 안내 후 진행. 로컬 design-kit 해시 ≠ `preflight.kit_sha256`이면 같은 안내(경고성, 차단 아님).

## 2. 실행 시퀀스

1. **preflight** — `mcp__hyean__preflight` 1콜: 크레딧 잔량(<30이면 §0 경계 규약대로 사용자 경고)·api_status·버전. 배치(여러 보고서) 실행 시 매 보고서 시작 전 재확인.
2. **런 격리** — `reports/` 스캔 → 다음 번호 → `REPORT_START=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)` → `mkdir -p reports/{NNN}_{이름}_{YYYYMMDD}/_workspace` → `.report_start`에 타임스탬프 고정. **루트 `_workspace/`·루트 `index.html` 생성 금지.** 스캔에서 **동일 대상·동일 날짜 런이 이미 보이면** 새 수집 전에 1줄 고지 + 재사용/신규 여부 확인 1회 (동일 요청 재실행 크레딧 절약).
3. **플랜 수령** — `mcp__hyean__get_plan(request_type, context)` 1콜.
   - request_type: `single_stock | compare | sector | macro | screening | deep_screening | portfolio | quant | industry_report | watchlist_brief | event_interpretation | dd | custom`
   - 라우팅 힌트: 공시 1건 해석("이 유상증자 무슨 의미야")=`event_interpretation` · 신뢰/리스크 실사("믿어도 되나", 목표가 없음)=`dd` · 둘 다 기업 전체 밸류에이션 요청이면 `single_stock`.
   - context: `{companies: [{name, corp_code?}], focus?, depth?, credits_remaining(preflight값), notes?}`
   - 산출물 Write **3종 전부 의무**: `plan_md` → `$RUN_DIR/_workspace/PLAN.md` · `agents[].brief_md` → `$RUN_DIR/agents/{name}.md` · `validation_checklist_md` → `_workspace/VALIDATION.md`. **fast-path로 brief를 프롬프트에 인라인하더라도 agents/{name}.md 저장은 생략 금지** — finalize 스냅샷·채점·재현성이 이 파일을 요구 (002 회귀: 미저장 → 에이전트 설계 채점 붕괴).
4. **서브에이전트 병렬 발사** — PLAN.md의 T1~T6 필수 턴 시퀀스대로 `general-purpose` + brief 인라인 + 런 컨텍스트(RUN_DIR 절대경로). ∥ 묶음은 반드시 한 메시지에 동시 호출. 서브에이전트는 `mcp__hyean__call_api(_batch)`·`mcp__hyean__get_reference`·WebSearch를 사용. **`.claude/agents/` 레지스트리 절대 경유 금지.**
5. **Data Gate** — 1턴 batched: `ls _workspace/00_raw/` + 각 JSON `json.loads` 유효성(절단 감지). PLAN.md의 게이트/Stop Trigger 표 적용.
6. **분석 → 작성 → 검증** — PLAN.md 순서대로. 작성은 `scripts/assemble_report.py <RUN_DIR> --title "..."`로 조립(citation 토큰 자동 확장), **index.html 단일 산출물**(별도 보고서.md 없음). 검증은 VALIDATION.md 체크리스트를 1회 batched로 (수정 라운드 최대 1회).
7. **finalize** — `bash .claude/skills/financial-harness/scripts/finalize_run.sh <RUN_DIR> "<request>" "<da_note>" "<notes>" "<agents>"` → 이어서 `mcp__hyean__log_run(run_id, request_type, credits_used, duration_s)` (비차단 — 실패해도 런은 성공).
8. **결과 보기 게이트** — `AskUserQuestion`: "완성된 보고서를 브라우저로 열까요?" [Chrome으로 열기 (권장) / 안 열기]. 열기 → `open -a "Google Chrome" "$(pwd)/<RUN_DIR>/index.html"` (실패 시 기본 브라우저 폴백). 배치는 마지막 1회만. headless면 경로만 출력.

한 세션에서 여러 보고서 가능 — session.jsonl은 `.report_start` 타임스탬프 필터로 보고서별 구간 저장(finalize가 처리).

## 3. 파일 규율 (불변 조항)

- **모든 산출물은 `reports/NNN/` 안에만.**
- **무가공 저장 계약**: `call_api*` 결과의 `data` 필드를 **가공 없이** `_workspace/00_raw/{save_as}.json`으로 Write — rcp_no/source_url/quality 필드가 citation 파이프라인(expand_citations.py)의 입력. 재직렬화·필드 선별 금지.
- **대화에 긴 JSON 출력 금지** — 파일로만. 벌크 수집은 반드시 서브에이전트에서.
- **API 호출은 `call_api_batch`로 묶기** (12콜/batch 상한 — 초과 시 분할).
- **Stop Triggers**: 핵심 파일 2+ 누락 / 크레딧 부족 / 에이전트 40턴 초과 → STOP + 사용자 보고.

## 4. 업데이트 ("하네스 업데이트해줘")

- 방법론·API 플랜·에이전트 brief = **서버가 항상 최신** (할 일 없음).
- 이 폴더(로더·scripts·design-kit)만 `git pull`. 충돌 시 재클론: `rm -rf .claude/skills/financial-harness && git clone https://github.com/twiw49/financial-harness.git .claude/skills/financial-harness` — `reports/`는 프로젝트 루트라 무손실.

## 5. 참고

- request_type 13종: §2.3 목록. 새 형태 요청은 `custom`으로 받아 PLAN 골격 위에 즉석 설계.
- `get_reference` 문서 9종: `analysis-quickcard · analysis-framework · hyean-api-guide · api-reference · report-template · web-search-strategy · external-data-sources · multi-company-framework · devils-advocate-guide` (+`section` 파라미터로 헤딩 슬라이스).
- 로컬 잔류 파일: `references/design-cheatsheet.md`(report-writer 필독 — 111KB design-kit 통독 금지), `templates/design-kit.html`, `scripts/`(assemble_report·expand_citations·report_quality_check·finalize_run).
- 하네스 구축/확장 메타 워크플로우는 서비스 저장소 `docs/harness-references/`로 이동 (제품 배포 대상 아님).
