"""演示用样例数据（--mock 模式）。

字段命名刻意做了「混搭」——同一份数据里同时使用 productId / goodsId、
pointPrice / needPoint 等不同写法，用于校验 adapters.py 的容错能力。

⚠️ 以下价格与积分为演示值，仅用于展示算法效果，
   不代表麦当劳中国真实定价。真实数据请在配置 MCP Token 后自动拉取。
"""

from __future__ import annotations

MOCK_ACCOUNT = {
    "code": 0,
    "data": {
        "availablePoint": 12680,
        "expiringSoon": 9200,
        "frozenPoint": 300,
        "totalPoint": 58400,
        "expireDate": "2026-12-31",
    },
}

MOCK_PRODUCTS = {
    "code": 0,
    "data": {
        "list": [
            {"productId": "SKU001", "productName": "麦旋风（奥利奥）", "pointPrice": 950,
             "cashPrice": 9.5, "categoryName": "甜品", "remainStock": 888},
            {"productId": "SKU002", "productName": "薯条（中）", "pointPrice": 1200,
             "cashPrice": 12.0, "categoryName": "小食", "remainStock": 999},
            {"goodsId": "SKU003", "name": "巨无霸", "needPoint": 2500,
             "rmbPrice": 25.0, "category": "汉堡", "stock": 500},
            {"productId": "SKU004", "productName": "板烧鸡腿堡", "pointPrice": 2100,
             "cashPrice": 19.0, "categoryName": "汉堡", "remainStock": 420},
            {"skuId": "SKU005", "title": "麦辣鸡翅（2块）", "pointPrice": 1400,
             "salePrice": 13.0, "typeName": "小食", "stockNum": 300},
            {"productId": "SKU006", "productName": "中杯可乐", "pointPrice": 950,
             "cashPrice": 9.0, "categoryName": "饮料", "remainStock": 1000},
            {"productId": "SKU007", "productName": "麦咖啡拿铁（大）", "pointPrice": 1900,
             "cashPrice": 21.0, "categoryName": "饮料", "remainStock": 260},
            # 下列三项无现金价，用于验证「同类目估算 / 全站兜底」两级降级
            {"goodsId": "SKU008", "name": "限定随行杯", "needPoint": 5600,
             "category": "小食", "stock": 120},
            {"productId": "SKU009", "productName": "薯条造型手机支架", "pointPrice": 7200,
             "categoryName": "周边", "remainStock": 60},
            {"productId": "SKU010", "productName": "麦麦IP Joy 公仔", "pointPrice": 9800,
             "categoryName": "周边", "remainStock": 25},
            {"productId": "SKU011", "productName": "儿童玩具（当季）", "pointPrice": 3900,
             "categoryName": "周边", "remainStock": 80},
            {"productId": "SKU012", "productName": "冰淇淋甜筒", "pointPrice": 620,
             "cashPrice": 6.0, "categoryName": "甜品", "remainStock": 1000},
            # 异常数据：缺积分价，应被算法跳过而非崩溃
            {"productId": "SKU013", "productName": "积分不足勿扰款", "stock": 0},
        ]
    },
}

MOCK_LOTTERY = {
    "code": 0,
    "data": {
        "activityName": "麦麦积分抽奖",
        "status": "进行中",
        "costPoint": 500,
        "prizeList": [
            {"prizeName": "巨无霸套餐券", "valueYuan": 38.0, "winRate": 0.005, "remainStock": 40},
            {"prizeName": "薯条兑换券", "valueYuan": 12.0, "winRate": 0.06, "remainStock": 600},
            {"prizeName": "甜筒兑换券", "valueYuan": 6.0, "winRate": 0.25, "remainStock": 3000},
            {"prizeName": "中杯可乐券", "valueYuan": 9.0, "winRate": 0.10, "remainStock": 1500},
            {"prizeName": "谢谢参与", "valueYuan": 0.0, "winRate": 0.585, "remainStock": 99999},
        ],
    },
}
