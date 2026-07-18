#!/bin/bash
# 런 마무리 헬퍼: ledger + 스냅샷 + session + 워크벤치 정리 + 재채점
# 사용법(프로젝트 루트에서): bash .claude/skills/financial-harness/scripts/finalize_run.sh [--request-type <type>] <RUN_DIR> "<request>" "<da_note>" "<extra_notes>" "<agent1,agent2,...>"
#   --request-type <type>: 선택. ledger에 request_type 기록 → 채점기가 유형별 루브릭 적용. 생략 시 현행과 동일(하위호환).
#   5번째 위치 인자(사용 에이전트 목록) 생략 시 기존 ledger의 agents[].name에서 유도.
#   둘 다 없으면 .claude/agents 전체 복사 + 경고 (이전 런 에이전트 혼입 위험).
set -e
# 선행 옵션 파싱 (위치 인자 앞의 --플래그만) — 하위호환: 플래그 없으면 기존 위치 인자 그대로
REQUEST_TYPE=""
while [ "${1:0:2}" = "--" ]; do
  case "$1" in
    --request-type) REQUEST_TYPE="$2"; shift 2 ;;
    *) echo "⚠ 알 수 없는 옵션 $1 무시" >&2; shift ;;
  esac
done
RUN="$1"; REQ="$2"; DA="${3:-DA 미발동}"; NOTES="${4:-}"; AGENT_ARG="${5:-}"
START=$(cat "$RUN/_workspace/.report_start" 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)

# 이 런에서 사용한 에이전트 결정: ① 5번째 인자 ② 기존 ledger ③ 전체(경고)
if [ -n "$AGENT_ARG" ]; then
  AGENTS="$AGENT_ARG"
