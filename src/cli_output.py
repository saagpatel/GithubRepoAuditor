"""Rich CLI output helpers with graceful fallback to plain print.

All terminal output goes through this module. If rich is not installed,
everything degrades to plain text — the tool stays usable.
"""
from __future__ import annotations

import sys

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_stderr_console = Console(stderr=True) if HAS_RICH else None
_stdout_console = Console() if HAS_RICH else None


def create_progress() -> "Progress | None":
    """Create a Rich progress bar for stderr. Returns None if rich unavailable."""
    if not HAS_RICH:
        return None
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=_stderr_console,
        transient=True,
    )


def print_status(msg: str) -> None:
    """Print a styled status message to stderr."""
    if HAS_RICH:
        _stderr_console.print(f"  [bold]{msg}[/bold]")
    else:
        print(f"  {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    """Print a yellow warning to stderr."""
    if HAS_RICH:
        _stderr_console.print(f"  [yellow]⚠ {msg}[/yellow]")
    else:
        print(f"  ⚠ {msg}", file=sys.stderr)


def print_info(msg: str) -> None:
    """Print an info message to stderr."""
    if HAS_RICH:
        _stderr_console.print(f"  [dim]{msg}[/dim]")
    else:
        print(f"  {msg}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print a green success message to stdout."""
    if HAS_RICH:
        _stdout_console.print(f"[green]✓[/green] {msg}")
    else:
        print(f"✓ {msg}")


def print_summary(lines: list[str]) -> None:
    """Print multi-line summary to stdout."""
    if HAS_RICH:
        _stdout_console.print("\n".join(lines))
    else:
        print("\n".join(lines))
