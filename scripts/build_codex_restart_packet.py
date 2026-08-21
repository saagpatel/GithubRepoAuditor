#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _main() -> int:
    from github_repo_auditor.codex_restart_packet import main

    return main()

if __name__ == "__main__":
    raise SystemExit(_main())
