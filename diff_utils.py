import difflib
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()


def make_diff(old: str, new: str, filename: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    ))


def print_diff(old: str, new: str, filename: str) -> bool:
    """Print a colored diff. Returns True if there are changes."""
    diff_text = make_diff(old, new, filename)
    if not diff_text:
        console.print(f"[yellow]No changes in {filename}[/yellow]")
        return False
    console.print(Panel(
        Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
        title=f"[bold cyan]{filename}[/bold cyan]",
        border_style="cyan",
    ))
    return True


def apply_write(path: str, new_content: str, auto_confirm: bool = False) -> str:
    """Show diff, optionally confirm, then write. Returns status string."""
    p = Path(path)
    old_content = p.read_text(encoding="utf-8") if p.exists() else ""

    has_changes = print_diff(old_content, new_content, p.name)
    if not has_changes:
        return "No changes needed"

    if auto_confirm or Confirm.ask("[bold]Apply these changes?[/bold]", default=False):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_content, encoding="utf-8")
        return f"Written: {path}"

    return "Cancelled by user"
