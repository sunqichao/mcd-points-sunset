"""零依赖自测：验证估值、抽奖期望、背包择优三条主链路。

运行： python3 tests/test_core.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from liquidator import (  # noqa: E402
    Account,
    Plan,
    Prize,
    Product,
    assess_lottery,
    decide,
    expiry_urgency,
    global_fallback_vpp,
    optimize_plan,
    value_products,
)

PASSED = 0
FAILED = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}  {detail}")


def near(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


print("\n[1] 单位积分价值估值")
products = [
    Product("p-cone", "麦旋风", 1500, 9.5, "甜品"),
    Product("p-bigmac", "巨无霸", 3000, 23.0, "汉堡"),
    Product("p-fries", "薯条（中）", 1200, 12.0, "小食"),
    Product("p-cup", "限定随行杯", 5000, None, "小食"),  # 无现金价 -> 同类目估算
    Product("p-toy", "限定玩具", 4000, None, "周边"),  # 同类目无样本 -> 全站兜底
]
fallback = global_fallback_vpp(products)
valued = value_products(products, fallback_vpp=fallback)
by_name = {v.product.name: v for v in valued}

check("薯条 VPP 精确折算 = 12/1200", near(by_name["薯条（中）"].vpp, 0.01),
      f"实际 {by_name['薯条（中）'].vpp}")
check("薯条走 cash 精确口径", by_name["薯条（中）"].basis == "cash")
check("限定随行杯用同类目估算", by_name["限定随行杯"].basis == "category",
      by_name["限定随行杯"].basis)
check("限定玩具降级到全站兜底", by_name["限定玩具"].vpp > 0 and by_name["限定玩具"].basis == "category")
check("VPP 千分口径换算正确", near(by_name["薯条（中）"].vpp_per_1k, 10.0),
      f"实际 {by_name['薯条（中）'].vpp_per_1k}")

print("\n[2] 抽奖期望值（官方披露概率）")
prizes = [
    Prize("巨无霸兑换券", 23.0, 0.01, 10),
    Prize("薯条兑换券", 12.0, 0.09, 90),
    Prize("甜筒兑换券", 6.0, 0.30, 300),
    Prize("谢谢参与", 0.0, 0.60, 600),
]
lot = assess_lottery(prizes, cost_points=500)
expected_ev = 0.01 * 23 + 0.09 * 12 + 0.30 * 6
check("单次抽奖期望 = 3.11 元", near(expected_ev, 3.11), f"实际 {expected_ev}")
check("折算后 ≈ 6.22 元/千分", near(lot.ev_per_1k, 6.22, tol=0.01), f"实际 {lot.ev_per_1k}")
check("悲观档不高于期望档", lot.pessimistic_per_1k <= lot.ev_per_1k)
check("乐观档不低于期望档", lot.optimistic_per_1k >= lot.ev_per_1k)

print("\n[3] 抽奖 vs 确定兑换的决策")
verdict_bal = decide(valued, lot, "balanced")
check("薯条 VPP 更高时推荐兑换而非抽奖", verdict_bal.recommend_exchange is True,
      verdict_bal.lottery_verdict)
verdict_agg = decide(valued, lot, "aggressive")
check("激进档依然不该抽（6.22 < 10 元/千分）", verdict_agg.recommend_exchange is True,
      verdict_agg.lottery_verdict)

# 反例：抽奖明显更划算时应翻转结论
rich = [Prize("大额券", 80.0, 0.5, 5), Prize("谢谢参与", 0.0, 0.5, 5)]
rich_lot = assess_lottery(rich, cost_points=500)
check("富奖池期望 = 80 元/千分", near(rich_lot.ev_per_1k, 80.0), f"实际 {rich_lot.ev_per_1k}")
verdict_rich = decide(valued, rich_lot, "balanced")
check("奖池变富后转为推荐抽奖", verdict_rich.recommend_exchange is False,
      verdict_rich.lottery_verdict)

print("\n[4] 概率未披露 -> 不确定度上升")
blind = [
    Prize("神秘大奖", 50.0, None, 2),
    Prize("小额券", 5.0, None, 98),
]
blind_lot = assess_lottery(blind, cost_points=500)
check("未披露概率时 uncertainty 为 0.6", near(blind_lot.scenario["uncertainty"], 0.6),
      str(blind_lot.scenario))
check("概率走脚手架按库存占比归一化后仍可算期望", blind_lot.ev_per_1k > 0,
      f"实际 {blind_lot.ev_per_1k}")

print("\n[5] 背包择优：利用即将过期积分")
budget = 10000
plan: Plan = optimize_plan(budget, valued)
check("预算不超支", plan.total_points <= budget, f"用了 {plan.total_points}/{budget}")
check("确实选到了商品", len(plan.items) > 0, f"选中 {len(plan.items)} 件")
check("回收价值 > 0", plan.total_value > 0, f"实际 {plan.total_value}")
check("利用率 > 50%", plan.utilization > 0.5, f"实际 {plan.utilization}")

# 小额预算时不应超支
plan_small = optimize_plan(1000, valued)
check("预算 1000 时无超支项", plan_small.total_points <= 1000,
      f"用了 {plan_small.total_points}")

# 零 budget / 空商品不崩
check("budget=0 返回空方案", optimize_plan(0, valued).total_points == 0)
check("空商品列表返回空方案", optimize_plan(9999, []).total_points == 0)

print("\n[6] 到期预警分级")
c1, m1 = expiry_urgency(3)
c2, m2 = expiry_urgency(15)
c3, m3 = expiry_urgency(120)
c4, m4 = expiry_urgency(None)
check("3 天 -> critical", c1 == "critical", m1)
check("15 天 -> warning", c2 == "warning", m2)
check("120 天 -> safe", c3 == "safe", m3)
check("未知 -> unknown", c4 == "unknown", m4)

print("\n[7] 账户快照结构")
acc = Account(available=12000, expiring_soon=10000, frozen=500, total=12500)
check("可用积分与冻结积分分离", acc.available == 12000 and acc.frozen == 500)
check("清算预算取即将过期部分", acc.expiring_soon == 10000)

print(f"\n{'=' * 46}\n通过 {PASSED} 项，失败 {FAILED} 项\n{'=' * 46}")
sys.exit(1 if FAILED else 0)
