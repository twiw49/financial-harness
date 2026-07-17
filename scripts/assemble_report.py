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
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
KIT = SKILL_DIR / "templates" / "design-kit.html"


def extract_blocks(kit_html: str):
    """design-kit.html에서 <style>…</style>와 모든 <script>…</script>(CDN 제외 인라인) 추출."""
    style_m = re.search(r"<style>.*?</style>", kit_html, re.S)
    style = style_m.group(0) if style_m else ""
    # 인라인 script (src= 없는 것)만
    scripts = []
    for m in re.finditer(r"<script>(.*?)</script>", kit_html, re.S):
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
