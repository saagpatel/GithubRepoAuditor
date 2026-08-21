"""Watch mode — re-run audit on interval."""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timezone
from typing import Callable


def run_watch_loop(audit_fn: Callable[[], None], interval: int = 3600) -> None:
    """Run audit_fn repeatedly with sleep between runs.

    Handles SIGINT and SIGTERM gracefully, completing the current run before
    stopping. If audit_fn raises, the error is logged and the loop continues.
    """
    stop = False

    def _handle_signal(sig: int, frame: object) -> None:
        nonlocal stop
        print("\n  Watch mode: shutting down gracefully...", file=sys.stderr)
        stop = True

    old_int = signal.signal(signal.SIGINT, _handle_signal)
    old_term = signal.signal(signal.SIGTERM, _handle_signal)

    run_count = 0
    try:
        while not stop:
            run_count += 1
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            print(f"\n{'=' * 60}", file=sys.stderr)
            print(f"  Watch mode: run #{run_count} at {ts}", file=sys.stderr)
            print(f"{'=' * 60}", file=sys.stderr)

            try:
                audit_fn()
            except Exception as e:
                print(f"  Watch mode: error in run #{run_count}: {e}", file=sys.stderr)

            if stop:
                break

            print(
                f"  Watch mode: next run in {interval}s. Press Ctrl+C to stop.",
                file=sys.stderr,
            )
            elapsed = 0
            while elapsed < interval and not stop:
                time.sleep(min(5, interval - elapsed))
                elapsed += 5
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)

    print(f"  Watch mode: completed {run_count} runs.", file=sys.stderr)
