# code-agent

A local AI coding assistant powered by LM Studio. Point it at any repo and give it a task — it reads the codebase, plans, edits files with diff previews, and commits changes.

## Requirements

- Python 3.11+
- [LM Studio](https://lmstudio.ai) running with a model loaded and the local server enabled
- Recommended models: `Qwen2.5-Coder-7B-Instruct`, `Llama-3.1-8B-Instruct`

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# One-shot task
python main.py "add error handling to all routes" --repo /path/to/project

# Interactive REPL
python main.py --interactive --repo /path/to/project

# Auto-confirm all file writes
python main.py "refactor auth middleware" --repo . --yes

# Use a specific model
python main.py "explain the codebase" --repo . --model "llama-3.1-8b-instruct"
```

## How it works

The agent runs a ReAct loop (Reason → Act → Observe) until the task is done:

1. Reads the repo structure with `file_tree`
2. Searches and reads relevant files
3. Proposes file changes — shows a colored diff and asks for confirmation
4. Commits via git if requested

## MCP servers (optional)

Edit `mcp_servers.json` to connect external MCP tool servers:

```json
{
  "servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/repo"]
    }
  ]
}
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `LM_STUDIO_URL` | `http://localhost:1234/v1` | LM Studio API endpoint |
| `AGENT_MODEL` | `qwen2.5-coder-7b-instruct` | Model name as shown in LM Studio |

Or pass `--url` and `--model` flags directly.
