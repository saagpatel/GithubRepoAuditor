import os
import signal
from unittest.mock import patch

from src.watch import run_watch_loop


class TestWatchLoop:
    def test_runs_audit_fn(self):
        calls = []

        def audit():
            calls.append(1)
            os.kill(os.getpid(), signal.SIGINT)

        run_watch_loop(audit, interval=1)
        assert len(calls) == 1

    def test_handles_audit_error(self):
        calls = []

        def audit():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            os.kill(os.getpid(), signal.SIGINT)

        with patch("time.sleep"):
            run_watch_loop(audit, interval=1)
        assert len(calls) == 2  # Continued after error

    def test_respects_interval(self):
        sleep_calls = []

        def audit():
            os.kill(os.getpid(), signal.SIGINT)

        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            run_watch_loop(audit, interval=10)
        # Should not have slept (stopped immediately after first run)
        assert len(sleep_calls) == 0

    def test_restores_signal_handlers_after_completion(self):
        original_int = signal.getsignal(signal.SIGINT)
        original_term = signal.getsignal(signal.SIGTERM)

        def audit():
            os.kill(os.getpid(), signal.SIGINT)

        run_watch_loop(audit, interval=1)

        assert signal.getsignal(signal.SIGINT) is original_int
        assert signal.getsignal(signal.SIGTERM) is original_term

    def test_sigterm_stops_loop(self):
        calls = []

        def audit():
            calls.append(1)
            os.kill(os.getpid(), signal.SIGTERM)

        run_watch_loop(audit, interval=1)
        assert len(calls) == 1