elif [ -f "$RUN/_workspace/CHECKPOINT_LEDGER.json" ]; then
  AGENTS=$(python3 -c "
import json
d=json.load(open('$RUN/_workspace/CHECKPOINT_LEDGER.json'))
names=[a['name'].split('(')[0].strip() for a in d.get('agents',[])]
print(','.join(names))" 2>/dev/null || true)
fi
if [ -z "$AGENTS" ]; then
  AGENTS=$(ls .claude/agents/*.md 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/.md//' | paste -sd, -)
  echo "⚠ 사용 에이전트 목록 미지정 — .claude/agents 전체($AGENTS)를 스냅샷. 이전 런 에이전트 혼입 가능." >&2
fi

# ledger (없으면 생성, 있으면 유지)
if [ ! -f "$RUN/_workspace/CHECKPOINT_LEDGER.json" ]; then
python3 -c "
import json
json.dump({
 'run':'$(basename $RUN)','request':'''$REQ''',
 'data_isolation':'fresh API; no cache reuse',
 'data_gate':{'passed':True,'missing':[],'notes':'''$NOTES'''.split('|') if '''$NOTES''' else []},
 'stop_triggers':[],
 'agents':[{'name':a,'status':'done'} for a in '''$AGENTS'''.split(',') if a],
 'devils_advocate':{'note':'''$DA'''},
 'report_start':'$START'
}, open('$RUN/_workspace/CHECKPOINT_LEDGER.json','w'), ensure_ascii=False, indent=1)
"
fi
# request_type 주입 (선택) — 신규/기존 ledger 모두에 멱등 기록. 채점기가 이 키로 유형별 루브릭 적용.
if [ -n "$REQUEST_TYPE" ] && [ -f "$RUN/_workspace/CHECKPOINT_LEDGER.json" ]; then
python3 -c "
import json
p='$RUN/_workspace/CHECKPOINT_LEDGER.json'
d=json.load(open(p)); d['request_type']='$REQUEST_TYPE'
json.dump(d, open(p,'w'), ensure_ascii=False, indent=1)
print('request_type:', '$REQUEST_TYPE')
"
fi
# .report_end는 최초 finalize 시점 고정 (재실행 시 세션 필터 범위 보존)
[ -f "$RUN/_workspace/.report_end" ] || echo "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" > "$RUN/_workspace/.report_end"
mkdir -p "$RUN/agents" "$RUN/skills"
# 에이전트 스냅샷 — v3: 로더가 get_plan 수신 시 brief를 $RUN/agents/에 이미 Write함.
# 여기서는 존재 확인만 하고, 비어 있으면 구 스킬 라이브러리(v2 잔존 설치) 폴백 복사.
COPIED=$(ls "$RUN/agents"/*.md 2>/dev/null | wc -l | tr -d ' ')
if [ "$COPIED" = "0" ]; then
  AGENT_LIB=".claude/skills/financial-harness/agents"
  for a in $(echo "$AGENTS" | tr ',' ' '); do
    if [ -f "$AGENT_LIB/$a.md" ]; then cp "$AGENT_LIB/$a.md" "$RUN/agents/"; COPIED=$((COPIED+1)); fi
  done
fi
echo "agents snapshot: $COPIED file(s) — $AGENTS"
echo "inline orchestrator. agents=$AGENTS" > "$RUN/skills/README.txt"
PROJ_GLOB=$(pwd | sed "s|/|-|g"); JSONL=$(ls -t ~/.claude/projects/*${PROJ_GLOB##*-}*/*.jsonl 2>/dev/null | head -1)  # 프로젝트 전사본(있으면)
END=$(cat "$RUN/_workspace/.report_end" 2>/dev/null || echo "9999")
python3 -c "
import json
start='$START'; end='$END'; out=[]
for l in open('$JSONL'):
    try:
        ts=json.loads(l).get('timestamp','')
        if start<=ts<=end: out.append(l)
    except: pass
open('$RUN/session.jsonl','w').writelines(out); print('session', len(out))
" 2>/dev/null || true

# ── 리포트 메타 주입 (hyean-web 공유용) ─────────────────────────
# index.html <head>에 hyean-report-meta(JSON) + generator 마커 삽입.
# 서버 업로드 시 이 블록을 파싱해 생성시각/소요시간/에이전트/모델/프롬프트를 표시.
# harness가 '아는' 값만 담는다 (토큰수는 셀프리포트 불가 → 미포함).
HARNESS_VER=$(cat .claude/skills/financial-harness/HARNESS_VERSION 2>/dev/null || echo "unknown")
HV="$HARNESS_VER" RUN="$RUN" START="$START" END="$END" REQ="$REQ" AGENTS="$AGENTS" JSONL="$JSONL" python3 <<'PYEOF' 2>/dev/null || echo "⚠ 메타 주입 스킵 (index.html 미존재 가능)"
import json, os, re, glob, collections
from datetime import datetime

run = os.environ["RUN"]
html_path = os.path.join(run, "index.html")
if not os.path.exists(html_path):
    cands = sorted(glob.glob(os.path.join(run, "*.html")))
    if not cands:
        raise SystemExit("no html")
    html_path = cands[0]

def parse_iso(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None

start, end = parse_iso(os.environ.get("START")), parse_iso(os.environ.get("END"))
duration = int((end - start).total_seconds()) if (start and end and end >= start) else None

# 모델 = session.jsonl(시간필터 산출물) 또는 원본 JSONL의 최빈 model
model = None
sess = os.path.join(run, "session.jsonl")
src = sess if os.path.exists(sess) else (os.environ.get("JSONL") or "")
if src and os.path.exists(src):
    models = []
    for l in open(src, errors="ignore"):
        try:
            m = json.loads(l).get("message", {}).get("model")
            if m:
                models.append(m)
        except Exception:
            pass
    if models:
        model = collections.Counter(models).most_common(1)[0][0]

agents = [a.strip() for a in (os.environ.get("AGENTS") or "").split(",") if a.strip()]
meta = {
    "generator": "financial-harness",
    "harness_version": os.environ.get("HV", "unknown"),
    "generated_at": os.environ.get("END") if end else None,
    "started_at": os.environ.get("START") if start else None,
    "duration_seconds": duration,
    "model": model,
    "agents": agents,
    "agent_count": len(agents),
    "prompt": (os.environ.get("REQ") or "")[:2000],
}
block = (
    '<meta name="generator" content="financial-harness@%s">\n'
    '<script type="application/json" id="hyean-report-meta">%s</script>'
) % (meta["harness_version"], json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))

html = open(html_path, encoding="utf-8").read()
# 멱등: 기존 블록 제거 후 재주입 (finalize 재실행 안전)
html = re.sub(r'<meta name="generator" content="financial-harness@[^"]*">\s*', "", html)
html = re.sub(r'<script type="application/json" id="hyean-report-meta">.*?</script>\s*', "", html, flags=re.DOTALL)
if "</head>" in html:
    html = html.replace("</head>", block + "\n</head>", 1)
else:
    html = block + "\n" + html
open(html_path, "w", encoding="utf-8").write(html)
print("report meta injected:", os.path.basename(html_path),
      "| dur=%ss agents=%d model=%s" % (duration, len(agents), model))
PYEOF

echo "=== 최종 채점: $(basename $RUN) ==="
# 크래시 은폐 금지 — grep 파이프는 채점기 예외를 삼킨다 (RETRO 002 A-1: AttributeError가 무음 통과)
QC_OUT=$(python3 .claude/skills/financial-harness/scripts/report_quality_check.py "$RUN" 2>&1) || {
  RC=$?
  echo "✗ 채점 실패 (exit $RC) — 원문 마지막 15줄:" >&2
  echo "$QC_OUT" | tail -15 >&2
  exit $RC
}
echo "$QC_OUT" | grep -E "Total:|데이터 완전|원문 출처|보고서 품질|API 활용|에이전트 설계"
