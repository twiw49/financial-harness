#!/usr/bin/env python3
"""
assemble_report.py — 보고서 HTML 조립기 (보일러플레이트 자동 래핑)
═══════════════════════════════════════════════════════════════════
report-writer가 **본문 콘텐츠 조각**(섹션/표/차트/citation 토큰)만 작성하면,
design-kit.html의 <head> 스타일(1900+줄 CSS) + Chart.js + 4개 <script>(OHLCV/
Citation Drawer/Interactive/TOC)를 자동으로 감싸 완전한 index.html을 만든다.
이어서 expand_citations로 citation 토큰을 일괄 확장한다.

> 목적: report-writer가 매번 111KB design-kit을 읽고 head/CSS/JS 보일러플레이트를
>       손으로 복사하던 작업 제거. 보일러플레이트는 매 보고서 동일(결정적)하므로
>       **렌더 품질은 1:1 보존**. report-writer는 본문(콘텐츠)에만 집중.

사용법:
  python3 assemble_report.py <RUN_DIR> --title "삼성전자 투자분석 보고서" \
      [--body <RUN_DIR>/_workspace/body.html] [--out <RUN_DIR>/index.html] [--no-expand]

본문 파일(body.html) 작성 규칙:
  · <body> 바로 안에 들어갈 콘텐츠만 작성 (DOCTYPE/head/<body>/</body> 쓰지 말 것).
  · 디자인은 design-cheatsheet.md의 컴포넌트 클래스 사용.
  · 수치 출처는 citation 토큰({{h|...}} 등, report-template.md §4) 사용 — 본 스크립트가 확장.
  · 차트는 <canvas id="..."> + 인라인 <script>new Chart(...)</script>로 본문에 포함 가능.
"""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
KIT = SKILL_DIR / "templates" / "design-kit.html"


def check_inline_scripts(body: str):
    """본문 인라인 <script>의 JS 문법을 node --check로 검사.
    inline Chart.js 오타(예: 군더더기 ']')가 SyntaxError를 내면 차트 init이 조용히 실패해
    **빈 캔버스**가 되던 클래스(013 weightDonut)를 조립 시점에 포착한다.
    반환: (errors[(hint, msg)], checked: bool). node 미설치면 checked=False(검사 생략)."""
    scripts = re.findall(r"<script>(.*?)</script>", body, re.S)  # 인라인만(src= 있는 것은 매칭 안 됨)
    if not scripts:
        return [], True
    node = shutil.which("node")
    if not node:
        return [], False
    errors = []
    for idx, js in enumerate(scripts):
        js_clean = re.sub(r"\{\{.*?\}\}", "0", js, flags=re.S)  # citation 토큰은 0으로 치환(문법 오탐 방지)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(js_clean)
            path = tf.name
        try:
            r = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                idm = re.search(r"getElementById\(['\"]([^'\"]+)", js)
                hint = idm.group(1) if idm else f"script#{idx + 1}"
                errline = next((l.strip() for l in r.stderr.splitlines() if "Error" in l), "SyntaxError")
                errors.append((hint, errline))
        finally:
            os.unlink(path)
    return errors, True


def extract_blocks(kit_html: str):
    """design-kit.html에서 <style>…</style>와 모든 <script>…</script>(CDN 제외 인라인) 추출."""
    style_m = re.search(r"<style>.*?</style>", kit_html, re.S)
    style = style_m.group(0) if style_m else ""
    # 인라인 script (src= 없는 것)만 — 단, <style> 블록을 먼저 제거하고 검색한다.
    # design-kit의 CSS 주석에 리터럴 "<script>" 텍스트가 있어(사용법 안내), 이를 그대로
    # 검색하면 non-greedy 매칭이 주석의 <script>부터 본문 첫 실제 </script>까지(=CSS 사본+
    # </head><body>+데모 전체)를 한 덩어리로 삼켜 매 보고서에 죽은 블록이 주입된다.
    kit_no_style = re.sub(r"<style>.*?</style>", "", kit_html, flags=re.S)
    scripts = []
    for m in re.finditer(r"<script>(.*?)</script>", kit_no_style, re.S):
        scripts.append(f"<script>{m.group(1)}</script>")
    # Chart.js CDN
    cdn_m = re.search(r'<script src="[^"]*chart\.js[^"]*"></script>', kit_html)
    cdn = cdn_m.group(0) if cdn_m else \
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
    return cdn, style, scripts


def assemble(title: str, body: str, kit_html: str) -> str:
    cdn, style, scripts = extract_blocks(kit_html)
    scripts_joined = "\n".join(scripts)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{cdn}
{style}
</head>
<body>
{body}
{scripts_joined}
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-expand", action="store_true", help="citation 토큰 확장 생략")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    body_file = Path(args.body) if args.body else run_dir / "_workspace" / "body.html"
    out_file = Path(args.out) if args.out else run_dir / "index.html"

    if not KIT.exists():
        print(f"✗ design-kit 없음: {KIT}")
        sys.exit(2)
    if not body_file.exists():
        print(f"✗ 본문 파일 없음: {body_file}\n  report-writer가 본문 콘텐츠를 여기에 먼저 작성해야 한다.")
        sys.exit(2)

    kit_html = KIT.read_text()
    body = body_file.read_text()
    out_file.write_text(assemble(args.title, body, kit_html))
    style_kb = len(re.search(r"<style>.*?</style>", kit_html, re.S).group(0)) / 1024
    print(f"✓ 조립 완료: {out_file} ({out_file.stat().st_size/1024:.0f}KB, CSS {style_kb:.0f}KB 인라인)")

    # 인라인 <script> 문법 검사 — 빈 차트(오타로 init 실패) 조립 시 포착
    js_errors, checked = check_inline_scripts(body)
    if js_errors:
        print(f"  ⚠ 인라인 <script> 문법 오류 {len(js_errors)}건 → 해당 차트가 **빈 캔버스**로 뜬다. 반드시 수정:")
        for hint, msg in js_errors:
            print(f"     - {hint}: {msg}")
    elif not checked and re.search(r"<script>", body):
        print("  (node 미설치 — 인라인 스크립트 문법 검사 생략)")

    if args.no_expand:
        print("  (--no-expand: citation 토큰 미확장)")
        return
    # citation 토큰 확장
    sys.argv = ["expand_citations.py", str(run_dir), str(out_file)]
    import importlib.util
    spec = importlib.util.spec_from_file_location("expand_citations", SKILL_DIR / "scripts" / "expand_citations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()  # 자체 종료코드 사용 (미스 시 1)


if __name__ == "__main__":
    main()
