# 参赛提交指南

比赛最终以官方仓库下的 Issue 为准，本文含全部可复制的命令与文案。

- 官方入口：<https://github.com/M-China/mcd-developer-innovation-challenge>
- 截止时间：**2026 年 10 月 25 日 23:59**
- 注意：官方 README 中的旧链接 `M-China-Official/...` 已失效会 404，请使用上面的 `M-China` 地址。

---

## 第一步：创建公开仓库 ✅ 已完成

仓库已创建并推送：**<https://github.com/sunqichao/mcd-points-sunset>**

| 项目 | 状态 |
|---|---|
| 可见性 | Public ✅（私有仓库不能参赛） |
| 默认分支 | main |
| 提交历史 | `6d14807` Initial commit → `41b7474` 作品首版 |
| 文件数 | 20（含官方要求的全部必备文件） |
| Topics | `mcdonalds` `mcp` `model-context-protocol` `ai-skill` 等 8 个 |
| License | MIT |

## 第二步：推送代码 ✅ 已完成

后续若本地还有改动，在 `repo/` 目录下执行：

```bash
git add .
git commit -m "说明本次改动"
git push
```

推送前建议确认一次没有凭证被带上：

```bash
git status --porcelain | grep -i -E "\.env$|token" ; echo "无输出即安全"
```

若 GitHub 要求身份认证，`git push` 时用户名填 GitHub 账号，密码处填 **Personal Access Token**（在 Settings → Developer settings → Personal access tokens 生成，勾选 `repo` 权限）。

## 第三步：提交报名 Issue

打开 <https://github.com/M-China/mcd-developer-innovation-challenge/issues> → **New issue**

> ⚠️ 官方要求：Issue 内容**不超过 1000 字**，且**务必不要插入图片**，否则可能报名失败。

**Issue 标题**（可自定义，建议）：

```text
【参赛申请】麦麦积分清算局：把抽奖和商城兑换放在同一把尺子上比价
```

**Issue 正文**（替换 `sunqichao` 后整段复制）：

```text
【参赛申请】
项目名称：麦麦积分清算局（McPoints Sunset）
项目地址：https://github.com/sunqichao/mcd-points-sunset
项目简介：在积分过期之前，把每一分都花在单位价值最高的去路上。

基于麦当劳中国官方 MCP 的 AI Skill，已完成真实联调，单次清算调用 7 个只读工具。

关键在于两个只有真接才会踩到的坑。

坑一：商城里大量商品是「凭券享 X 元购买」券，官方说明写「凭本券可享受3.9元购买圆筒冰淇淋」，兑换后仍要付钱，用券面价当价值会虚高三成。本项目改按「券内单品常规菜单价合计 − 凭券应付现金」折算，菜单价取自 query-meals 的真实门店报价，逐单品核价而非估算。

坑二：query-lottery-info 返回 27 项奖品却不公布任何中签概率。本项目按奖品名称规则逐项折价，在等概率假设下给出参考期望值，同时明确标注该假设大概率高估——概率未知时不替用户拍板，直接退回收益确定的兑换。

择优用 0-1 背包 DP 而非单价贪心，真实运行预算利用率 97%。无法核定价值的商品一律排除并给出原因，不拿估算数字假装精确。

Python 3.9+ 零第三方依赖，含 47 项离线断言，默认只读。

真实调用 7 个只读工具：query-my-account、mall-points-products、mall-product-detail、query-lottery-info、now-time-info、query-nearby-stores、query-meals。绝不自动扣除积分；draw-lottery 与 mall-create-order 需用户明确指令并二次确认才会触发。

本项目使用 WorkBuddy 开发，已提交 workbuddy.md。
```

## 第四步：等待回执

提交后系统会在该 Issue 下自动回复**报名成功 / 失败原因**。失败会写明原因，修改后可重新提交。

报名成功还不够——**排行榜按 Star 数定胜负**，且 Star 需大于 0 才会进榜。建议随后：

- 确认仓库确实是 Public
- 检查 README 渲染正常、`demo/index.html` 能打开
- 把仓库链接分享给可能感兴趣的朋友

---

## 后续：拿到真实 Token 后刷新为真实数据

```bash
cp .env.example .env     # 填入真实 MCP Token
python3 src/pipeline.py                 # 终端清算报告
python3 src/build_demo.py --real        # 用真实数据重生成看板
```

由于真实数据涉及个人资产，建议上传前人工检查 `demo/index.html` 中是否包含不想公开的兑换记录。
