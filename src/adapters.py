"""容错提取器：把麦当劳 MCP 的原始响应规整成算法需要的结构。

为什么这样做：
MCP 工具返回的是供 LLM 阅读的文本/JSON，字段名未在本项目文档中固化。
硬编码字段名会在官方调整结构时立刻崩掉，因此这里用「键名候选 + 递归搜索」，
优先匹配候选键，其次按常见命名后缀推断，实在找不到才跳过并留下告警。

所有 *_warnings 都会出现在最终报告里，不会静默吞掉问题。
"""

from __future__ import annotations

from typing import Any

from liquidator import Account, Prize, Product

# 键名候选：按置信度从高到低
KEYS: dict[str, tuple[str, ...]] = {
    "id": ("productId", "product_id", "id", "skuId", "sku_id", "itemId", "goodsId"),
    "name": ("productName", "product_name", "name", "title", "goodsName", "couponName", "prizeName"),
    "points": ("pointPrice", "points_price", "needPoint", "need_point", "points",
               "point", "exchangePoint", "exchange_point", "score", "costPoint"),
    "cash": ("cashPrice", "cash_price", "price", "salePrice", "sale_price",
             "rmbPrice", "rmb_price", "amount", "amountYuan", "marketPrice", "value"),
    "stock": ("stock", "remainStock", "remain_stock", "stockNum", "stock_num",
              "quantity", "remainQuantity", "availableStock"),
    "category": ("category", "categoryName", "category_name", "type", "typeName", "tagName"),
    "probability": ("probability", "rate", "winRate", "win_rate", "chance", "odds"),
    "value": ("value", "valueYuan", "price", "marketPrice", "worth", "amount"),
    "expiring": ("expiringSoon", "expiring_soon", "willExpire", "will_expire",
                 "expirePoint", "expire_point", "soonExpire"),
    "available": ("availablePoint", "available_point", "available", "usablePoint",
                  "usable_point", "balance", "pointBalance"),
    "frozen": ("frozenPoint", "frozen_point", "frozen", "freezePoint"),
    "total": ("totalPoint", "total_point", "accumulatePoint", "total", "cumulativePoint"),
    "date": ("expireDate", "expire_date", "expiryDate", "validUntil", "endTime", "expireTime"),
    "cost": ("costPoint", "cost_point", "consumePoint", "perDraw", "needPoint", "pointPerDraw",
             "singleCost", "drawCost"),
}


def _pick(obj: dict[str, Any], field: str) -> Any:
    src = {str(k).lower(): v for k, v in obj.items()}
    for key in KEYS[field]:
        if key.lower() in src and src[key.lower()] not in (None, ""):
            return src[key.lower()]
    return None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        try:
            return int(float(s))
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("¥", "").replace("元", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def iter_dicts(node: Any, depth: int = 0):
    """深度优先遍历所有 dict 节点。"""
    if depth > 8:
        return
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from iter_dicts(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from iter_dicts(v, depth + 1)


def extract_products(raw: Any, warnings: list[str]) -> list[Product]:
    """从 mall-points-products / mall-product-detail 响应中提取商品。"""
    products: list[Product] = []
    seen: set[str] = set()

    for node in iter_dicts(raw):
        name = _pick(node, "name")
        points = _to_int(_pick(node, "points"))
        # 商品行必须同时有名字和积分价，否则视为容器节点跳过
        if not isinstance(name, str) or not name.strip() or points is None or points <= 0:
            continue
        pid = str(_pick(node, "id") or name)
        if pid in seen:
            continue
        seen.add(pid)

        cash = _to_float(_pick(node, "cash"))
        stock = _to_int(_pick(node, "stock")) or 0
        category = _pick(node, "category")
        category = str(category) if isinstance(category, str) and category.strip() else "其他"

        products.append(
            Product(
                product_id=pid,
                name=name.strip(),
                points_price=points,
                cash_price=cash if (cash is not None and cash > 0) else None,
                category=category,
                stock=stock,
            )
        )

    if not products:
        warnings.append("未能从麦麦商城响应中解析出任何商品，请检查 Token 权限或工具返回结构。")
    return products


def extract_account(raw: Any, warnings: list[str]) -> Account:
    """从 query-my-account 响应中提取积分账户快照。"""
    acc = Account()
    for node in iter_dicts(raw):
        available = _to_int(_pick(node, "available"))
        if available is not None:
            acc.available = available
            acc.expiring_soon = _to_int(_pick(node, "expiring")) or 0
            acc.frozen = _to_int(_pick(node, "frozen")) or 0
            acc.total = _to_int(_pick(node, "total")) or available
            return acc
    warnings.append("未能解析积分账户，后续将以「仅估算商品性价比」模式继续。")
    return acc


def extract_expire_date(raw: Any) -> str | None:
    """从 now-time-info 或账户响应中抓取到期日字符串。"""
    for node in iter_dicts(raw):
        d = _pick(node, "date")
        if isinstance(d, str) and d.strip():
            return d.strip()
    return None


def extract_lottery(raw: Any, warnings: list[str]) -> tuple[list[Prize], int | None]:
    """从 query-lottery-info 中提取奖品池与单次消耗积分。"""
    prizes: list[Prize] = []
    cost: int | None = None

    for node in iter_dicts(raw):
        c = _to_int(_pick(node, "cost"))
        if c is not None and c > 0 and cost is None:
            cost = c

    for node in iter_dicts(raw):
        name = _pick(node, "name")
        if not isinstance(name, str) or not name.strip():
            continue
        value = _to_float(_pick(node, "value"))
        prob = _to_float(_pick(node, "probability"))
        qty = _to_int(_pick(node, "stock"))
        # 概率字段通常是比例（0-1）或百分比（0-100），统一到 0-1
        if prob is not None and prob > 1:
            prob = prob / 100.0
        if value is None and prob is None and qty is None:
            continue
        prizes.append(
            Prize(name=name.strip(), value_cny=value, probability=prob, quantity=qty)
        )

    if not prizes:
        warnings.append("未从积分抽奖活动中解析到奖品列表，抽奖对比将跳过。")
    return prizes, cost
