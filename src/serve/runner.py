"""Subprocess runner for /runs/new — spawns audit CLI and streams stdout."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import uuid
from collections import deque
from collections.abc import Generator  # noqa: F401  (used in type annotation)
from pathlib import Path

# ── Allowlist of safe audit flags that can be passed via the web UI ──────────
SAFE_FLAG_NAMES: frozenset[str] = frozenset(
    {
        "portfolio-truth",
        "portfolio-context-recovery",
        "control-center",
        "briefing",
        "approval-center",
        "doctor",
        "html",
        "pdf",
        "review-pack",
        "output-dir",
        "excel-mode",
        "portfolio-profile",
    }
)

# Shell metacharacters that must never appear in flag values
_SHELL_METACHAR = set(";|&$`\\<>!")

# GitHub usernames and organization names are limited to alphanumerics plus
# single hyphens, cannot start/end with a hyphen, and max out at 39 chars.
_GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

# Max lines kept per run
_MAX_LINES = 200


class RunSession:
    """Holds state for one spawned audit subprocess."""

    def __init__(self, run_id: str, cmd: list[str]) -> None:
        self.run_id = run_id
        self.cmd = cmd
        self._lines: deque[str] = deque(maxlen=_MAX_LINES)
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._return_code: int | None = None
        self._proc: subprocess.Popen[str] | None = None

    # ── internal ─────────────────────────────────────────────────────────────

    def _stream(self) -> None:
        assert self._proc is not None
        for raw in self._proc.stdout:  # type: ignore[union-attr]
            line = raw.rstrip("\n")
            with self._lock:
                self._lines.append(line)
        self._proc.wait()
        self._return_code = self._proc.returncode
        self._done.set()

    # ── public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,  # never shell=True
        )
        t = threading.Thread(target=self._stream, daemon=True)
        t.start()

    def tail(self, after: int = 0) -> Generator[str, None, None]:
        """Yield all buffered lines from position *after*, then any new ones."""
        sent = after
        while True:
            with self._lock:
                snapshot = list(self._lines)
            for line in snapshot[sent:]:
                sent += 1
                yield line
            if self._done.is_set():
                break

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def return_code(self) -> int | None:
        return self._return_code


# ── Registry ──────────────────────────────────────────────────────────────────

_registry: dict[str, RunSession] = {}
_registry_lock = threading.Lock()


def validate_flags(flags: dict[str, str | bool]) -> list[str]:
    """Return a flat CLI argument list after validating flag names and values.

    Raises ValueError with a descriptive message on any violation.
    """
    args: list[str] = []
    for name, value in flags.items():
        # Normalise dashes/underscores
        norm = name.replace("_", "-").lstrip("-")
        if norm not in SAFE_FLAG_NAMES:
            raise ValueError(f"Flag '--{norm}' is not in the allowed list")
        if isinstance(value, bool):
            if value:
                args.append(f"--{norm}")
        else:
            val_str = str(value)
            bad = _SHELL_METACHAR.intersection(val_str)
            if bad:
                raise ValueError(f"Flag '--{norm}' value contains disallowed character(s): {bad}")
            args.extend([f"--{norm}", val_str])
    return args


def validate_username(username: str) -> str:
    """Return a safe GitHub username/org name for subprocess arguments."""
    candidate = username.strip()
    if not _GITHUB_OWNER_RE.fullmatch(candidate):
        raise ValueError("Username must be a valid GitHub owner name")
    if "--" in candidate:
        raise ValueError("Username must not contain consecutive hyphens")
    return candidate


def spawn_run(username: str, flags: dict[str, str | bool], output_dir: Path) -> str:
    """Validate flags, spawn audit subprocess, register session.  Returns run_id."""
    safe_username = validate_username(username)
    flag_args = validate_flags(flags)
    run_id = uuid.uuid4().hex
    cmd = [sys.executable, "-m", "src.cli", safe_username, *flag_args]
    session = RunSession(run_id=run_id, cmd=cmd)
    with _registry_lock:
        _registry[run_id] = session
    session.start()
    return run_id


def get_session(run_id: str) -> RunSession | None:
    with _registry_lock:
        return _registry.get(run_id)
