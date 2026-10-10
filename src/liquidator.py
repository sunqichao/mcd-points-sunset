"""麦麦积分清算局 · 核心估值与优化算法。

三层结构（与 MCP 调用层完全解耦，可离线测试）：

    1. 估值层  Valuation     把每个积分去路折算成「单位积分的人民币价值」
    2. 择优层  Optimization  背包 DP，在即将过期积分预算内最大化回收价值
    3. 决策层  Decision      抽奖期望值 vs 确定兑换，按风险偏好给出结论

设计原则：
- 能精确算的精确算，不能精确算的**明确标注估算**，不假装算得准
- 任何涉及扣分/下单的动作都不在本模块触发，本模块只产出「建议」
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------- 风险偏好档位

RiskProfile = dict[str, float]

RISK_PROFILES: dict[str, RiskProfile] = {
    #               溢价系数  不确定度惩罚
    "conservative": {"premium": 0.20, "uncertainty_penalty": 0.90},
    "balanced": {"premium": 0.08, "uncertainty_penalty": 0.50},
    "aggressive": {"premium": 0.00, "uncertainty_penalty": 0.15},
}

DEFAULT_PROFILE = "balanced"


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class Product:
    """麦麦商城商品。points_price 为积分兑换价，cash_price 为纯现金购买价。"""

    product_id: str
    name: str
    points_price: int
    cash_price: float | None = None
    category: str = "其他"
    stock: int = 0

    @property
    def max_buy(self) -> int:
        """本算法默认每种商品只兑换 1 件，避免把预算压在单一商品上。"""
        return 1


@dataclass
class ValuedProduct:
    """已估值的商品。"""

    product: Product
    vpp: float  # 元/积分
    basis: str  # "cash"（有现金价）或 "category"（同类目估算）或 "unknown"
    note: str = ""

    @property
    def vpp_per_1k(self) -> float:
        return round(self.vpp * 1000, 4)

    @property
    def recycle_value(self) -> float:
        """兑换该商品实际「回收」的人民币价值。"""
        if self.basis == "cash":
            return float(self.product.cash_price or 0.0)
        # 估算口径下的名义价值，用于背包排序，不代表真实到手金额
        return round(self.vpp * self.product.points_price, 2)


@dataclass(frozen=True)
class Prize:
    """抽奖奖品。probability 为 None 表示官方未披露概率。"""

    name: str
    value_cny: float | None = None
    probability: float | None = None
    quantity: int | None = None


@dataclass
class LotteryAssessment:
    cost_points: int
    scenario: dict[str, float | None] = field(default_factory=dict)

    # scenario 中三个值统一为「元/积分」口径，per_1k 属性只做 ×1000 放大
    @property
    def ev_per_1k(self) -> float:
        return round((self.scenario.get("expected") or 0.0) * 1000, 4)

    @property
    def pessimistic_per_1k(self) -> float:
        return round((self.scenario.get("pessimistic") or 0.0) * 1000, 4)

    @property
    def optimistic_per_1k(self) -> float:
        return round((self.scenario.get("optimistic") or 0.0) * 1000, 4)


@dataclass
class Account:
    """用户积分账户快照。"""

    available: int = 0
    expiring_soon: int = 0
    frozen: int = 0
    total: int = 0


@dataclass
class PlanItem:
    product: Product
    quantity: int
    points: int
    value: float


@dataclass
class Plan:
    budget: int
    items: list[PlanItem] = field(default_factory=list)

    @property
    def total_points(self) -> int:
        return sum(i.points for i in self.items)

    @property
    def total_value(self) -> float:
        return round(sum(i.value for i in self.items), 2)

    @property
    def utilization(self) -> float:
        return round(self.total_points / self.budget, 4) if self.budget else 0.0

    @property
    def leftover(self) -> int:
        return max(self.budget - self.total_points, 0)


# ---------------------------------------------------------------- 1. 估值层


def estimate_category_vpp(products: Sequence[Product], category: str) -> float | None:
    """用同类目内有现金价的商品，取 VPP 中位数作为该类目的估算基准。"""
    candidates: list[float] = []
    for p in products:
        if p.category != category or p.category == "其他":
            continue
        if p.cash_price and p.points_price > 0:
            candidates.append(p.cash_price / p.points_price)
    if not candidates:
        return None
    candidates.sort()
    mid = len(candidates) // 2
    if len(candidates) % 2 == 1:
        return candidates[mid]
    return (candidates[mid - 1] + candidates[mid]) / 2


def value_products(products: Iterable[Product], fallback_vpp: float | None = None) -> list[ValuedProduct]:
    """为商城商品估值。

    精确口径：同时存在现金价与积分价时，1 积分 = cash_price / points_price 元。
    估算口径：只有积分价时，用同类目中位数；同类目无样本时降级到全局 fallback。
    无样本且无 fallback 时，VPP 记为 0 并标注「无法估值」，绝不臆造数字。
    """
    products = list(products)
    valued: list[ValuedProduct] = []

    for p in products:
        if p.points_price <= 0:
            continue
        if p.cash_price and p.cash_price > 0:
            valued.append(
                ValuedProduct(
                    product=p,
                    vpp=p.cash_price / p.points_price,
                    basis="cash",
                    note="按官方现金价精确折算",
                )
            )
            continue

        cat_vpp = estimate_category_vpp(products, p.category)
        if cat_vpp is not None:
            valued.append(
                ValuedProduct(
                    product=p,
                    vpp=cat_vpp,
                    basis="category",
                    note=f"无现金价，按「{p.category}」同类目中位数估算",
                )
            )
        elif fallback_vpp is not None:
            valued.append(
                ValuedProduct(
                    product=p,
                    vpp=fallback_vpp,
                    basis="category",
                    note="无同类目样本，按全站基准估算（置信度低）",
                )
            )
        else:
            valued.append(
                ValuedProduct(
                    product=p,
                    vpp=0.0,
                    basis="unknown",
                    note="缺少可比价格，无法估值，已排除在推荐之外",
                )
            )
    return valued


def global_fallback_vpp(products: Sequence[Product]) -> float | None:
    """全站 VPP 基准：所有有现金价商品的中位数。"""
    samples = sorted(
        p.cash_price / p.points_price
        for p in products
        if p.cash_price and p.cash_price > 0 and p.points_price > 0
    )
    if not samples:
        return None
    mid = len(samples) // 2
    if len(samples) % 2 == 1:
        return samples[mid]
    return (samples[mid - 1] + samples[mid]) / 2


# ---------------------------------------------------------------- 2. 抽奖期望


def normalize_probabilities(prizes: Sequence[Prize]) -> list[tuple[Prize, float]]:
    """把奖品池规整成 (奖品, 概率) 且概率和为 1。

    优先使用官方披露的概率；若未提供，则用奖品剩余数量的占比作为代理权重，
    并同时返回 lower_confidence 标记（由调用方读取）。
    """
    pool = [p for p in prizes if p.value_cny is not None]
    if not pool:
        return []

    total_p = sum(p.probability for p in pool if p.probability is not None)
    if total_p > 0 and math.isclose(total_p, 1.0, abs_tol=1e-6):
        return [(p, p.probability or 0.0) for p in pool if p.probability is not None]

    known = [(p, p.probability or 0.0) for p in pool if p.probability is not None]
    unknown = [p for p in pool if p.probability is None]

    if not unknown:
        s = sum(w for _, w in known) or 1.0
        return [(p, w / s) for p, w in known]

    total_q = sum(p.quantity or 0 for p in unknown)
    if total_q > 0:
        inferred = [(p, (p.quantity or 0) / total_q) for p in unknown]
    else:
        inferred = [(p, 1.0 / len(unknown)) for p in unknown]

    merged = known + inferred
    s = sum(w for _, w in merged) or 1.0
    return [(p, w / s) for p, w in merged]


def probability_is_disclosed(prizes: Sequence[Prize]) -> bool:
    pool = [p for p in prizes if p.value_cny is not None]
    if not pool:
        return False
    return all(p.probability is not None for p in pool)


def assess_lottery(prizes: Sequence[Prize], cost_points: int) -> LotteryAssessment:
    """三档评估单次抽奖的价值。

    expected    : Σ p_i × v_i                     加权期望
    pessimistic : 按最差档（价值最低且概率非零的奖品）保守估计
    optimistic  : 按最好奖品的加权上界

    官方未披露概率时，uncertainty 提高，交由风险偏好系数向下修正。
    """
    if cost_points <= 0:
        return LotteryAssessment(cost_points=cost_points, scenario={"expected": None,
                                                                    "pessimistic": None,
                                                                    "optimistic": None})
    dist = normalize_probabilities(prizes)
    if not dist:
        return LotteryAssessment(cost_points=cost_points, scenario={"expected": None,
                                                                    "pessimistic": None,
                                                                    "optimistic": None})

    expected = sum(p * (item.value_cny or 0.0) for item, p in dist)
    worst_value = min((item.value_cny or 0.0) for item, _ in dist)
    best_value = max((item.value_cny or 0.0) for item, _ in dist)

    disclosed = probability_is_disclosed(prizes)
    # 概率未知时用「最差结果与期望值的加权」作为悲观估计，避免盲目乐观
    pessimistic = worst_value if disclosed else worst_value * 0.5 + expected * 0.5
    optimistic = max(best_value * dist[0][1] + expected * (1 - dist[0][1]), expected)

    return LotteryAssessment(
        cost_points=cost_points,
        scenario={
            "expected": round(expected / cost_points, 8),
            "pessimistic": round(pessimistic / cost_points, 8),
            "optimistic": round(optimistic / cost_points, 8),
            "uncertainty": 0.25 if disclosed else 0.60,
        },
    )


# ---------------------------------------------------------------- 3. 决策层


@dataclass
class Verdict:
    recommend_exchange: bool
    reason: str
    best_product: ValuedProduct | None
    lottery: LotteryAssessment | None
    lottery_verdict: str
    profile: str


def decide(
    valued: Sequence[ValuedProduct],
    lottery: LotteryAssessment | None,
    profile_name: str = DEFAULT_PROFILE,
) -> Verdict:
    """在有现金价的确定收益 vs 抽奖的期望收益之间做决策。

    抽奖 side 引入两重折扣：
    - uncertainty_penalty：概率未披露时按不确定度打折
    - premium：抽奖必须显著好于确定兑换，才值得承担波动
    """
    profile = RISK_PROFILES.get(profile_name, RISK_PROFILES[DEFAULT_PROFILE])
    usable = [v for v in valued if v.basis == "cash"]
    pool = usable or [v for v in valued if v.basis != "unknown"]

    best = max(pool, key=lambda v: v.vpp, default=None)
    best_vpp = best.vpp if best else 0.0

    if lottery is None or not lottery.scenario.get("expected"):
        return Verdict(
            recommend_exchange=True,
            reason="当前未获取到可评估的抽奖活动，全部按确定兑换处理。",
            best_product=best,
            lottery=None,
            lottery_verdict="无抽奖数据",
            profile=profile_name,
        )

    unc = float(lottery.scenario.get("uncertainty") or 0.0)
    pen = profile["uncertainty_penalty"]
    adjusted_ev = lottery.ev_per_1k / 1000 * (1 - unc * pen)
    threshold = best_vpp * (1 + profile["premium"])

    if adjusted_ev > threshold:
        lottery_verdict = f"抽奖期望 {adjusted_ev * 1000:.2f} 元/千分 > 兑换门槛 {threshold * 1000:.2f} 元/千分，可抽"
        recommend_exchange = False
    else:
        lottery_verdict = (
            f"风险调整后抽奖 {adjusted_ev * 1000:.2f} 元/千分 ≤ 兑换门槛 "
            f"{threshold * 1000:.2f} 元/千分，不划算"
        )
        recommend_exchange = True

    return Verdict(
        recommend_exchange=recommend_exchange,
        reason=f"当前为「{profile_name}」档：不确定度惩罚 {pen:.2f}，溢价要求 {profile['premium']:.0%}。",
        best_product=best,
        lottery=lottery,
        lottery_verdict=lottery_verdict,
        profile=profile_name,
    )


# ---------------------------------------------------------------- 4. 背包择优


def optimize_plan(
    budget: int,
    valued: Sequence[ValuedProduct],
    *,
    include_estimated: bool = False,
    max_items: int = 8,
) -> Plan:
    """在兑换预算内做 0/1 背包，最大化回收价值。

    budget 通常取「即将过期积分」，也可传「可用积分」做全量规划。

    include_estimated（默认 False）是本算法的关键取舍：
    估算价值的商品（无官方现金价）虽然 VPP 可能好看，但那个数字本身是推出来的，
    拿推算值去做最优化，等于用假数字做决策，因此默认只让**有官方现金价**的商品
    进入背包，估算商品另作一张「待定清单」交给人来判断。

    每个商品每种至多 1 件，DP 维度为 (商品数 × 预算)。
    预算对 10 分取整后降维，控制 DP 规模到可接受范围（兑换价通常为整百）。
    """
    if budget <= 0:
        return Plan(budget=budget)

    if include_estimated:
        items = [v for v in valued if v.basis != "unknown" and 0 < v.product.points_price <= budget]
    else:
        items = [v for v in valued if v.basis == "cash" and 0 < v.product.points_price <= budget]
    if not items:
        return Plan(budget=budget)

    step = 10
    scaled_budget = budget // step
    scaled_weight = [max(1, i.product.points_price // step) for i in items]
    values = [i.recycle_value for i in items]

    n = len(items)
    # dp[j] = 前 i 个商品在缩放预算 j 下的最大价值；take 记录是否选取
    dp = [0.0] * (scaled_budget + 1)
    take: list[list[bool]] = [[] for _ in range(n)]

    for i in range(n):
        w = scaled_weight[i]
        v = values[i]
        chosen = [False] * (scaled_budget + 1)
        for j in range(scaled_budget, w - 1, -1):
            candidate = dp[j - w] + v
            if candidate > dp[j]:
                dp[j] = candidate
                chosen[j] = True
        take[i] = chosen

    # 回溯选择路径
    pickup: list[int] = []
    j = scaled_budget
    for i in range(n - 1, -1, -1):
        if j >= scaled_weight[i] and take[i][j]:
            pickup.append(i)
            j -= scaled_weight[i]
    pickup.reverse()

    if max_items > 0 and len(pickup) > max_items:
        # 件数受限时按单件价值保留，避免盲目截断索引丢掉高价值商品
        pickup.sort(key=lambda i: -values[i])
        pickup = pickup[:max_items]
        pickup.sort()

    plan = Plan(budget=budget)
    for i in pickup:
        vp = items[i]
        plan.items.append(
            PlanItem(
                product=vp.product,
                quantity=1,
                points=vp.product.points_price,
                value=round(vp.recycle_value, 2),
            )
        )
    return plan


# ---------------------------------------------------------------- 5. 到期预警


def expiry_urgency(days_left: int | None) -> tuple[str, str]:
    """按剩余天数给出清算紧迫度。"""
    if days_left is None:
        return "unknown", "未获取到到期日，建议主动核实"
    if days_left <= 0:
        return "expired", "积分已过期或当日过期，立即处理"
    if days_left <= 7:
        return "critical", f"仅剩 {days_left} 天，进入强制清算模式"
    if days_left <= 30:
        return "warning", f"剩余 {days_left} 天，建议本周内安排"
    return "safe", f"剩余 {days_left} 天，可从容规划"
