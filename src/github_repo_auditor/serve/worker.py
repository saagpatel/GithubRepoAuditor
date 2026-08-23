"""Fixed-command worker for server-triggered local audits."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from github_repo_auditor.serve.runner import validate_username


def _load_request() -> tuple[str, list[str], Path]:
    payload: Any = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("run request must be an object")

    username = payload.get("username")
    flag_args = payload.get("flag_args")
    output_dir = payload.get("output_dir")
    if (
        not isinstance(username, str)
        or not isinstance(flag_args, list)
        or not isinstance(output_dir, str)
    ):
        raise ValueError("run request has an invalid shape")
    if not all(isinstance(value, str) for value in flag_args):
        raise ValueError("run request flags must be strings")
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        raise ValueError("run request output_dir must be absolute")
    return validate_username(username), flag_args, output_path


def main() -> None:
    username, flag_args, output_dir = _load_request()
    # The child invokes the Python entry point directly. The values are parser
    # arguments here, not an OS command line supplied to subprocess.Popen.
    sys.argv = ["audit", username, "--output-dir", str(output_dir), *flag_args]
    from github_repo_auditor.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
