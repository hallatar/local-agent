from contextlib import AsyncExitStack
from typing import Optional

try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    _MCP_OK = True
except ImportError:
    _MCP_OK = False


class MCPBridge:
    def __init__(self, server_configs: list[dict]):
        self.configs = server_configs
        self._stack = AsyncExitStack()
        self._sessions: dict[str, "ClientSession"] = {}
        self._tool_to_server: dict[str, str] = {}
        self._schemas: list[dict] = []

    async def start(self):
        if not _MCP_OK:
            if self.configs:
                print("[MCP] Warning: 'mcp' package not installed. Run: pip install mcp")
            return
        await self._stack.__aenter__()
        for cfg in self.configs:
            try:
                await self._connect(cfg)
            except Exception as e:
                print(f"[MCP] Failed to connect '{cfg.get('name', cfg.get('command', '?'))}': {e}")

    async def _connect(self, cfg: dict):
        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env=cfg.get("env") or None,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session: ClientSession = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools_result = await session.list_tools()
        name = cfg.get("name", cfg["command"])
        self._sessions[name] = session

        for tool in tools_result.tools:
            self._tool_to_server[tool.name] = name
            schema = tool.inputSchema if hasattr(tool, "inputSchema") else {"type": "object", "properties": {}}
            self._schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"MCP tool from {name}",
                    "parameters": schema,
                },
            })

        print(f"[MCP] Connected '{name}': {len(tools_result.tools)} tools")

    async def get_tool_schemas(self) -> list[dict]:
        return self._schemas

    async def has_tool(self, name: str) -> bool:
        return name in self._tool_to_server

    async def call_tool(self, name: str, args: dict) -> str:
        server = self._tool_to_server.get(name)
        if not server:
            return f"MCP tool '{name}' not found"
        try:
            result = await self._sessions[server].call_tool(name, args)
            parts = [item.text for item in result.content if hasattr(item, "text")]
            return "\n".join(parts) or "Tool returned no text content"
        except Exception as e:
            return f"MCP error calling '{name}': {e}"

    async def stop(self):
        try:
            await self._stack.__aexit__(None, None, None)
        except Exception:
            pass
