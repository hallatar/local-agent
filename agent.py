import asyncio
import json
from typing import Optional

from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

import config
from tools import TOOLS_SCHEMA, dispatch_tool
from mcp_bridge import MCPBridge

console = Console()


class Agent:
    def __init__(
        self,
        repo_path: str,
        auto_confirm: bool = False,
        mcp_servers: Optional[list] = None,
    ):
        self.repo_path = repo_path
        self.auto_confirm = auto_confirm
        self.client = AsyncOpenAI(
            base_url=config.LM_STUDIO_BASE_URL,
            api_key=config.LM_STUDIO_API_KEY,
        )
        self.mcp = MCPBridge(mcp_servers or [])
        self.messages: list[dict] = []

    async def run(self, task: str) -> str:
        await self.mcp.start()
        all_tools = TOOLS_SCHEMA + await self.mcp.get_tool_schemas()

        self.messages = [
            {"role": "system", "content": config.SYSTEM_PROMPT},
            {"role": "user", "content": f"Repository: {self.repo_path}\n\nTask: {task}"},
        ]

        console.print(Panel(
            f"[bold green]Task:[/bold green] {task}\n[dim]Repo: {self.repo_path} | Model: {config.DEFAULT_MODEL}[/dim]",
            border_style="green",
        ))

        for step in range(1, config.MAX_ITERATIONS + 1):
            console.rule(f"[dim]Step {step}[/dim]")

            try:
                if config.STREAM:
                    content, finish, tool_calls_raw = await self._stream_step(all_tools)
                else:
                    response = await self.client.chat.completions.create(
                        model=config.DEFAULT_MODEL,
                        messages=self.messages,
                        tools=all_tools,
                        tool_choice="auto",
                        max_tokens=config.MAX_TOKENS,
                        temperature=config.TEMPERATURE,
                    )
                    msg = response.choices[0].message
                    finish = response.choices[0].finish_reason
                    content = msg.content or ""
                    tool_calls_raw = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in (msg.tool_calls or [])
                    ]

                    if content:
                        console.print(f"[bold cyan]Reasoning:[/bold cyan] {content}")

            except Exception as e:
                console.print(f"[red]LLM error: {e}[/red]")
                await self.mcp.stop()
                return f"Error: {e}"

            # Final answer — no tool calls
            if finish == "stop" or not tool_calls_raw:
                result = content or ""
                console.print(Panel(Markdown(result), title="[bold green]Done[/bold green]", border_style="green"))
                await self.mcp.stop()
                return result

            # Append assistant message (with tool calls) to history
            assistant_msg: dict = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            # tool_calls_raw is always list[dict] (stream=True path normalises non-stream too)
            assistant_msg["tool_calls"] = tool_calls_raw
            self.messages.append(assistant_msg)

            # Execute all tool calls in parallel, then append results in order
            for tc in tool_calls_raw:
                fn = tc["function"]["name"]
                args_preview = ", ".join(
                    f"{k}={repr(v)[:50]}"
                    for k, v in (json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}).items()
                )
                console.print(f"[bold yellow]▶ {fn}[/bold yellow]([dim]{args_preview}[/dim])")

            results = await asyncio.gather(*[self._run_tool(tc) for tc in tool_calls_raw])

            for tc_id, result in results:
                snippet = str(result)
                console.print(f"[dim]  → {snippet[:300]}{'...' if len(snippet) > 300 else ''}[/dim]")
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": str(result),
                })

        await self.mcp.stop()
        console.print("[yellow]Max iterations reached[/yellow]")
        return "Reached max iterations without completing the task"

    async def _stream_step(self, all_tools: list) -> tuple[str, str, list[dict]]:
        """Stream one LLM turn. Returns (content, finish_reason, tool_calls)."""
        stream = await self.client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=self.messages,
            tools=all_tools,
            tool_choice="auto",
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
            stream=True,
        )

        content_parts: list[str] = []
        # index -> {"id", "name", "arguments"}
        tc_acc: dict[int, dict] = {}
        finish = "stop"
        printed_header = False

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            if choice.finish_reason:
                finish = choice.finish_reason

            delta = choice.delta

            # Stream text content token by token
            if delta.content:
                if not printed_header:
                    console.print("[bold cyan]Reasoning:[/bold cyan] ", end="")
                    printed_header = True
                print(delta.content, end="", flush=True)
                content_parts.append(delta.content)

            # Accumulate tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_acc:
                        tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tc_acc[idx]["id"] += tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_acc[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_acc[idx]["arguments"] += tc_delta.function.arguments

        if printed_header:
            print()  # newline after streamed content

        content = "".join(content_parts)
        tool_calls = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in tc_acc.values()
        ]
        return content, finish, tool_calls

    async def _run_tool(self, tc: dict) -> tuple[str, str]:
        """Dispatch one tool call. Returns (tool_call_id, result_str)."""
        fn = tc["function"]["name"]
        tc_id = tc["id"]
        try:
            args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}

        if await self.mcp.has_tool(fn):
            result = await self.mcp.call_tool(fn, args)
        else:
            # dispatch_tool is sync (file I/O / subprocess) — run in thread pool
            result = await asyncio.to_thread(dispatch_tool, fn, args, self.repo_path, self.auto_confirm)

        return tc_id, str(result)
