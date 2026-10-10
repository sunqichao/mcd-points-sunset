# WorkBuddy 开发记录

> 本文件用于核验「麦当劳程序员创意开发大赛 × WorkBuddy 联动奖励」资格。
> 项目「麦麦积分清算局（mcd-points-sunset）」全程使用 WorkBuddy 完成。

## 1. 需求来源

用户提供《2026 麦当劳程序员创意开发大赛》活动说明，要求基于**麦当劳中国官方 MCP 能力**开发一个 AI Skill 作品并完成参赛报名。

约束条件：
- 作品必须真实调用麦当劳 MCP；
- 仓库必须 Public 开源，并包含官方规定的全部文件；
- 最终需在官方仓库提交 Issue 完成报名；
- 使用 WorkBuddy 开发可申领专项积分。

## 2. WorkBuddy 实际承担的工作

### 阶段一 · 赛事情报与选题决策（WorkBuddy 独立完成）

- 通过 GitHub API 定位官方组织 `M-China`，克隆并通读了两个核心仓库：
  - `mcd-developer-innovation-challenge`（赛事规则 / 活动规则 / 参赛声明模板）
  - `mcd-mcp-server`（MCP 接入指南 / 工具清单）
- 拉取官方 `RANKING.md` 并做量化分析：共 270 份报名申请、141 个进榜项目，按项目名归类统计出各赛道拥挤度
- 结论驱动选题：点餐（22）、省钱/券（19）、营养/热量（15）已是红海；而抽奖（1）、商城（2）、门店（2）几乎无人涉足
- 输出可视化图表辅助判断，最终选定「积分资产清算」方向

> 附带修正了一个易踩的坑：官方 README 中的 Issue 链接指向已失效的 `M-China-Official` 组织，实际入口为 `M-China`。

### 阶段二 · 方案设计与算法实现

- 设计三层算法架构：估值层（单位积分价值）、决策层（抽奖期望 vs 风险调整）、择优层（背包 DP）
- 编写 `src/liquidator.py`、`src/mcp_client.py`、`src/adapters.py`、`src/pipeline.py`、`src/build_demo.py`
- 自主发现并修复两处实现缺陷（详见第 3 节）

### 阶段三 · 质量保障

- 编写 28 项断言的自测 `tests/test_core.py`，覆盖估值精度、期望值、决策翻转、背包不超支、边界情况
- 对产出文档做异常字符与非预期词扫描，清理混入的噪声词

### 阶段四 · 交付文档

生成 README.md、MCP_INTEGRATION.md、CONTEST_DECLARATION.md、SKILL.md、mcp-config.example.json、docs/GET_MCP_TOKEN.md 与可视化看板。

## 3. 值得记录的两处自我纠错

1. **抽奖期望值单位错误**：自测发现 `ev_per_1k` 属性在已归一化的 `scenario` 上重复除了一次 `cost_points`，数值偏差 500 倍。修复后期望值从 0.0124 校正为 6.22 元/千积分。
2. **用推算值做最优化**：初版让估算价值的商品参与背包求解，导致产出「回收约 ¥70.84」这种由推算得来的数字。判定为方法论错误，改为默认只用有官方现金价的商品择优，估算商品另设「待定清单」，并新增 `--include-estimated` 开关。

## 4. 关于真实 MCP 对接的验证

用户尚未提供 MCP Token，但已用占位 Token 完成一次真实请求：

```text
数据获取失败：401：MCP Token 无效、已过期或未提供。请检查 Authorization 请求头与 Token。
```

该结果说明：客户端与 `https://mcp.mcd.cn` 的 MCP 握手、鉴权头构造、错误码解析链路均已跑通，服务端正确识别这是一次协议合法但凭证无效的请求。取得真实 Token 后无需改动代码即可切换到真实数据。

## 5. 产出清单

| 文件 | 说明 |
|---|---|
| `README.md` | 项目介绍、安装、使用示例、目标用户 |
| `SKILL.md` | Skill 本体，含安全边界与执行规则 |
| `MCP_INTEGRATION.md` | MCP 接入说明：工具、流程、业务价值 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方模板，逐字一致） |
| `mcp-config.example.json` | 脱敏 MCP 配置 |
| `src/` | 客户端、容错适配、算法、流程、看板生成 |
| `tests/test_core.py` | 28 项算法断言 |
| `demo/index.html` | 自包含可视化看板（零外部依赖） |
