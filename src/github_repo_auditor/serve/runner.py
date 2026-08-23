"""Subprocess runner for /runs/new — spawns audit CLI and streams stdout."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import uuid
from collections import deque
from collections.abc import Generator
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

# Only flags that are valid without a value belong in the checkbox UI. The
# broader allowlist remains available to validated programmatic callers.
SAFE_BOOLEAN_FLAG_NAMES: frozenset[str] = frozenset(
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

    def __init__(
        self,
        run_id: str,
        username: str,
        flag_args: list[str],
        output_dir: Path,
    ) -> None:
        self.run_id = run_id
        self.output_dir = output_dir.resolve()
        # Keep the OS command line constant. Form-derived values are supplied
        # to the worker over stdin and become parser arguments only inside the
        # child process; they never participate in process creation.
        self.cmd = (sys.executable, "-m", "github_repo_auditor.serve.worker")
        self._request = {
            "username": username,
            "flag_args": flag_args,
            "output_dir": str(self.output_dir),
        }
        self._lines: deque[tuple[int, str]] = deque(maxlen=_MAX_LINES)
        self._next_line = 0
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._return_code: int | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    # ── internal ─────────────────────────────────────────────────────────────

    def _stream(self) -> None:
        assert self._proc is not None
        for raw in self._proc.stdout:  # type: ignore[union-attr]
            line = raw.rstrip("\n")
            with self._lock:
                self._lines.append((self._next_line, line))
                self._next_line += 1
        self._proc.wait()
        self._return_code = self._proc.returncode
        self._done.set()

    # ── public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,  # never shell=True
            )
        except OSError:
            with self._lock:
                self._lines.append(
                    (self._next_line, "Unable to start the local audit process.")
                )
                self._next_line += 1
            self._return_code = 127
            self._done.set()
            return
        assert self._proc.stdin is not None
        t = threading.Thread(target=self._stream, daemon=True)
        t.start()
        try:
            self._proc.stdin.write(json.dumps(self._request))
            self._proc.stdin.close()
        except OSError:
            with self._lock:
                self._lines.append(
                    (self._next_line, "Unable to send the local audit request.")
                )
                self._next_line += 1
            try:
                self._proc.stdin.close()
            except OSError:
                pass

    def read(self, after: int = 0) -> tuple[list[str], int, bool]:
        """Return buffered lines at or after cursor *after* without blocking.

        The returned cursor is suitable for the next call. ``truncated`` is
        true when the requested cursor predates the bounded in-memory buffer.
        """
        with self._lock:
            snapshot = list(self._lines)
            next_line = self._next_line
        oldest = snapshot[0][0] if snapshot else next_line
        truncated = after < oldest
        effective_after = max(after, oldest)
        return (
            [line for index, line in snapshot if index >= effective_after],
            next_line,
            truncated,
        )

    def tail(self, after: int = 0) -> Generator[str, None, None]:
        """Yield the currently buffered lines without waiting for completion."""
        lines, _cursor, _truncated = self.read(after=after)
        yield from lines

    def cancel(self) -> bool:
        """Request termination of a running child process.

        Returns ``True`` only when a live process received the request. A
        short background grace period avoids blocking the request handler.
        """
        proc = self._proc
        if proc is None or self._done.is_set() or proc.poll() is not None:
            return False
        self._cancel_requested = True
        proc.terminate()

        def _enforce() -> None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

        threading.Thread(target=_enforce, daemon=True).start()
        return True

    def belongs_to(self, output_dir: Path) -> bool:
        """Return whether this run belongs to one configured server root."""
        return self.output_dir == output_dir.resolve()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def return_code(self) -> int | None:
        return self._return_code

    @property
    def status(self) -> str:
        if not self.done:
            return "running"
        if self._cancel_requested:
            return "cancelled"
        return "succeeded" if self.return_code == 0 else "failed"


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
                raise ValueError(
                    f"Flag '--{norm}' value contains disallowed character(s): {bad}"
                )
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
    if any(name.replace("_", "-").lstrip("-") == "output-dir" for name in flags):
        raise ValueError("Flag '--output-dir' is controlled by the local server")
    flag_args = validate_flags(flags)
    run_id = uuid.uuid4().hex
    session = RunSession(
        run_id=run_id,
        username=safe_username,
        flag_args=flag_args,
        output_dir=output_dir,
    )
    with _registry_lock:
        _registry[run_id] = session
    session.start()
    return run_id


def get_session(run_id: str) -> RunSession | None:
    with _registry_lock:
        return _registry.get(run_id)
