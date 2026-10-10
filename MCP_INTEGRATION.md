# MCP 接入说明

本项目真实接入麦当劳中国官方 MCP Server，并真实调用其工具完成积分清算。

> 接入依据：[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server) 官方文档
> 开放平台：<https://open.mcd.cn/mcp>

---

## 1. 接入方式

| 项目 | 值 |
|---|---|
| Server URL | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权方式 | `Authorization: Bearer <MCP Token>` |
| 限流 | 600 次 / 分钟（超限返回 429） |
| Token 申请 | 手机号登录 <https://open.mcd.cn/mcp> → 控制台 → 激活 |

配置示例见 [`mcp-config.example.json`](./mcp-config.example.json)，其中 Token 使用环境变量占位符 `${MCD_MCP_TOKEN}`，仓库内**不含任何真实凭证**。

本项目未使用任何第三方 HTTP SDK，客户端 [`src/mcp_client.py`](./src/mcp_client.py) 仅依赖 Python 标准库实现 MCP 握手（`initialize` → `notifications/initialized` → `tools/list` / `tools/call`），并兼容 `application/json` 与 `text/event-stream` 两种响应体。

---

## 2. 实际调用的工具

本项目的**只读清算链路**调用以下 4 个工具：

| Tool | 名称 | 在项目中的作用 | 贡献的数据 |
|---|---|---|---|
| `query-my-account` | 我的积分查询 | 盘点资产，确定清算预算 | 可用积分、即将过期积分、冻结积分、累计积分 |
| `mall-points-products` | 麦麦商城商品列表 | 枚举所有积分去路 | 商品名称、积分价、现金价、库存、类目 |
| `query-lottery-info` | 查看积分抽奖活动信息 | 评估「抽奖」这条不确定去路 | 单次消耗积分、奖品池、奖品余量 |
| `now-time-info` | 获取当前时间信息 | 计算到期倒计时 | 服务端当前日期 |

补充链路（按需调用）：

| Tool | 用途 |
|---|---|
| `mall-product-detail` | `mall-points-products` 未返回现金价时，补拉商品详情以确定可否精确估值 |
| `mall-order-list` | 核验历史兑换记录，避免重复推荐刚换过的商品 |

**写操作工具（`draw-lottery` / `mall-create-order`）在当前版本中不会被自动调用。** 它们会真实消耗用户积分，仅在用户明确给出执行指令并完成二次确认后才可能触发。这是刻意的设计取舍，详见下方「安全边界」。

---

## 3. 调用流程

```text
启动
 │
 ├─ initialize ─────────────────► 建立 MCP 会话，维护 Mcp-Session-Id
 │
 ├─ tools/list ─────────────────► 校验 Token 权限，确认 4 个只读工具可用
 │                                 （缺失任何一个即中止并提示，不静默降级）
 │
 ├─ query-my-account ───────────┐
 ├─ mall-points-products ───────┤ 三路并行取数（受 600 次/分钟限流保护）
 └─ query-lottery-info ─────────┘
 │
 ├─ now-time-info ──────────────► 服务端基准时间 → 到期倒计时 → 紧迫度分级
 │
 ├─ 估值   单位价值       ─────────► 每个去路折算成「元 / 千积分」
 ├─ 期望   抽奖期望值     ─────────► 抽奖三档（悲观 / 期望 / 乐观）
 ├─ 决策   风险调整       ─────────► 按风险偏好判定「抽奖 vs 兑换」
 ├─ 择优   背包动态规划   ─────────► 在清算预算内求总回收价值最大的组合
 │
 └─ 输出：终端报告 / report.json / 可视化看板 demo/index.html
```

对应代码：

| 阶段 | 文件 |
|---|---|
| MCP 传输与握手 | [`src/mcp_client.py`](./src/mcp_client.py) |
| 响应字段容错提取 | [`src/adapters.py`](./src/adapters.py) |
| 估值 / 期望 / 决策 / 背包 | [`src/liquidator.py`](./src/liquidator.py) |
| 流程编排与报告 | [`src/pipeline.py`](./src/pipeline.py) |
| 可视化看板生成 | [`src/build_demo.py`](./src/build_demo.py) |

---

## 4. 为什么用「键名候选 + 递归搜索」解析响应

MCP 工具的返回结构面向 LLM 设计，官方文档未固化字段名。硬编码 `data.list[0].pointPrice` 这类路径，一旦官方微调结构就会全线崩溃。

[`src/adapters.py`](./src/adapters.py) 的做法是：为每个语义字段准备一组候选键名（如积分价对应 `pointPrice` / `needPoint` / `exchangePoint` / `score` …），递归遍历响应树取值，取不到就降级并在报告中留下告警，**绝不静默吞掉问题**。所有告警都会出现在最终报告里。

样例数据 [`src/sample_data.py`](./src/sample_data.py) 刻意混用了多种字段名写法，就是为了让这条容错链路可以被持续验证。

---

## 5. 业务价值

麦当劳 MCP 把点餐、门店、券券、活动、积分、抽奖等能力开放出来后，**「积分资产怎么处置」**是一个被忽视的环节：积分有时效，用户既不知道自己有多少即将过期，也不知道哪条去向的单位价值更高，更无法在受限预算内凑出最优组合。

本 Skill 把这件事从「凭感觉换」变成三个可计算的步骤：

1. **统一度量**——把商城兑换与抽奖折算到同一个「元 / 千积分」尺子上，让不同性质去向可以横向比较；
2. **风险定价**——抽奖是不确定收益，通过不确定度惩罚与溢价要求把「波动」折进决策，而不是只比较期望值；
3. **预算择优**——把「这笔积分怎么花完最值」建模成背包问题求最优解，而不是按单价贪心导致大量小额积分无处安放。

产出直接可执行：一份带数字的组合清单，以及「多久之内必须处理」的预警。

---

## 6. 安全边界

- **只读默认**：常规运行绝不调用 `draw-lottery` / `mall-create-order`，不入账任何订单、不扣任何积分；
- **双开关写保护**：即便显式要求执行写操作，仍需同时通过 `--execute` 与 `--i-know-this-costs-points` 两道确认；
- **凭证隔离**：Token 只从环境变量读取，仓库只含占位符配置，`.gitignore` 已排除 `.env` 与真实响应产物；
- **知情而非代劳**：估算类商品不参与自动择优，另列清单交给用户判断，避免用推算数字替人决策。

---

## 7. 无 Token 时如何验证

未配置 Token 也能完整验证全部算法链路：

```bash
python3 src/pipeline.py --mock      # 完整清算报告
python3 tests/test_core.py          # 28 项算法断言
python3 src/build_demo.py           # 生成可视化看板
```

配置 Token 后，同一套代码无需改动即可切换到真实数据。
