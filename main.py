import sys
from pathlib import Path

# Ensure imports work regardless of where this script is called from
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import argparse
import json

import config
from agent import Agent


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="Local code agent powered by LM Studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python main.py "add error handling to all routes" --repo e:/AlphaNew/Alpha/HTTP
  python main.py "explain the auth flow" --repo .
  python main.py --interactive --repo /path/to/project
  python main.py "run tests and fix failures" --repo . --yes
        """,
    )
    p.add_argument("task", nargs="?", help="Task to perform (omit for --interactive mode)")
    p.add_argument("--repo", "-r", default=".", help="Path to target repo (default: current dir)")
    p.add_argument("--model", "-m", help=f"LM Studio model name (default: {config.DEFAULT_MODEL})")
    p.add_argument("--url", help=f"LM Studio base URL (default: {config.LM_STUDIO_BASE_URL})")
    p.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all file writes without prompting")
    p.add_argument("--interactive", "-i", action="store_true", help="Start interactive REPL session")
    return p


def load_mcp_servers() -> list:
    if config.MCP_CONFIG_FILE.exists():
        try:
            return json.loads(config.MCP_CONFIG_FILE.read_text()).get("servers", [])
        except Exception as e:
            print(f"Warning: could not load MCP config: {e}")
    return []


async def run_once(task: str, repo_path: str, auto_confirm: bool, mcp_servers: list) -> str:
    agent = Agent(repo_path, auto_confirm=auto_confirm, mcp_servers=mcp_servers)
    return await agent.run(task)


def main():
    args = build_parser().parse_args()

    if args.model:
        config.DEFAULT_MODEL = args.model
    if args.url:
        config.LM_STUDIO_BASE_URL = args.url

    repo_path = str(Path(args.repo).resolve())
    mcp_servers = load_mcp_servers()

    if args.interactive:
        print(f"\n  Code Agent  |  model: {config.DEFAULT_MODEL}  |  repo: {repo_path}")
        print("  Type your task and press Enter. 'quit' to exit.\n")
        while True:
            try:
                task = input(">>> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye.")
                break
            if not task:
                continue
            if task.lower() in {"quit", "exit", "q"}:
                print("Bye.")
                break
            asyncio.run(run_once(task, repo_path, args.yes, mcp_servers))

    elif args.task:
        asyncio.run(run_once(args.task, repo_path, args.yes, mcp_servers))

    else:
        build_parser().print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
