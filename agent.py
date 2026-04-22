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
                response = await self.client.chat.completions.create(
                    model=config.DEFAULT_MODEL,
                    messages=self.messages,
                    tools=all_tools,
                    tool_choice="auto",
                    max_tokens=config.MAX_TOKENS,
                    temperature=config.TEMPERATURE,
                )
            except Exception as e:
                console.print(f"[red]LLM error: {e}[/red]")
                await self.mcp.stop()
                return f"Error: {e}"

            msg = response.choices[0].message
            finish = response.choices[0].finish_reason

            if msg.content:
                console.print(f"[bold cyan]Reasoning:[/bold cyan] {msg.content}")

            # Final answer — no tool calls
            if finish == "stop" or not msg.tool_calls:
                result = msg.content or ""
                console.print(Panel(Markdown(result), title="[bold green]Done[/bold green]", border_style="green"))
                await self.mcp.stop()
                return result

            # Append assistant message (with tool calls) to history
            assistant_msg: dict = {"role": "assistant"}
            if msg.content:
                assistant_msg["content"] = msg.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
            self.messages.append(assistant_msg)

            # Execute each tool call and collect results
            for tc in msg.tool_calls:
                fn = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                preview = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
                console.print(f"[bold yellow]▶ {fn}[/bold yellow]([dim]{preview}[/dim])")

                if await self.mcp.has_tool(fn):
                    result = await self.mcp.call_tool(fn, args)
                else:
                    result = dispatch_tool(fn, args, self.repo_path, self.auto_confirm)

                snippet = str(result)
                console.print(f"[dim]  → {snippet[:300]}{'...' if len(snippet) > 300 else ''}[/dim]")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })

        await self.mcp.stop()
        console.print("[yellow]Max iterations reached[/yellow]")
        return "Reached max iterations without completing the task"
