import os
from pathlib import Path

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = "lm-studio"
DEFAULT_MODEL = os.getenv("AGENT_MODEL", "llama3.3-8b-instruct-thinking-heretic-uncensored-claude-4.5-opus-high-reasoning-i1")

MAX_ITERATIONS = 30
MAX_TOKENS = 2048  # Keep low so system prompt + history fits within n_ctx=4096
TEMPERATURE = 0.1
STREAM = True

MCP_CONFIG_FILE = Path(__file__).parent / "mcp_servers.json"

SYSTEM_PROMPT = """You are an expert software engineering assistant with access to tools for reading, writing, and managing code repositories.

You work in a ReAct loop:
1. THINK: Reason about what to do next
2. ACT: Call a tool
3. OBSERVE: Read the result
4. Repeat until the task is complete

Guidelines:
- Always use file_tree first to understand the repo structure
- Always read a file before writing to it
- Use search_files to find relevant code before making changes
- Use git_status before committing
- When writing files, the user will confirm diffs before they are applied
- Be thorough but efficient — don't read files you don't need
"""
