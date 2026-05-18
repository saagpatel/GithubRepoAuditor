from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

logger = logging.getLogger(__name__)

LOCKFILES = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "go.sum",
    "bun.lockb",
)

MANIFESTS = (
    "package.json",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pyproject.toml",
    "Pipfile",
    "Gemfile",
    "composer.json",
    "setup.py",
    "setup.cfg",
    "pom.xml",
    "build.gradle",
    "Package.swift",
)


class DependenciesAnalyzer(BaseAnalyzer):
    name = "dependencies"
    weight = 0.10

    def cache_inputs_hash(
        self,
        repo_path: Path | None,
        metadata: RepoMetadata,
    ) -> str | None:
        """Hash the bytes of all present lockfiles + manifest files.

        Returns None if repo_path is not available or no dependency files exist,
        so the analyzer runs unconditionally in those cases.
        """
        if repo_path is None:
            return None
        pieces: list[bytes] = []
        for fname in LOCKFILES + MANIFESTS:
            fpath = repo_path / fname
            if fpath.is_file():
                try:
                    pieces.append(fname.encode())
                    pieces.append(fpath.read_bytes())
                except OSError:
                    pass
        if not pieces:
            return None
        h = hashlib.sha256()
        for piece in pieces:
            h.update(piece)
            h.update(b"\x00")
        return h.hexdigest()

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
        sbom_source: str = "lockfile",
    ) -> AnalyzerResult:
        """Analyze dependencies for a repo.

        Args:
            repo_path:     Local clone path.
            metadata:      Repo metadata from the GitHub API.
            github_client: Optional GitHubClient instance.
            sbom_source:   ``"lockfile"`` (default, existing path) or ``"github"``
                           (fetch SPDX SBOM from GitHub's dependency graph API).
                           When ``"github"`` is requested but the call fails (403/404,
                           network error), the analyzer falls back to the lockfile path
                           for *this repo only* and logs at INFO level.
        """
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # Lockfile exists (always computed for scoring context)
        found_lockfiles = [f for f in LOCKFILES if (repo_path / f).is_file()]
        details["lockfiles"] = found_lockfiles
        if found_lockfiles:
            score += 0.4
            findings.append(f"Lockfiles: {', '.join(found_lockfiles)}")
        else:
            findings.append("No lockfile found")

        # Manifest exists (always computed)
        found_manifests = [f for f in MANIFESTS if (repo_path / f).is_file()]
        details["manifests"] = found_manifests
        if found_manifests:
            score += 0.4
            findings.append(f"Manifests: {', '.join(found_manifests)}")
        else:
            findings.append("No dependency manifest found")

        # Dependency count — via SBOM or local lockfile parsing
        dep_count: int | None = None
        sbom_used = False

        if sbom_source == "github" and github_client is not None:
            owner, _, repo_name = metadata.full_name.partition("/")
            if owner and repo_name:
                try:
                    sbom_result = github_client.get_dependency_sbom(owner, repo_name)  # type: ignore[union-attr]
                    if sbom_result.get("available"):
                        packages = sbom_result.get("packages", [])
                        dep_count = sbom_result.get("package_count", len(packages))
                        details["sbom_packages"] = packages
                        details["sbom_source"] = "github"
                        sbom_used = True
                    else:
                        logger.info(
                            "SBOM unavailable for %s (%s) — falling back to lockfile",
                            metadata.full_name,
                            sbom_result.get("reason", "unknown"),
                        )
                except Exception as exc:
                    logger.warning(
                        "SBOM fetch failed for %s: %s — falling back to lockfile",
                        metadata.full_name,
                        exc,
                    )
            else:
                logger.info(
                    "Cannot determine owner/repo from full_name %r — using lockfile",
                    metadata.full_name,
                )

        if not sbom_used:
            dep_count = _count_dependencies(repo_path, found_manifests)
            details["sbom_source"] = "lockfile"

        details["dep_count"] = dep_count
        if dep_count is not None:
            if 1 <= dep_count <= 500:
                score += 0.2
                findings.append(f"Dependency count: {dep_count}")
            elif dep_count > 500:
                findings.append(f"Excessive dependencies: {dep_count}")
            else:
                findings.append("Zero dependencies declared")
        else:
            findings.append("Could not determine dependency count")

        # Libyears freshness (optional — requires network for registry queries)
        if found_manifests:
            try:
                from src.cache import ResponseCache
                from src.libyears import compute_libyears

                cache = ResponseCache(ttl=86400)  # 24hr for registries
                libyears_data = compute_libyears(repo_path, found_manifests, cache)
                # libyears also emits a 'dep_count' key — preserve ours if already set
                _saved_dep_count = details.get("dep_count")
                details.update(libyears_data)
                if _saved_dep_count is not None:
                    details["dep_count"] = _saved_dep_count
                if libyears_data.get("total_libyears") is not None:
                    findings.append(f"Libyears: {libyears_data['total_libyears']}")
            except Exception:
                pass  # Non-fatal — libyears is a bonus signal

        return self._result(score, findings, details)


def _count_dependencies(repo_path: Path, manifests: list[str]) -> int | None:
    """Try to count declared dependencies from the first parseable manifest."""
    if "package.json" in manifests:
        try:
            pkg = json.loads((repo_path / "package.json").read_text(errors="replace"))
            deps = len(pkg.get("dependencies", {}))
            dev_deps = len(pkg.get("devDependencies", {}))
            return deps + dev_deps
        except (json.JSONDecodeError, OSError):
            pass

    if "requirements.txt" in manifests:
        try:
            lines = (repo_path / "requirements.txt").read_text(errors="replace").splitlines()
            return sum(
                1
                for line in lines
                if line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith("-")
            )
        except OSError:
            pass

    if "Cargo.toml" in manifests:
        try:
            content = (repo_path / "Cargo.toml").read_text(errors="replace")
            # Count lines in [dependencies] section
            in_deps = False
            count = 0
            for line in content.splitlines():
                if line.strip() == "[dependencies]":
                    in_deps = True
                    continue
                if line.strip().startswith("[") and in_deps:
                    break
                if in_deps and "=" in line and line.strip():
                    count += 1
            return count
        except OSError:
            pass

    if "go.mod" in manifests:
        try:
            content = (repo_path / "go.mod").read_text(errors="replace")
            in_require = False
            count = 0
            for line in content.splitlines():
                if line.strip().startswith("require"):
                    in_require = True
                    continue
                if in_require and line.strip() == ")":
                    break
                if in_require and line.strip():
                    count += 1
            return count
        except OSError:
            pass

    if "pyproject.toml" in manifests:
        try:
            content = (repo_path / "pyproject.toml").read_text(errors="replace")
            # Look for dependencies list
            in_deps = False
            count = 0
            for line in content.splitlines():
                if "dependencies" in line and "=" in line:
                    in_deps = True
                    continue
                if in_deps and line.strip() == "]":
                    break
                if in_deps and line.strip().startswith('"'):
                    count += 1
            return count if count > 0 else None
        except OSError:
            pass

    return None
