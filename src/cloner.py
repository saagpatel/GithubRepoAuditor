from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.models import RepoMetadata

logger = logging.getLogger(__name__)

CLONE_DIR = Path("/tmp/audit-repos")


def _auth_url(clone_url: str, token: str | None) -> str:
    """Inject token into HTTPS clone URL for private repo access."""
    if token and clone_url.startswith("https://"):
        return clone_url.replace("https://", f"https://{token}@", 1)
    return clone_url


def clone_repo(clone_url: str, name: str, token: str | None = None) -> Path:
    """Shallow-clone a single repo into CLONE_DIR/name.

    Returns the path to the cloned repo directory.
    """
    dest = CLONE_DIR / name
    url = _auth_url(clone_url, token)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        # Log without the URL to avoid leaking tokens
        logger.warning("Clone failed for %s: %s", name, exc.stderr.decode().strip())
        raise
    except subprocess.TimeoutExpired:
        logger.warning("Clone timed out for %s (120s)", name)
        raise

    return dest


def cleanup() -> None:
    """Remove all cloned repos."""
    if CLONE_DIR.exists():
        shutil.rmtree(CLONE_DIR, ignore_errors=True)


@contextmanager
def clone_workspace(
    repos: list[RepoMetadata],
    token: str | None = None,
) -> Generator[dict[str, Path], None, None]:
    """Context manager that clones repos and ensures cleanup.

    Yields a dict mapping repo name -> cloned path.
    Failed clones are skipped with a warning.
    """
    CLONE_DIR.mkdir(parents=True, exist_ok=True)
    cloned: dict[str, Path] = {}
    total = len(repos)

    try:
        for i, repo in enumerate(repos, 1):
            print(
                f"  [{i}/{total}] Cloning {repo.full_name}...",
                file=sys.stderr,
            )
            try:
                path = clone_repo(repo.clone_url, repo.name, token)
                cloned[repo.name] = path
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                print(
                    f"  ⚠ Failed to clone {repo.name}, skipping",
                    file=sys.stderr,
                )
        yield cloned
    finally:
        cleanup()
