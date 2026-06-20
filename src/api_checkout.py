"""Materialize a sparse, API-sourced repo skeleton for clone-free scoring.

The audit engine's analyzers read a repo from the local filesystem. To score an
arbitrary public GitHub user *without* cloning every repo (the hosted, multi-tenant
path), this module reconstructs a sparse on-disk skeleton from the GitHub API:

* one Git Trees API call yields every path → directories are created and files are
  ``touch``-ed so presence-based analyzers (structure, testing, CI, docs, build)
  see the real shape of the repo;
* a bounded set of high-signal files (README, dependency manifests) are fetched via
  the Contents API and written with real content, so content-based analyzers
  (README quality, dependency counts, test-framework detection) still work.

The existing analyzers run against this skeleton unmodified. ``materialize_api_workspace``
mirrors ``cloner.clone_workspace`` exactly (context manager yielding ``{name: Path}``),
so it is a drop-in replacement for the clone step.

Materialization is sequential on purpose: it keeps API access well under GitHub's
secondary rate limits (concurrent-request and points-per-minute caps) that a
parallel burst across many repos would trip.
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Generator

from src.models import RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 5000
DEFAULT_MAX_CONTENT_FILES = 20

# Files whose *content* (not just presence) carries real scoring signal. Matched
# case-insensitively by basename; anything starting with ``readme`` also qualifies.
CONTENT_FILE_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "gemfile",
    "composer.json",
}


def _is_content_file(path: str) -> bool:
    base = path.rsplit("/", 1)[-1].lower()
    return base.startswith("readme") or base in CONTENT_FILE_NAMES


def _safe_target(dest: Path, rel: str) -> Path | None:
    """Resolve ``rel`` under ``dest``, rejecting traversal/absolute escapes.

    Tree paths come from arbitrary remote repos, so a malicious entry like
    ``../../etc/passwd`` or ``/abs/evil`` must never resolve outside ``dest``.
    """
    rel = rel.strip()
    if not rel or rel in (".", "..") or "\x00" in rel:
        return None
    candidate = (dest / rel).resolve()
    dest_resolved = dest.resolve()
    if candidate == dest_resolved:
        return None
    if dest_resolved not in candidate.parents:
        return None
    return candidate


def materialize_api_checkout(
    metadata: RepoMetadata,
    client: "GitHubClient",
    dest: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_content_files: int = DEFAULT_MAX_CONTENT_FILES,
) -> Path:
    """Build a sparse skeleton of one repo under ``dest`` from the GitHub API.

    Returns ``dest``. If the repo tree is unavailable (empty repo, missing ref,
    or an API error), ``dest`` is created empty so downstream analyzers score it
    as a near-empty repo rather than crashing.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    owner, _, repo = metadata.full_name.partition("/")
    if not owner or not repo:
        logger.warning(
            "Cannot materialize %r: full_name is not 'owner/repo'",
            metadata.full_name,
        )
        return dest

    tree = client.get_repo_tree(owner, repo, metadata.default_branch)
    if not tree.get("available"):
        return dest
    if tree.get("truncated"):
        logger.warning(
            "Tree truncated for %s — skeleton is incomplete", metadata.full_name
        )

    for rel in tree.get("dirs", []):
        target = _safe_target(dest, rel)
        if target is not None:
            target.mkdir(parents=True, exist_ok=True)

    content_budget = max_content_files
    for rel in tree.get("files", [])[:max_files]:
        target = _safe_target(dest, rel)
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        text = ""
        if content_budget > 0 and _is_content_file(rel):
            fetched = client.get_file_content(
                owner, repo, rel, ref=metadata.default_branch
            )
            if fetched is not None:
                text = fetched
                content_budget -= 1
        target.write_text(text, encoding="utf-8")

    return dest


@contextmanager
def materialize_api_workspace(
    repos: list[RepoMetadata],
    client: "GitHubClient",
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_content_files: int = DEFAULT_MAX_CONTENT_FILES,
) -> Generator[dict[str, Path], None, None]:
    """Materialize API skeletons for many repos into a session-unique temp dir.

    Drop-in replacement for ``cloner.clone_workspace``: yields a dict mapping
    repo name → skeleton path. A repo that fails to materialize is skipped with
    a warning so one bad repo never aborts a portfolio scan.
    """
    with tempfile.TemporaryDirectory(prefix="audit-api-") as tmpdir:
        root = Path(tmpdir)
        workspace: dict[str, Path] = {}
        total = len(repos)
        for index, repo in enumerate(repos, 1):
            if on_progress:
                on_progress(index, total, repo.name)
            try:
                dest = materialize_api_checkout(
                    repo,
                    client,
                    root / repo.name,
                    max_files=max_files,
                    max_content_files=max_content_files,
                )
                workspace[repo.name] = dest
            except Exception as exc:  # noqa: BLE001 — one bad repo must not abort the scan
                logger.warning("API checkout failed for %s: %s", repo.name, exc)
                if on_error:
                    on_error(repo.name, str(exc))
        yield workspace
