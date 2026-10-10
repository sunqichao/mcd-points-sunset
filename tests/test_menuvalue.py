"""券价折算层的断言测试（纯离线，不联网）。

重点验证「不能把券面价当成价值」这条业务规则在各种输入下都不跑偏。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from menuvalue import (  # noqa: E402
    MenuIndex,
    evaluate_coupon,
    parse_bundle,
    pay_price_from_name,
    unrecognized_remainder,
)

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
    else:
        FAILED += 1
        print(f"  FAIL {label}  {detail}")


# 一张贴近真实门店的迷你菜单
INDEX = MenuIndex(
    {
        "巨无霸": 25.5,
        "可乐": 9.5,
        "麦辣鸡翅": 15.0,
        "板烧鸡腿堡": 23.5,
        "麦辣鸡腿汉堡": 22.5,
        "麦乐鸡": 14.0,
        "薯条": 13.5,
    }
)

PRICE_INDEX = INDEX.singles  # 期望值时直接从同一份菜单取，避免两处硬编码

# 7 个菜单单品 + 1 个自动补登的品牌全称（可口可乐）
check("菜单索引大小", INDEX.size == 8, str(INDEX.size))

# ---------- 券面应付价识别 ----------
check("名称读券价", pay_price_from_name("18.8元2份麦辣鸡翅") == 18.8)
check("名称无券价", pay_price_from_name("麦麦脆汁鸡两件套") is None)

# ---------- 官方说明解析 ----------
contents, reason = parse_bundle("21.9元巨无霸可乐组合", "凭本券可享受21.9元购买巨无霸可乐组合。本券套餐含1份巨无霸+1份中可乐，不可变更。")
check("说明解析出两个单品", len(contents) == 2, str(contents))
check("巨无霸 1 份", ("巨无霸", 1) in [(t, q) for q, t in contents], str(contents))

# 同一份内容在说明里被重复描述，不能叠加计数
repeat = "本券含2份麦辣鸡翅。使用规则：凭本券可购买2份麦辣鸡翅，每笔订单限用一张。"
contents2, _ = parse_bundle("16.9元2份麦辣鸡翅", repeat)
total = dict((t, q) for q, t in contents2).get("麦辣鸡翅")
check("重复描述不重复计数", total == 2, f"got {total}")

# ---------- 核心业务规则 ----------
net, regular, note = evaluate_coupon("21.9元巨无霸可乐组合", 21.9, "含1份巨无霸+1份中可乐", INDEX)
check("巨无霸可乐组合常规价", regular == 35.0, f"{regular}")
check("巨无霸可乐组合净价值", net == 13.1, f"{net}")

# 券面价不是价值
net2, _, _ = evaluate_coupon("3.9元圆筒冰淇淋", 3.9, "", INDEX)
check("无菜单价无法估值", net2 is None)

# 券面价等于常规价时不该给出正收益
net3, _, why3 = evaluate_coupon("25.5元巨无霸", 25.5, "含1份巨无霸", INDEX)
check("无节省应判为空", net3 is None, f"{net3}")
check("无节省有说明", "无节省" in str(why3), str(why3))

# 只有一半能认出来时必须判无法估值，不得给出偏低的精确值
net4, _, why4 = evaluate_coupon("6.9元可乐麦炫酷", 6.9, "", INDEX)
check("半认出不得估值", net4 is None, f"{net4}")
check("半认出有原因", "未识别" in str(why4), str(why4))

# 「任选」类内容不确定
net5, _, why5 = evaluate_coupon("5.9元香芋派/菠萝派任选", 5.9, "", INDEX)
check("任选不估值", net5 is None)

# 名称兜底：详情没给 extTradePrice 时也要能算
net6, regular6, _ = evaluate_coupon("22.9元2份板烧鸡腿堡", None, "", INDEX)
check("名称兜底券价", net6 == 24.1, f"{net6}")
check("名称兜底常规价", regular6 == 47.0, f"{regular6}")

# 数量翻倍
_, regular7, _ = evaluate_coupon("16.9元2份麦辣鸡翅", 16.9, "", INDEX)
check("2份按双倍计价", regular7 == 30.0, f"{regular7}")

# ---------- 残词识别 ----------
check("全部认出无残词", unrecognized_remainder("巨无霸可乐组合", ["巨无霸", "可乐"]) == "")
check("认出部分留残词", unrecognized_remainder("可乐麦炫酷", ["可乐"]) == "麦炫酷")

# ---------- 抽奖奖品估价（与券同一把尺子）----------
from menuvalue import parse_prize_value  # noqa: E402

# 立减券：面额即价值，不需要任何假设
v1, why1 = parse_prize_value("苹板支撑四件套立减8元券", INDEX)
check("立减券按面额", v1 == 8.0, f"{v1}")

# 折扣券：按真实菜单价折算「省下的那部分」，不是拍脑袋
v2, why2 = parse_prize_value("麦辣鸡腿汉堡5折优惠券", INDEX)
check("折扣券按菜单价", v2 == round(PRICE_INDEX["麦辣鸡腿汉堡"] * 0.5, 2), f"{v2} / {why2}")

# 组合类奖品必须按完整内容核价，只算一个单品属于低估
v3, why3 = parse_prize_value("麦辣鸡翅麦乐鸡6.8折优惠券", INDEX)
expect3 = round((PRICE_INDEX["麦辣鸡翅"] + PRICE_INDEX["麦乐鸡"]) * 0.32, 2)
check("组合奖品不得只算一件", v3 == expect3, f"{v3} != {expect3} / {why3}")

# 「件套」内容不确定 —— 宁可不算，也不能猜
v4, why4 = parse_prize_value("麦香鱼三件套4.5折优惠券", INDEX)
check("件套类拒绝估值", v4 is None, f"{v4}")
check("件套类有原因", "件套" in str(why4), str(why4))

# 「双重」意味着数量不明，同样拒绝
v5, why5 = parse_prize_value("双重麦乐鸡6.8折优惠券", INDEX)
check("数量不明拒绝估值", v5 is None, f"{v5}")

# 菜单里写简写、券里写全称时要能对齐
v6, why6 = parse_prize_value("大杯可口可乐3.6元优惠券", INDEX)
check("全称简称对齐", v6 == round(PRICE_INDEX["可乐"] - 3.6, 2), f"{v6} / {why6}")

# 积分类奖品用本工具自己算出的单位价值折算
v7, _ = parse_prize_value("28会员积分", INDEX, point_vpp_per_1k=50.0)
check("积分奖品自洽折算", v7 == 1.4, f"{v7}")

print("=" * 46)
print(f"通过 {PASSED} 项，失败 {FAILED} 项")
print("=" * 46)
raise SystemExit(1 if FAILED else 0)
