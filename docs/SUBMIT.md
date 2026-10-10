# 参赛提交指南

比赛最终以官方仓库下的 Issue 为准，本文含全部可复制的命令与文案。

- 官方入口：<https://github.com/M-China/mcd-developer-innovation-challenge>
- 截止时间：**2026 年 10 月 25 日 23:59**
- 注意：官方 README 中的旧链接 `M-China-Official/...` 已失效会 404，请使用上面的 `M-China` 地址。

---

## 第一步：创建公开仓库

在 GitHub 新建仓库，**Repository name** 建议填 `mcd-points-sunset`，**务必选择 Public**（私有仓库不能参赛）。

创建时**不要**勾选 Add README / .gitignore / LICENSE——本地已有。

## 第二步：推送代码

把下面的 `sunqichao` 换成你的 GitHub 用户名后依次执行：

```bash
cd /path/to/mcd-points-sunset

git init
git add .
git commit -m "feat: 麦麦积分清算局 - 基于麦当劳官方 MCP 的积分清算 Skill"

git branch -M main
git remote add origin https://github.com/sunqichao/mcd-points-sunset.git
git push -u origin main
```

推送前建议再确认一次没有凭证被带上：

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

基于麦当劳中国官方 MCP 的 AI Skill，把「麦麦商城兑换」和「积分抽奖」两条去向折算到统一的度量「元 / 千积分」上比较，并给出到期预警与最优兑换组合。

核心做三件事：
1）估值——有官方现金价的商品按「现金价 ÷ 积分价」精确折算；没有现金价的按同类目中位数估算，并明确标注【准】/【估】，不假装算得准。
2）决策——抽奖是不确定收益，不只比期望值，而是按「不确定度惩罚 + 溢价要求」做风险调整后再下结论。实测常见奖品池下抽奖期望约 6.62 元/千积分，显著低于直接兑换的 11.05 元/千积分。
3）择优——把「这笔积分怎么花完最值」建模为背包问题用 DP 求解，而非按单价贪心，实测预算利用率可达 99%。估算价值的商品默认不参与择优，另列待定清单交用户判断。

真实调用 4 个 MCP 只读工具：query-my-account、mall-points-products、query-lottery-info、now-time-info。默认只读，绝不自动扣除任何积分；draw-lottery 与 mall-create-order 需用户明确指令并二次确认才会触发。

Python 3.9+ 零第三方依赖，无需 pip install。未申请 Token 也可用 --mock 跑通完整链路，含 28 项算法断言与零外部依赖的可视化看板 demo/index.html。

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
