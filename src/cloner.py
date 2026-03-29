from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator

from src.models import RepoMetadata

logger = logging.getLogger(__name__)


def _auth_url(clone_url: str, token: str | None) -> str:
    """Inject token into HTTPS clone URL for private repo access."""
    if token and clone_url.startswith("https://"):
        return clone_url.replace("https://", f"https://{token}@", 1)
    return clone_url


def clone_repo(clone_url: str, name: str, token: str | None = None, clone_dir: Path | None = None) -> Path:
    """Shallow-clone a single repo into clone_dir/name.

    Returns the path to the cloned repo directory.
    """
    if clone_dir is None:
        clone_dir = Path(tempfile.mkdtemp(prefix="audit-repos-"))
    dest = clone_dir / name
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
