"""MCP (Model Context Protocol) 适配器。

M3.3 交付：让 CogCore Agent 能加载并调用 MCP server 暴露的工具。

设计：
- 不引入新依赖（用 stdlib subprocess + json 即可）
- 一个 MCP server = 一个子进程，通过 stdin/stdout 交换 JSON-RPC 消息
- 每个 server 的 tools/list 返回的 tool 都注册到 ToolRegistry
- 调用时转发到对应 server

协议要点（Model Context Protocol 2024-11-05）：
- 传输：stdio，每个消息一行 JSON
- 握手：client 先发 initialize，server 回 result，client 再发 notifications/initialized
- 列出工具：tools/list
- 调用工具：tools/call，返回 {content: [{type: "text", text: "..."}]}

用法：
    from cogcore.mcp_adapter import MCPAdapter, MCPServerConfig

    adapter = MCPAdapter()
    adapter.add_server(MCPServerConfig(
        name="mock",
        command="python",
        args=["tests/mock_mcp_server.py"],
    ))
    adapter.connect_all()

    from cogcore.tools import ToolRegistry
    registry = ToolRegistry()
    adapter.register_all(registry)
    # 现在 registry 里有了所有 MCP 工具

    # 或者直接调用:
    result = adapter.call_tool("mock", "echo", {"text": "hi"})
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================


@dataclass
class MCPServerConfig:
    """单个 MCP server 配置。"""

    name: str = ""
    command: str = ""           # 启动命令（如 "python" / "npx"）
    args: list[str] = field(default_factory=list)  # 命令参数
    env: dict[str, str] = field(default_factory=dict)  # 额外环境变量
    cwd: str | None = None      # 工作目录
    enabled: bool = True
    description: str = ""


# ============================================================
# 客户端
# ============================================================


class MCPClient:
    """单个 MCP server 的客户端。"""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._proc: subprocess.Popen | None = None
        self._next_id = 1
        self._server_info: dict = {}

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """启动子进程并完成 initialize 握手。"""
        if self.is_running:
            return
        env = {**__import__("os").environ, **self.config.env}
        cmd = [self.config.command] + list(self.config.args)
        logger.info(f"MCP[{self.config.name}]: starting {cmd}")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=self.config.cwd,
            text=True,
            bufsize=1,
        )
        # initialize
        result = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cogcore", "version": "0.3.0"},
        })
        self._server_info = result
        # notifications/initialized (no response expected)
        self._notify("notifications/initialized", {})
        logger.info(f"MCP[{self.config.name}]: connected, server={self._server_info.get('serverInfo', {})}")

    def stop(self) -> None:
        """关闭子进程。"""
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=2)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        finally:
            self._proc = None

    def list_tools(self) -> list[dict]:
        """返回该 server 暴露的所有工具。"""
        result = self._request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用一个工具, 返回 text content。"""
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        # 拼接所有 text 类型 content
        parts: list[str] = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)

    # ============================================================
    # JSON-RPC 内部
    # ============================================================

    def _request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        """发送请求并等待响应。"""
        if not self.is_running:
            raise RuntimeError(f"MCP[{self.config.name}] not running")
        req_id = self._next_id
        self._next_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(msg)
        assert self._proc is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

        # 读一行响应
        import select
        # 简化：直接 readline, 加 timeout
        # Windows 上 select 不能用在 pipe 上, 用线程或非阻塞 IO
        # 实用方案: 在线程里读, 简单阻塞
        # 这里用直接 readline + 30s 超时
        import threading
        result_holder: dict = {}

        def reader() -> None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    return
                resp = json.loads(line)
                if resp.get("id") == req_id:
                    result_holder["resp"] = resp
            except Exception as e:
                result_holder["error"] = e

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if "resp" not in result_holder:
            raise TimeoutError(f"MCP[{self.config.name}] {method} timed out")
        resp = result_holder["resp"]
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"MCP[{self.config.name}] error: {err}")
        return resp.get("result", {})

    def _notify(self, method: str, params: dict) -> None:
        """发送通知（无响应）。"""
        if not self.is_running:
            return
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(msg)
        assert self._proc is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()


# ============================================================
# 适配器
# ============================================================


class MCPAdapter:
    """管理多个 MCP server 并把工具注册到 ToolRegistry。"""

    def __init__(self) -> None:
        self._configs: list[MCPServerConfig] = []
        self._clients: dict[str, MCPClient] = {}

    def add_server(self, config: MCPServerConfig) -> None:
        if not config.name:
            raise ValueError("MCPServerConfig.name is required")
        self._configs.append(config)

    def connect_all(self) -> dict[str, int]:
        """启动所有 enabled server, 返回 {name: tool_count}。"""
        results: dict[str, int] = {}
        for cfg in self._configs:
            if not cfg.enabled:
                continue
            try:
                client = MCPClient(cfg)
                client.start()
                tools = client.list_tools()
                self._clients[cfg.name] = client
                results[cfg.name] = len(tools)
                logger.info(f"MCP[{cfg.name}]: {len(tools)} tools loaded")
            except Exception as e:
                logger.warning(f"MCP[{cfg.name}] failed to start: {e}")
                results[cfg.name] = -1
        return results

    def disconnect_all(self) -> None:
        for client in self._clients.values():
            client.stop()
        self._clients.clear()

    def register_all(self, registry: Any) -> int:
        """把所有 server 的工具注册到 registry（ToolRegistry）。
        返回注册的总数。
        """
        count = 0
        for server_name, client in self._clients.items():
            try:
                tools = client.list_tools()
            except Exception as e:
                logger.warning(f"MCP[{server_name}]: list_tools failed: {e}")
                continue
            for tool in tools:
                self._register_one(registry, server_name, client, tool)
                count += 1
        return count

    def _register_one(
        self,
        registry: Any,
        server_name: str,
        client: MCPClient,
        tool: dict,
    ) -> None:
        """注册单个 MCP tool 到 ToolRegistry。

        工具名加 server 前缀避免冲突：mcp__{server}__{tool}
        """
        name = tool.get("name", "")
        if not name:
            return
        qualified = f"mcp__{server_name}__{name}"
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        schema: dict[str, str] = {}
        for k in properties:
            t = properties[k].get("type", "string")
            if t == "string":
                schema[k] = "string"
            elif t in ("integer", "number"):
                schema[k] = "number"
            elif t == "boolean":
                schema[k] = "bool"
            elif t in ("array", "object"):
                schema[k] = "dict"
            else:
                schema[k] = "string"

        def make_caller(srv: str, c: MCPClient, tname: str, required_keys: list[str]):
            def caller(**kwargs: Any) -> str:
                # MCP 必填参数检查
                missing = [k for k in required_keys if k not in kwargs]
                if missing:
                    return f"Error: missing required args: {missing}"
                try:
                    return c.call_tool(tname, kwargs)
                except Exception as e:
                    return f"MCP error: {e}"

            return caller

        registry.register_tool(
            name=qualified,
            func=make_caller(server_name, client, name, required),
            schema=schema,
        )
        registry.add_to_allowlist(qualified)
        logger.debug(f"MCP: registered {qualified} (desc='{description[:40]}...')")

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """直接通过指定 server 调用工具。"""
        client = self._clients.get(server_name)
        if client is None:
            raise KeyError(f"MCP server '{server_name}' not connected")
        return client.call_tool(tool_name, arguments)

    def server_names(self) -> list[str]:
        return list(self._clients.keys())

    def __enter__(self) -> "MCPAdapter":
        self.connect_all()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect_all()
