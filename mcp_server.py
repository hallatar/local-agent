#!/usr/bin/env python3
"""
MCP server that exposes code-agent tools to Continue.dev (or any MCP client).

Usage:
  python mcp_server.py --repo /path/to/project
"""
import sys
import argparse
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from tools import dispatch_tool, TOOLS_SCHEMA
from diff_utils import make_diff

_REPO_PATH = str(Path.cwd())

server = Server("code-agent")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["function"]["name"],
            description=t["function"]["description"],
            inputSchema=t["function"]["parameters"],
        )
        for t in TOOLS_SCHEMA
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    args = arguments or {}

    # Default git tools repo_path to the configured repo so the LLM
    # doesn't need to know it explicitly
    if name in {"git_status", "git_diff", "git_log", "git_commit"}:
        args.setdefault("repo_path", _REPO_PATH)

    # write_file: auto-apply (no interactive prompt over stdio) and return the diff
    if name == "write_file":
        p = Path(args["path"])
        if not p.is_absolute():
            p = Path(_REPO_PATH) / p
        p = p.resolve()
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        new = args["content"]
        diff = make_diff(old, new, p.name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new, encoding="utf-8")
        text = f"Written: {p}\n\n```diff\n{diff}\n```" if diff else f"Written: {p} (no changes)"
    else:
        text = dispatch_tool(name, args, _REPO_PATH, auto_confirm=True)

    return [types.TextContent(type="text", text=str(text))]


async def serve():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="code-agent",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="code-agent MCP server for Continue.dev")
    parser.add_argument(
        "--repo",
        default=str(Path.cwd()),
        help="Repository path to operate on (default: current directory)",
    )
    args = parser.parse_args()
    _REPO_PATH = str(Path(args.repo).resolve())
    asyncio.run(serve())
