"""由清算报告生成自包含的可视化 Demo。

产出 demo/index.html —— 零外部依赖（无 CDN、无 fetch、无需起服务），
双击即可在浏览器中打开，便于评审者与开发者直接查看。

用法：
    python3 src/build_demo.py                 # 用演示数据生成
    python3 src/build_demo.py --real          # 真实调用 MCP 后生成
    python3 src/build_demo.py --report x.json # 从已有报告生成
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from pipeline import build_report  # noqa: E402
from sample_data import MOCK_ACCOUNT, MOCK_LOTTERY, MOCK_PRODUCTS  # noqa: E402

PROFILES = ["conservative", "balanced", "aggressive"]
TEMPLATE_PATH = os.path.join(ROOT, "demo", "template.html")
OUTPUT_PATH = os.path.join(ROOT, "demo", "index.html")


def load_reports(args: argparse.Namespace) -> dict:
    if args.report:
        with open(args.report, encoding="utf-8") as fh:
            base = json.load(fh)
        single = {p: base for p in PROFILES}
        return single

    if args.real:
        from pipeline import fetch_from_mcp

        raw = fetch_from_mcp()
    else:
        raw = (MOCK_ACCOUNT, MOCK_PRODUCTS, MOCK_LOTTERY, {})

    reports = {}
    for profile in PROFILES:
        reports[profile] = build_report(*raw, profile=profile, budget_override=args.budget)
    return reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="真实调用麦当劳 MCP")
    parser.add_argument("--report", default=None, help="从指定 report.json 生成")
    parser.add_argument("--budget", type=int, default=None)
    parser.add_argument("--out", default=OUTPUT_PATH)
    args = parser.parse_args()

    reports = load_reports(args)

    with open(TEMPLATE_PATH, encoding="utf-8") as fh:
        template = fh.read()

    payload = json.dumps(reports, ensure_ascii=False)
    source = "real" if (args.real or args.report) else "mock"
    html = template.replace("__REPORT_DATA__", payload).replace("__SOURCE__", source)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)

    size_kb = len(html.encode("utf-8")) / 1024
    print(f"已生成 {args.out}（{size_kb:.1f} KB，自包含，可直接双击打开）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
