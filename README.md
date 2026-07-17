# Financial Harness

> AI 에이전트가 [Hyean API](https://hyean.io)(교차검증된 한국 기업 재무 데이터)로
> 한국 상장기업 분석 보고서를 생성하는 Claude Code 스킬.
> **v3부터 방법론·데이터는 Hyean MCP 서버가 런타임 제공** — 이 리포는 얇은 로더 + 보고서 조립 도구만 담는다.

## 설치 (v3 — MCP)

```bash
# 1) 새 폴더 (권장)
mkdir my-analysis && cd my-analysis

# 2) 로더 스킬 설치
git clone https://github.com/twiw49/financial-harness.git .claude/skills/financial-harness
cp .claude/skills/financial-harness/settings.template.json .claude/settings.json

# 3) Hyean MCP 서버 연결 (hyean.io 계정으로 브라우저 로그인 — API 키 불필요)
claude mcp add --transport http hyean https://api.hyean.io/mcp

# 4) 실행
claude
# → /mcp → hyean → 브라우저에서 로그인·승인 (최초 1회)
# → "삼성전자 분석해줘"
```

계정이 없다면 승인 화면에서 이메일 인증으로 즉시 생성됩니다 (무료 1,000크레딧/월).

> 기존 프로젝트 폴더에서도 사용 가능합니다. 단, `.claude/settings.json`이 이미 있다면 덮어쓰지 말고 수동 merge 하세요.

> **여러 분석 폴더를 쓴다면**: `claude mcp add`는 기본적으로 실행한 폴더에만 등록됩니다(local scope).
> 컴퓨터의 모든 프로젝트에서 쓰려면 `-s user`를 붙이세요 — `claude mcp add -s user --transport http hyean https://api.hyean.io/mcp`.
> OAuth 로그인은 한 번이면 됩니다 (토큰은 사용자 단위 저장·자동 갱신).

### v2(git clone + .env) 사용자 마이그레이션

공개 전환과 함께 리포 히스토리가 v3 기준으로 재시작되어 v2 클론에서는 `git pull`이 동작하지 않습니다. 재클론하세요:

```bash
rm -rf .claude/skills/financial-harness
git clone https://github.com/twiw49/financial-harness.git .claude/skills/financial-harness
claude mcp add --transport http hyean https://api.hyean.io/mcp
# .env의 HYEAN_API_KEY는 더 이상 필요 없음 (원하면 삭제)
```
`reports/`는 프로젝트 루트에 있으므로 재클론해도 무손실입니다.

### CI / 헤드리스 (브라우저 없는 환경)

```bash
claude mcp add --transport http hyean https://api.hyean.io/mcp \
  --header "Authorization: Bearer $HYEAN_API_KEY"   # hyean.io 대시보드에서 발급한 키
```

## 사용법

Claude Code에서 자연어로 입력하면 스킬이 자동 발동됩니다 — 별도 슬래시 커맨드 불필요.

```
삼성전자 주식의 가치를 분석하고 보고서를 작성해주세요
```

## 무엇이 어디에 있나

| 구성요소 | 위치 | 갱신 |
|---|---|---|
| 분석 방법론·에이전트 정의·API 플랜 | **Hyean MCP 서버** (`get_plan`/`get_reference`) | 자동 (항상 최신) |
| 로더 스킬 (SKILL.md) | 이 리포 | `git pull` |
| 보고서 조립 (`scripts/`, `templates/design-kit.html`, `references/design-cheatsheet.md`) | 이 리포 | `git pull` |
| 산출물 (`reports/NNN/` — 보고서·데이터·세션) | 프로젝트 루트 | — (사용자 소유) |

## 크레딧

분석 1런 ≈ 17크레딧 (표준 단일종목). Free 1,000cr/월 ≈ 58런.
요금·충전: https://hyean.io/pricing

## 산출물 구조

```
reports/001_삼성전자_20260717/
├── index.html            # 최종 보고서 (Citation Drawer — 모든 수치 → DART 원문 추적)
├── _workspace/           # 수집 원본(00_raw) + 분석 중간산출물 + PLAN.md
├── agents/               # 이 런에 사용된 에이전트 정의 스냅샷
└── session.jsonl         # 이 런의 대화 기록
```

## 라이선스

이 리포(로더 스킬·조립 스크립트·디자인 킷)는 [MIT](LICENSE)입니다.
Hyean MCP 서버가 런타임에 제공하는 분석 방법론·데이터는 이 라이선스의 대상이 아니며, [hyean.io](https://hyean.io) 서비스 약관을 따릅니다.
