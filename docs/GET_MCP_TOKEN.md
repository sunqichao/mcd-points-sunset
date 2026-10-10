# 申请麦当劳 MCP Token

全程约 1 分钟，只需手机号。Token 免费，个人使用。

## 第一步：打开开放平台

访问 <https://open.mcd.cn/mcp>

## 第二步：登录

点击页面右上角的**【登录】**按钮，跳转登录页后用**手机号 + 验证码**完成登录。

登录成功后会跳回首页，此时右上角的「登录」按钮会变成**「控制台」**——这是判断是否登录成功最简单的方法。

## 第三步：申请 Token

点击右上角**「控制台」**，弹出控制台窗口，点击里面的**「激活」**按钮申请 MCP Token。

## 第四步：同意协议

阅读并勾选同意《麦当劳 MCP 服务规则》，继续。

## 第五步：复制 Token

申请成功后页面上会出现 Token 字符串，点击**一键复制**。

> ⚠️ Token 等同你的账户凭证，**不要**把它发给别人、贴到聊天记录或提交进任何代码仓库。

---

## 配置到本项目

```bash
cp .env.example .env
```

编辑 `.env`，把 `YOUR_MCP_TOKEN` 换成刚才复制的 Token：

```text
MCD_MCP_TOKEN=把这一行整体替换成你在控制台复制的 Token
```

`.env` 已被 `.gitignore` 排除，不会被 `git add .` 误提交。

验证是否配置成功：

```bash
python3 src/pipeline.py
```

看到清算报告即表示对接成功。

---

## 配置到 AI 客户端（可选）

若要在 WorkBuddy / Claude Desktop / Cursor / Cherry Studio 中直接使用，把 `mcp-config.example.json` 的内容粘贴进 MCP 配置，**记得把 `${MCD_MCP_TOKEN}` 替换成真实 Token**：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer 这里换成你的真实Token"
      }
    }
  }
}
```

以 WorkBuddy 为例：左侧边栏【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】→ 粘贴 → 保存 → 启用。

---

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `401：MCP Token 无效、已过期或未提供` | Token 填错、未替换占位符，或已在控制台重新生成 | 检查 `.env` 中是否仍是 `YOUR_...`，或重新申请 Token |
| `429：触发限流` | 每分钟请求超过 600 次 | 降低调用频率。本项目一次完整清算只发起约 5 次请求，正常不会触发 |
| `数据获取失败：当前 MCP Token 未提供以下工具` | 账号未开通对应业务权限 | 先确认麦当劳 App 中该业务可正常使用；本项目必需的 4 个查询工具缺失时会明确列出，不会静默降级 |
| 提示「未检测到有效的 MCP Token」 | 环境变量未注入当前 shell | 确认 `.env` 已创建；本项目会自动读取仓库根目录的 `.env` |

> 若暂时不想申请，可先用 `python3 src/pipeline.py --mock` 查看完整效果，逻辑链路完全一致。

---

## 服务约束

- 服务范围：中国大陆地区（不含港澳台）
- 传输协议：Streamable HTTP
- 限流：600 次 / 分钟
- 适用范围：个人非商业用途；不得用于商业售卖、付费分发或暗示官方背书
- 详见 [麦当劳 MCP Server 服务规则](https://cdn.mcd.cn/cms/pages/MCPServerRules.html)
