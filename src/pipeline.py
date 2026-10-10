"""麦麦积分清算局 · 主流程。

     python3 src/pipeline.py            # 真实调用 MCP（需 MCD_MCP_TOKEN）
     python3 src/pipeline.py --mock     # 免 Token 演示模式
     python3 src/pipeline.py --profile aggressive
     python3 src/pipeline.py --budget 8000

安全默认值：
- 只读。永远只调用查询类工具，**不会**触发展开 mall-create-order / draw-lottery
- 若要真正下单/抽奖，必须显式加 --execute --i-know-this-costs-points 两道开关
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def load_dotenv(root: str = ROOT) -> None:
    """读取仓库根目录的 .env（零第三方依赖）。

    已存在的同名环境变量优先，避免覆盖 CI / shell 中显式注入的值。
    """
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    except OSError:
        pass


load_dotenv()

from adapters import (  # noqa: E402
    extract_account,
    extract_expire_date,
    extract_lottery,
    extract_products,
)
from liquidator import (  # noqa: E402
    DEFAULT_PROFILE,
    Plan,
    Verdict,
    assess_lottery,
    decide,
    expiry_urgency,
    global_fallback_vpp,
    optimize_plan,
    value_products,
)
from sample_data import MOCK_ACCOUNT, MOCK_LOTTERY, MOCK_PRODUCTS  # noqa: E402

READ_ONLY_TOOLS = ("query-my-account", "mall-points-products", "query-lottery-info", "now-time-info")
WRITE_TOOLS = ("mall-create-order", "draw-lottery")


def fetch_from_mcp() -> tuple[dict, dict, dict, dict]:
    """拉取清算所需的四份真实数据。"""
    from mcp_client import McpError, connect

    client = connect()
    available = {t.get("name") for t in client.list_tools()}
    missing = [t for t in READ_ONLY_TOOLS if t not in available]
    if missing:
        raise RuntimeError(f"当前 MCP Token 未提供以下工具：{missing}")

    return (
        client.call_tool("query-my-account"),
        client.call_tool("mall-points-products"),
        client.call_tool("query-lottery-info"),
        client.call_tool("now-time-info"),
    )


def build_report(
    account_raw: dict,
    products_raw: dict,
    lottery_raw: dict,
    time_raw: dict,
    *,
    profile: str = DEFAULT_PROFILE,
    budget_override: int | None = None,
    include_estimated: bool = False,
) -> dict:
    """纯函数式地组装清算报告，便于离线测试与 Demo 复用。"""
    warnings: list[str] = []

    products = extract_products(products_raw, warnings)
    account = extract_account(account_raw, warnings)
    prizes, cost = extract_lottery(lottery_raw, warnings)
    expire_date = extract_expire_date(time_raw) or extract_expire_date(account_raw)

    # 清算预算：优先用「即将过期积分」，没有则退回到可用积分
    budget = budget_override or account.expiring_soon or account.available

    fallback = global_fallback_vpp(products)
    valued = value_products(products, fallback_vpp=fallback)

    lottery = assess_lottery(prizes, cost) if (prizes and cost) else None
    verdict: Verdict = decide(valued, lottery, profile)
    plan: Plan = optimize_plan(budget, valued, include_estimated=include_estimated)

    days_left = _days_until(expire_date)
    urgency, urgency_msg = expiry_urgency(days_left)

    ranked = sorted(
        (v for v in valued if v.basis != "unknown"),
        key=lambda v: v.vpp,
        reverse=True,
    )

    return {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "profile": profile,
            "mode": "dry-run",
            "include_estimated": include_estimated,
            "budget_mode": "override" if budget_override else ("expiring" if account.expiring_soon else "available"),
            "tools_used": list(READ_ONLY_TOOLS),
        },
        "account": {
            "available": account.available,
            "expiring_soon": account.expiring_soon,
            "frozen": account.frozen,
            "total": account.total,
            "budget": budget,
            "expire_date": expire_date,
            "days_left": days_left,
            "urgency": urgency,
            "urgency_message": urgency_msg,
        },
        "products": [
            {
                "name": vp.product.name,
                "points": vp.product.points_price,
                "cash": vp.product.cash_price,
                "category": vp.product.category,
                "stock": vp.product.stock,
                "vpp_per_1k": vp.vpp_per_1k,
                "basis": vp.basis,
                "note": vp.note,
            }
            for vp in ranked
        ],
        "lottery": (
            {
                "cost_points": lottery.cost_points,
                "ev_per_1k": lottery.ev_per_1k,
                "pessimistic_per_1k": lottery.pessimistic_per_1k,
                "optimistic_per_1k": lottery.optimistic_per_1k,
                "uncertainty": lottery.scenario.get("uncertainty"),
                "prize_count": len(prizes),
            }
            if lottery
            else None
        ),
        "verdict": {
            "recommend_exchange": verdict.recommend_exchange,
            "reason": verdict.reason,
            "lottery_verdict": verdict.lottery_verdict,
            "best_product": verdict.best_product.product.name if verdict.best_product else None,
            "best_vpp_per_1k": round(verdict.best_product.vpp * 1000, 4) if verdict.best_product else None,
        },
        "plan": {
            "budget": plan.budget,
            "total_points": plan.total_points,
            "total_value": plan.total_value,
            "utilization": plan.utilization,
            "leftover": plan.leftover,
            "items": [
                {
                    "name": i.product.name,
                    "points": i.points,
                    "value": i.value,
                    "note": next((v.note for v in valued if v.product is i.product), ""),
                }
                for i in plan.items
            ],
        },
        "watchlist": [
            {
                "name": vp.product.name,
                "points": vp.product.points_price,
                "category": vp.product.category,
                "stock": vp.product.stock,
                "vpp_per_1k": vp.vpp_per_1k,
                "note": vp.note,
            }
            for vp in ranked
            if vp.basis == "category"
        ],
        "warnings": warnings,
    }


def _days_until(date_str: str | None) -> int | None:
    if not date_str:
        return None
    clean = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            target = datetime.strptime(clean, fmt)
        except ValueError:
            continue
        return (target - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    return None


def render_text(report: dict) -> str:
    """终端可读的清算报告。"""
    acc = report["account"]
    lines: list[str] = []
    lines.append("\n" + "=" * 52)
    lines.append("  麦麦积分清算局 · McPoints Sunset")
    lines.append("=" * 52)

    if not isinstance(acc, dict):
        lines.append("账户数据不可用")
        return "\n".join(lines)

    lines.append(f"\n[账户]  可用 {acc['available']}  即将过期 {acc['expiring_soon']}  冻结 {acc['frozen']}")
    lines.append(f"[到期]  {acc.get('expire_date') or '未知'}"
                 f"（{acc.get('days_left') if acc.get('days_left') is not None else '?'} 天后）")
    lines.append(f"[预警]  {acc['urgency_message']}")
    lines.append(f"[预算]  {acc['budget']} 积分 · 模式：{report['meta']['budget_mode']}")

    lines.append("\n-- 单位积分价值排行（元 / 千积分） " + "-" * 16)
    for p in report["products"][:8]:
        flag = "准" if p["basis"] == "cash" else "估"
        lines.append(f"  {p['vpp_per_1k']:>7.2f}  [{flag}]  {p['name']:<16} {p['points']:>6} 分")
    lines.append("  注：[准]=按官方现金价精确折算  [估]=同类目估算")

    lot = report["lottery"]
    if lot:
        lines.append("\n-- 抽奖去路 " + "-" * 40)
        lines.append(f"  单次消耗 {lot['cost_points']} 积分，奖品 {lot['prize_count']} 档")
        lines.append(f"  悲观 {lot['pessimistic_per_1k']:.2f} / 期望 {lot['ev_per_1k']:.2f} "
                     f"/ 乐观 {lot['optimistic_per_1k']:.2f} 元每千积分")

    lines.append("\n-- 决策 " + "-" * 46)
    lines.append(f"  {report['verdict']['lottery_verdict']}")
    lines.append(f"  {report['verdict']['reason']}")

    plan = report["plan"]
    lines.append("\n-- 推荐兑换组合 " + "-" * 38)
    if plan["items"]:
        for it in plan["items"]:
            lines.append(f"  {it['name']:<16} {it['points']:>6} 分   回收约 ¥{it['value']}")
        lines.append(f"  合计 {plan['total_points']}/{plan['budget']} 分 "
                     f"（利用率 {plan['utilization']:.0%}），回收约 ¥{plan['total_value']}")
        if plan["leftover"]:
            lines.append(f"  剩余 {plan['leftover']} 分无高价值去路，可保留或等待新上架商品")
    else:
        lines.append("  预算内无可兑换的高价值商品")

    watchlist = report.get("watchlist") or []
    if watchlist:
        lines.append("\n-- 待定清单：无官方现金价，交给你判断 " + "-" * 6)
        lines.append("  左侧数值为同类目推算值，未参与上方的自动择优")
        for w in watchlist[:6]:
            lines.append(f"  ≈{w['vpp_per_1k']:>7.2f}      {w['name']:<16} {w['points']:>6} 分")
        if not report["meta"].get("include_estimated"):
            lines.append("  如需让它们参与择优，请加 --include-estimated")

    if report["warnings"]:
        lines.append("\n-- 告警 " + "-" * 46)
        for w in report["warnings"]:
            lines.append(f"  ! {w}")

    lines.append("\n本模式为只读预演，未扣除任何积分、未创建任何订单。")
    lines.append("=" * 52 + "\n")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦积分清算局")
    parser.add_argument("--mock", action="store_true", help="使用样例数据演示，无需 MCP Token")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        choices=["conservative", "balanced", "aggressive"], help="风险偏好")
    parser.add_argument("--budget", type=int, default=None, help="覆盖清算预算（积分）")
    parser.add_argument("--include-estimated", action="store_true",
                        help="允许估算价值的商品参与背包择优（默认只使用有官方现金价的商品）")
    parser.add_argument("--json", default=None, help="将报告写入指定 JSON 文件")
    parser.add_argument("--execute", action="store_true", help="允许执行写操作（下单/抽奖）")
    parser.add_argument("--i-know-this-costs-points", action="store_true",
                        help="二次确认：我知晓这将真实消耗积分")
    args = parser.parse_args()

    if args.execute and not (args.mock or args.i_know_this_costs_points):
        print("拒绝执行：写操作需同时提供 --execute 与 --i-know-this-costs-points。")
        print("真实积分一旦扣除不可撤销，请先确认推荐的兑换组合。")
        return 2
    if args.execute and not args.mock:
        print("写操作尚未在本版本中开放，当前版本仅做只读清算与预演。")
        return 2

    try:
        if args.mock:
            raw = (MOCK_ACCOUNT, MOCK_PRODUCTS, MOCK_LOTTERY, {})
        else:
            raw = fetch_from_mcp()
    except Exception as exc:  # noqa: BLE001
        print(f"数据获取失败：{exc}")
        print("提示：若尚未申请 MCP Token，可先运行 --mock 查看效果。")
        return 1

    report = build_report(
        *raw,
        profile=args.profile,
        budget_override=args.budget,
        include_estimated=args.include_estimated,
    )
    print(render_text(report))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"报告已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
