from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator

from src.models import RepoMetadata

logger = logging.getLogger(__name__)


@contextmanager
def _git_askpass_env(token: str | None) -> Generator[dict[str, str] | None, None, None]:
    """Create a temporary GIT_ASKPASS environment for authenticated clones."""
    if not token:
        yield None
        return

    fd, script_name = tempfile.mkstemp(prefix="git-askpass-", suffix=".sh")
    os.close(fd)
    script_path = Path(script_name)
    script_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                'case "$1" in',
                '  *Username*) printf "%s\\n" "x-access-token" ;;',
                '  *) printf "%s\\n" "$GITHUB_AUDITOR_CLONE_TOKEN" ;;',
                "esac",
            ]
        )
        + "\n"
    )
    script_path.chmod(0o700)

    env = os.environ.copy()
    env["GIT_ASKPASS"] = str(script_path)
    env["GITHUB_AUDITOR_CLONE_TOKEN"] = token
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        yield env
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


def clone_repo(clone_url: str, name: str, token: str | None = None, clone_dir: Path | None = None) -> Path:
    """Shallow-clone a single repo into clone_dir/name.

    Returns the path to the cloned repo directory.
    """
    if clone_dir is None:
        clone_dir = Path(tempfile.mkdtemp(prefix="audit-repos-"))
    dest = clone_dir / name

    try:
        with _git_askpass_env(token) as env:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", clone_url, str(dest)],
                check=True,
                capture_output=True,
                timeout=120,
                env=env,
            )
    except subprocess.CalledProcessError as exc:
        logger.warning("Clone failed for %s (git exited with %s)", name, exc.returncode)
        raise
    except subprocess.TimeoutExpired:
        logger.warning("Clone timed out for %s (120s)", name)
        raise

    return dest


@contextmanager
def clone_workspace(
    repos: list[RepoMetadata],
    token: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
) -> Generator[dict[str, Path], None, None]:
    """Context manager that clones repos into a session-unique temp dir.

    Yields a dict mapping repo name -> cloned path.
    Failed clones are skipped with a warning.

    on_progress(current, total, repo_name) — called per repo.
    on_error(repo_name, message) — called on clone failure.
    """
    with tempfile.TemporaryDirectory(prefix="audit-repos-") as tmpdir:
        clone_dir = Path(tmpdir)
        cloned: dict[str, Path] = {}
        total = len(repos)

        for i, repo in enumerate(repos, 1):
            if on_progress:
                on_progress(i, total, repo.name)
            else:
                print(
                    f"  [{i}/{total}] Cloning {repo.full_name}...",
                    file=sys.stderr,
                )
            try:
                path = clone_repo(repo.clone_url, repo.name, token, clone_dir)
                cloned[repo.name] = path
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if on_error:
                    on_error(repo.name, "clone failed")
                else:
                    print(
                        f"  ⚠ Failed to clone {repo.name}, skipping",
                        file=sys.stderr,
                    )
        yield cloned
