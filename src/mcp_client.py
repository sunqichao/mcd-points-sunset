"""麦当劳 MCP Server 轻量客户端（仅依赖 Python 标准库）。

实现 Model Context Protocol 的 Streamable HTTP 传输：
    initialize -> notifications/initialized -> tools/list -> tools/call

设计取舍：
- 零第三方依赖，clone 后无需 pip install 即可运行
- 同时兼容 application/json 与 text/event-stream 两种响应体
- 自动维护 Mcp-Session-Id
- 对 401 / 429 给出可读的错误提示（官方文档明确的两个错误码）

安全约定：
- Token 只从环境变量 MCD_MCP_TOKEN 读取，绝不落盘、绝不打印到日志
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """MCP 调用失败。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class HttpClientError(McpError):
    """HTTP 层错误，携带状态码用于区分 401/429。"""


class McpClient:
    def __init__(self, token: str | None = None, url: str | None = None) -> None:
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        self.url = (url or os.environ.get("MCD_MCP_URL") or DEFAULT_URL).rstrip("/")
        if not self.token or self.token.startswith("YOUR_"):
            raise McpError(
                "未检测到有效的 MCP Token。请设置环境变量 MCD_MCP_TOKEN，"
                "获取方式参见 docs/GET_MCP_TOKEN.md"
            )
        self.session_id: str | None = None
        self._id = 0

    # ---------- 传输层 ----------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, payload: dict[str, Any], *, notify: bool = False) -> dict[str, Any] | None:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                if notify:
                    return None
                raw = resp.read().decode("utf-8", errors="replace")
                return self._parse_payload(resp.headers.get("Content-Type", ""), raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 401:
                raise HttpClientError(
                    "401：MCP Token 无效、已过期或未提供。请检查 Authorization 请求头与 Token。",
                    code=401,
                ) from exc
            if exc.code == 429:
                raise HttpClientError(
                    "429：触发限流（600 次/分钟）。请降低调用频率后重试。",
                    code=429,
                ) from exc
            raise HttpClientError(f"HTTP {exc.code}：{detail}", code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise McpError(f"网络请求失败：{exc.reason}") from exc

    @staticmethod
    def _parse_payload(content_type: str, raw: str) -> dict[str, Any]:
        """解析响应体：普通 JSON 或 SSE 流（取最后一个 data: 事件）。"""
        if "text/event-stream" in content_type:
            last: dict[str, Any] | None = None
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if not chunk:
                        continue
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        last = parsed
            if last is None:
                raise McpError(f"无法从 SSE 流中解析响应：{raw[:200]}")
            return last

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McpError(f"响应不是合法 JSON：{raw[:200]}") from exc
        if isinstance(parsed, list):  # 批量响应
            for item in reversed(parsed):
                if isinstance(item, dict) and "result" in item:
                    return item
            return parsed[-1] if parsed else {}
        return parsed

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params
        result = self._post(payload)
        if result is None:
            raise McpError("服务端返回空响应")
        if "error" in result:
            err = result["error"]
            raise McpError(f"[{err.get('code')}] {err.get('message')}")
        return result.get("result")

    # ---------- 会话与工具 ----------

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-points-sunset", "version": "1.0.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notify=True)

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list")
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用指定工具，返回结构化结果。

        兼容 content: [{type:'text', text:'...'}] 形态，若 text 是 JSON 则自动解析。
        """
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result is None:
            return None
        content = result.get("content")
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            joined = "\n".join(texts).strip()
            if joined:
                try:
                    return json.loads(joined)
                except json.JSONDecodeError:
                    return joined
            return None
        return result.get("structuredContent") or result


def connect() -> McpClient:
    """建立并完成握手的会话。"""
    client = McpClient()
    client.initialize()
    return client
