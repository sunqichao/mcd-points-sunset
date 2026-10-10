"""把「凭券享 X 元购买」类商品折算成真实净价值。

这一层的存在理由，来自官方自己的两段原文（mall-product-detail 的 note 字段）：

    「凭本券可享受 3.9 元购买圆筒冰淇淋」
    「…是与不参加优惠活动情况下单独购买该产品的常规价格
      （或者其中所含单品的常规单买价总和）相比较」

由此得到唯一正确的算式：

    一张券的价值 = 券内所含单品的常规菜单价合计 − 凭券实际支付的现金

常见误区：直接拿券面价（官方文档里的 extTradePrice，也就是名字里那个「3.9 元」）
当价值。那是**你还要付出去的钱**，不是你赚到的钱。用它当价值会把性价比夸大数倍。

菜单价取自 query-meals 的真实门店报价，因此同一张券在不同城市的结论可能不同。
无法核到菜单价的商品一律返回 net=None，交由上层标注「无法估值」，绝不臆造。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 组合/套餐类菜名不能当「单品常规价」的子串基准
COMBO_MARKERS = ("套餐", "件套", "组合", "全家", "双人", "三人", "四人", "拼盘", "畅享", "分享")
# 「指定XX任选」意味着内容不确定，无法定出常规价
VAGUE_MARKERS = ("任选", "随机", "指定口味", "惊喜", "件套")

_NUM_CN = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

# 简称 -> 常见完整叫法，用于消除「菜单简写」与「券/奖品全称」之间的写法差异
_COMMON_ALIASES = {"可乐": "可口可乐"}


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip().replace(",", "").replace("¥", "").replace("元", ""))
    except ValueError:
        return None


def _name_variants(name: str) -> set[str]:
    """同一单品的常见叫法。"""
    variants = {name}
    if "汉堡" in name:
        variants.add(name.replace("汉堡", "堡"))
    elif "堡" in name:
        variants.add(name.replace("堡", "汉堡"))
    return variants


class MenuIndex:
    """门店菜单价格索引：单品名 -> 常规价。"""

    def __init__(self, singles: dict[str, float]) -> None:
        self.singles = dict(singles)
        # 券 / 奖品爱用完整品牌名，菜单爱用简称（「可口可乐」vs「可乐」）。
        # 简称已在菜单里时补登全称，避免因写法差异把确定能算的商品判为无法估值。
        for short, full in _COMMON_ALIASES.items():
            if short in self.singles and full not in self.singles:
                self.singles[full] = self.singles[short]

    @classmethod
    def from_meals(cls, meals_raw: Any) -> "MenuIndex":
        """从 query-meals 的 data.meals 构建索引，只保留单品。"""
        singles: dict[str, float] = {}
        meals = (meals_raw or {}).get("data", {}).get("meals")
        if not isinstance(meals, dict):
            return cls(singles)

        for item in meals.values():
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            price = _to_float(item.get("currentPrice"))
            if not name or price is None:
                continue
            if any(m in name for m in COMBO_MARKERS):
                continue
            # 同一道餐点菜单里写法可能不同（「麦辣鸡腿汉堡」vs 商品名里的「麦辣鸡腿堡」），
            # 两种写法都登记，否则匹配时会白白判成未识别。
            for key in _name_variants(name):
                if key not in singles or price < singles[key]:
                    singles[key] = price

        return cls(singles)
        return cls(singles)


    @property
    def size(self) -> int:
        return len(self.singles)

    def resolve(self, term: str) -> tuple[float, str] | None:
        """把「巨无霸」「中可乐」这类叫法落到菜单单品上。"""
        term = term.strip()
        if not term:
            return None
        if term in self.singles:
            return self.singles[term], term

        candidates = [n for n in self.singles if n in term or term in n]
        if not candidates:
            return None
        # 取最长匹配：最具体的那个才是真正的所指
        best = max(candidates, key=len)
        return self.singles[best], best


def _qty_of(text: str, pos: int) -> int:
    """从 item 出现位置往左找数量，如「2份麦辣鸡翅」「3块」。"""
    head = text[max(0, pos - 6): pos]
    m = re.search(r"(\d+)\s*(?:份|块|件|杯|个|支)", head)
    if m:
        return int(m.group(1))
    for word, num in _NUM_CN.items():
        if head.endswith(f"{word}份") or head.endswith(f"{word}件"):
            return num
    return 1


def parse_bundle(spu_name: str, note: str = "") -> tuple[list[tuple[int, str]], str | None]:
    """解析一张券里到底含哪些单品、各几份。返回 ([(份数, 称呼)...], 无法解析的原因)。"""
    name = str(spu_name or "")
    for marker in VAGUE_MARKERS:
        if marker in name:
            return [], "券内容为「任选」，单品不确定"

    # 优先用官方描述，句式稳定：「含1份巨无霸+1份中可乐」
    if note:
        flat = re.sub(r"<[^>]+>", " ", str(note))
        hits = re.findall(r"(\d+)\s*份\s*([\u4e00-\u9fa5A-Za-z0-9]{2,10}?)(?=[+＋，,、；。\s]|$)", flat)
        if hits:
            # 同一份商品往往在说明里被反复描述（开头承诺一遍、末尾 usage 再写一遍），
            # 按名称去重取最大份数，避免把同一份鸡翅算两次。
            merged: dict[str, int] = {}
            for q, t in hits:
                merged[t] = max(merged.get(t, 0), int(q))
            return [(q, t) for t, q in merged.items()], None

    # 官方描述里没有明确清单，交由上层按商品名兜底（见 parse_from_name）
    return [], "官方描述未给出明确的单品清单"


def parse_from_name(spu_name: str, index: MenuIndex) -> tuple[list[tuple[int, str]], str | None]:
    """从商品名反推所含单品，能被菜单核到的才留下。"""
    name = re.sub(r"^[\d.]+\s*元", "", str(spu_name or "")).strip()
    found: list[tuple[int, str]] = []
    consumed = [False] * len(name)

    # 长的菜单名优先，避免「麦辣鸡腿堡」被「麦辣鸡」截断
    for menu_name in sorted(index.singles, key=len, reverse=True):
        start = 0
        while True:
            pos = name.find(menu_name, start)
            if pos < 0:
                break
            if not any(consumed[pos: pos + len(menu_name)]):
                for i in range(pos, pos + len(menu_name)):
                    consumed[i] = True
                found.append((_qty_of(name, pos), menu_name))
            start = pos + len(menu_name)

    if not found:
        return [], "券内单品在菜单中未匹配到"

    return found, None


def unrecognized_remainder(spu_name: str, matched: Iterable[str]) -> str:
    """剔掉已识别单品后，商品名里还剩什么。

    剩余部分若仍含实词，说明这张券里还有认不出来的东西——
    此时宁可判为「无法估值」，也不能只算一半就标成精确值。
    """
    leftover = re.sub(r"^[\d.]+\s*元", "", str(spu_name or "")).strip()
    for term in sorted(matched, key=len, reverse=True):
        leftover = leftover.replace(term, "")
    # 清掉数量、单位与套餐修饰词，剩下的才是真·未知成分
    leftover = re.sub(r"[\d\s元份件块杯个支两一二三四五六七八九十]", "", leftover)
    for word in ("组合", "套装", "任选", "贴士", "超值"):
        leftover = leftover.replace(word, "")
    return leftover.strip()


def pay_price_from_name(spu_name: str) -> float | None:
    """商品详情没给出 extTradePrice 时，从商品名兜底读券面应付价。

    麦当劳把应付价写进商品名是稳定惯例（「18.8元2份麦辣鸡翅」），
    因此这里作为二级来源使用，一级仍是官方 extTradePrice 字段。
    """
    m = re.match(r"^([\d]+(?:\.\d+)?)\s*元", str(spu_name or "").strip())
    return float(m.group(1)) if m else None


def evaluate_coupon(
    spu_name: str,
    pay_price: float | None,
    note: str = "",
    index: MenuIndex | None = None,
) -> tuple[float | None, float | None, str]:
    """折算一张券。返回 (净价值, 常规价合计, 说明)。

    净价值为 None 表示无法定出常规价，调用方应按「无法估值」处理，不要用估算值顶替。
    """
    index = index or MenuIndex({})
    for marker in VAGUE_MARKERS:
        if marker in str(spu_name or ""):
            return None, None, "券内容为「任选」，单品不确定，无法给出精确价值"

    # 优先采信官方说明里的清单；说明里没有时，才退回按商品名推断
    contents, reason = parse_bundle(spu_name, note)
    from_official_note = bool(contents)
    if not contents:
        contents, reason = parse_from_name(spu_name, index)
        if contents:
            # 按名称推断容易「只认出一半」，此时必须判为无法估值：
            # 报一个偏低的精确数字，比直接承认算不出来更有害。
            left = unrecognized_remainder(spu_name, [t for _, t in contents])
            if left:
                return None, None, f"券内含未识别单品「{left}」，无法给出完整价值"
    if not contents:
        return None, None, reason or "未能识别出券内单品"

    regular = 0.0
    detail: list[str] = []
    for qty, term in contents:
        hit = index.resolve(term)
        if hit is None:
            return None, None, f"券内「{term}」在门店菜单中查无此单品"
        price, matched = hit
        regular += price * qty
        detail.append(f"{matched}×{qty}" if qty > 1 else matched)

    pay = _to_float(pay_price)
    if pay is None:
        pay = pay_price_from_name(spu_name)
    if pay is None:
        return None, regular, f"缺少券面应付价（{' + '.join(detail)}）"

    net = round(regular - pay, 2)
    if net <= 0:
        return None, regular, f"常规价 ¥{regular:.1f} − 应付 ¥{pay} 无节省，兑换不划算"
    return net, round(regular, 2), f"常规价 {' + '.join(detail)} ¥{regular:.1f} − 应付 ¥{pay}"


def bundle_regular_price(text: str, index: MenuIndex) -> tuple[float | None, str, str]:
    """把一个名称（券名 / 奖品名）折算成原创价合计。

    返回 (合计, 明细, 原因)；合计为 None 表示算不出来。
    与 evaluate_coupon 共用同一把尺子：**只要还有认不出来的成分就整体判 None**，
    既不捏造，也不含糊 —— 「麦香鱼三件套」不能只算麦香鱼就报出精确值。
    """
    for marker in VAGUE_MARKERS:
        if marker in str(text or ""):
            return None, "", f"内容含「{marker}」，单品不确定"

    items, reason = parse_from_name(text, index)
    if not items:
        return None, "", reason or "所含单品在菜单中未匹配到"

    left = unrecognized_remainder(text, [t for _, t in items])
    # 规格修饰词（大杯 / 中份…）不算未知成分
    left = re.sub(r"[大中小纯]", "", left)
    if left:
        return None, "", f"含未识别成分「{left}」，只算一半会低估，故不估值"

    total = 0.0
    detail: list[str] = []
    for qty, term in items:
        hit = index.resolve(term)
        if hit is None:
            return None, "", f"「{term}」在门店菜单中查无此单品"
        price, matched = hit
        total += price * qty
        detail.append(f"{matched}×{qty}" if qty > 1 else matched)
    return round(total, 2), " + ".join(detail), ""


def parse_prize_value(
    name: str,
    index: MenuIndex | None = None,
    point_vpp_per_1k: float | None = None,
) -> tuple[float | None, str]:
    """给单个奖品估价。返回 (价值元, 依据)；估不出来返回 (None, 原因)。

    官方 GraphQL 只给 name / imageUrl / typeText，**不公布任何概率**，
    也没有 value 字段，所以价值只能按奖品名称里的规则反推。
    """
    index = index or MenuIndex({})
    name = str(name or "").strip()

    # 「下单立减3元券」「苹板支撑四件套立减8元券」——直接等于减的钱
    m = re.search(r"立减\s*(\d+(?:\.\d+)?)\s*元", name)
    if m:
        return float(m.group(1)), f"券面明示立减 ¥{m.group(1)}"

    # 「大杯可口可乐3.6元优惠券」——付 X 元买某样东西，省下的是差价
    m = re.search(r"^(.*?)(\d+(?:\.\d+)?)元优惠券$", name)
    if m:
        regular, detail, why = bundle_regular_price(m.group(1).strip(), index)
        if regular is None:
            return None, why
        pay = float(m.group(2))
        if regular <= pay:
            return None, f"{detail} 常规价 ¥{regular} 不超过应付 ¥{pay}"
        return round(regular - pay, 2), f"{detail} 常规价 ¥{regular} − 应付 ¥{pay}"

    # 「麦辣鸡腿汉堡5折优惠券」——省下的是打折的那部分，基准仍是真实菜单价
    m = re.search(r"^(.*?)(\d+(?:\.\d+)?)折优惠券$", name)
    if m:
        regular, detail, why = bundle_regular_price(m.group(1).strip(), index)
        if regular is None:
            return None, why
        zhe = float(m.group(2))
        saved = round(regular * (1 - zhe / 10), 2)
        return saved, f"{detail} 常规价 ¥{regular} 的 {(10 - zhe) / 10:.0%} 折扣部分"

    # 「28会员积分」——奖品就是积分，价值由本工具自己算出的 VPP 决定
    m = re.match(r"^(\d+)\s*会员积分$", name)
    if m:
        pts = int(m.group(1))
        if point_vpp_per_1k:
            return round(pts * point_vpp_per_1k / 1000, 2), f"{pts} 积分按本单位价值折算"
        return None, "缺少单位积分价值基准"

    return None, "奖品为权益类，无法折算成确定金额"


def estimate_prize_pool(
    prizes_raw: Iterable[dict],
    index: MenuIndex | None = None,
    point_vpp_per_1k: float | None = None,
) -> tuple[list, list[dict]]:
    """在官方未公布概率的前提下给奖品池估价。

    返回 (可估价的 Prize 列表, 全部奖品的明细)。
    概率一律按**等概率**假设填 1/n —— 这只是为了让期望值有得可算，
    不代表真实概率，调用方必须在结论里写明这一点。
    """
    from liquidator import Prize

    details: list[dict] = []
    valued: list[tuple[str, float, str]] = []
    for item in prizes_raw or []:
        name = str((item or {}).get("name") or "").strip()
        if not name:
            continue
        value, why = parse_prize_value(name, index, point_vpp_per_1k)
        details.append({"name": name, "value": value, "reason": why})
        if value is not None:
            valued.append((name, value, why))

    if not valued:
        return [], details

    prob = 1.0 / len(valued)
    pool = [
        Prize(name=name, value_cny=value, probability=prob)
        for name, value, _ in valued
    ]
    return pool, details


def pick_store(client, city: str = "上海", keyword: str = "麦当劳") -> tuple[str, str]:
    """挑一家门店用于取菜单价。返回 (storeCode, storeName)。"""
    raw = client.call_tool(
        "query-nearby-stores", {"beType": 1, "searchType": 2, "city": city, "keyword": keyword}
    )
    rows = (raw or {}).get("data")
    rows = rows if isinstance(rows, list) else []
    if not rows:
        raise RuntimeError(f"未能在「{city}」搜到门店，可换一个城市试试")
    return str(rows[0].get("storeCode")), str(rows[0].get("storeName"))
