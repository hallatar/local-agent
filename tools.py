import re
import subprocess
from pathlib import Path
from typing import Optional

import diff_utils
import git_tools

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a file. Always read before writing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (absolute or relative to repo root)"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Shows a diff and asks for confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "Complete new file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a pattern across files using ripgrep (falls back to Python). Returns file:line matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal search pattern"},
                    "directory": {"type": "string", "description": "Directory to search (default: repo root)"},
                    "file_glob": {"type": "string", "description": "File filter e.g. '*.py' or '*.ts'"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory matching an optional glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "pattern": {"type": "string", "description": "Glob pattern e.g. '**/*.py' (default: '*')"},
                    "max_results": {"type": "integer", "description": "Limit (default: 100)"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_tree",
            "description": "Show a directory tree. Use this first to understand repo structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "max_depth": {"type": "integer", "description": "Max depth (default: 3)"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command in the repo. Use for tests, builds, linters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "description": "Working directory (default: repo root)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status of the repository.",
            "parameters": {
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff for the repo or a specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "file_path": {"type": "string", "description": "Specific file (optional)"},
                },
                "required": ["repo_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commit history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "n": {"type": "integer", "description": "Number of commits (default: 10)"},
                },
                "required": ["repo_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage files and create a commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "message": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific files to stage (optional, defaults to all modified)",
                    },
                },
                "required": ["repo_path", "message"],
            },
        },
    },
]

_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next", ".turbo"}


def _resolve(path: str, repo_path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(repo_path) / p
    return p.resolve()


def _build_tree(directory: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
    if depth > max_depth:
        return ["    " * depth + "..."]
    try:
        entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return []
    entries = [e for e in entries if e.name not in _IGNORE_DIRS]
    lines = []
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            ext = "    " if i == len(entries) - 1 else "│   "
            lines.extend(_build_tree(entry, prefix + ext, depth + 1, max_depth))
    return lines


def _search_fallback(pattern: str, directory: Path, file_glob: Optional[str]) -> str:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    results = []
    for path in directory.rglob(file_glob or "*"):
        if any(part in _IGNORE_DIRS or part.startswith(".") for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if regex.search(line):
                    results.append(f"{path}:{i}: {line.strip()}")
                    if len(results) >= 100:
                        results.append("... (truncated at 100 results)")
                        return "\n".join(results)
        except Exception:
            continue
    return "\n".join(results) if results else "No matches found"


def dispatch_tool(name: str, args: dict, repo_path: str, auto_confirm: bool = False) -> str:
    try:
        if name == "read_file":
            p = _resolve(args["path"], repo_path)
            if not p.exists():
                return f"File not found: {p}"
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 20000:
                content = content[:20000] + f"\n\n... (truncated — {len(content)} chars total)"
            return content

        if name == "write_file":
            p = _resolve(args["path"], repo_path)
            return diff_utils.apply_write(str(p), args["content"], auto_confirm)

        if name == "search_files":
            directory = _resolve(args.get("directory", repo_path), repo_path)
            pattern = args["pattern"]
            file_glob = args.get("file_glob")
            rg_cmd = ["rg", "--no-heading", "-n", pattern, str(directory)]
            if file_glob:
                rg_cmd += ["-g", file_glob]
            try:
                out = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=15).stdout.strip()
                return out or "No matches found"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return _search_fallback(pattern, directory, file_glob)

        if name == "list_files":
            directory = _resolve(args["directory"], repo_path)
            pattern = args.get("pattern", "*")
            limit = args.get("max_results", 100)
            files = []
            for p in sorted(directory.rglob(pattern)):
                if any(part in _IGNORE_DIRS for part in p.parts):
                    continue
                if p.is_file():
                    files.append(str(p.relative_to(directory)))
                    if len(files) >= limit:
                        files.append(f"... (limit {limit} reached)")
                        break
            return "\n".join(files) if files else "No files found"

        if name == "file_tree":
            directory = _resolve(args["directory"], repo_path)
            max_depth = args.get("max_depth", 3)
            lines = [str(directory)] + _build_tree(directory, max_depth=max_depth)
            return "\n".join(lines)

        if name == "run_command":
            cwd = _resolve(args.get("cwd", repo_path), repo_path)
            timeout = args.get("timeout", 30)
            result = subprocess.run(
                args["command"],
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"
            return output or f"(exit code {result.returncode}, no output)"

        if name == "git_status":
            return git_tools.git_status(args["repo_path"])

        if name == "git_diff":
            return git_tools.git_diff(args["repo_path"], args.get("file_path"))

        if name == "git_log":
            return git_tools.git_log(args["repo_path"], args.get("n", 10))

        if name == "git_commit":
            return git_tools.git_commit(args["repo_path"], args["message"], args.get("files"))

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error ({name}): {type(e).__name__}: {e}"
