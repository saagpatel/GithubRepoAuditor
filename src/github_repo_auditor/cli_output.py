"""Rich CLI output helpers with graceful fallback to plain print.

All terminal output goes through this module. If rich is not installed,
everything degrades to plain text — the tool stays usable.
"""
from __future__ import annotations

import re
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

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>(?P<key_quote>['\"]?)(?:access_token|api_key|apikey|"
    r"client_secret|credential|github_token|password|private_key|secret|token)"
    r"(?P=key_quote)\s*[:=]\s*)"
    r"(?:(?P<quoted_value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
    r"(?P<bare_value>[^\r\n,;}\]]+))"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)(?P<prefix>(?P<key_quote>['\"]?)authorization(?P=key_quote)\s*[:=]\s*)"
    r"(?:(?P<quoted_value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
    r"(?P<bare_value>[^\r\n}\]]+))"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |DSA )?PRIVATE KEY-----",
    re.DOTALL,
)
_SENSITIVE_TOKENS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[bpors]-[A-Za-z0-9-]{10,}\b"),
)


def redact_sensitive_text(msg: str) -> str:
    """Redact credential-shaped values before terminal output."""
    redacted = _PRIVATE_KEY_BLOCK.sub("<redacted>", str(msg))
    redacted = _AUTHORIZATION_VALUE.sub(_redact_assignment, redacted)
    redacted = _SENSITIVE_ASSIGNMENT.sub(_redact_assignment, redacted)
    for pattern in _SENSITIVE_TOKENS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def _redact_assignment(match: re.Match[str]) -> str:
    """Preserve assignment syntax while replacing its complete value."""
    quoted_value = match.group("quoted_value") or ""
    value_quote = quoted_value[:1]
    return f"{match.group('prefix')}{value_quote}<redacted>{value_quote}"


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
    msg = redact_sensitive_text(msg)
    if HAS_RICH:
        _stderr_console.print(f"  [bold]{msg}[/bold]")
    else:
        print(f"  {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    """Print a yellow warning to stderr."""
    msg = redact_sensitive_text(msg)
    if HAS_RICH:
        _stderr_console.print(f"  [yellow]⚠ {msg}[/yellow]")
    else:
        print(f"  ⚠ {msg}", file=sys.stderr)


def print_info(msg: str) -> None:
    """Print an info message to stderr."""
    msg = redact_sensitive_text(msg)
    # The shared output boundary redacts credential assignments and known token forms above.
    # codeql[py/clear-text-logging-sensitive-data]
    if HAS_RICH:
        _stderr_console.print(f"  [dim]{msg}[/dim]")
    else:
        print(f"  {msg}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print a green success message to stdout."""
    msg = redact_sensitive_text(msg)
    if HAS_RICH:
        _stdout_console.print(f"[green]✓[/green] {msg}")
    else:
        print(f"✓ {msg}")


def print_summary(lines: list[str]) -> None:
    """Print multi-line summary to stdout."""
    lines = [redact_sensitive_text(line) for line in lines]
    if HAS_RICH:
        _stdout_console.print("\n".join(lines))
    else:
        print("\n".join(lines))
