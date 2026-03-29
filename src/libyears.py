from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.cache import ResponseCache

logger = logging.getLogger(__name__)

# Registry URLs
NPM_REGISTRY = "https://registry.npmjs.org"
PYPI_REGISTRY = "https://pypi.org/pypi"
CRATES_REGISTRY = "https://crates.io/api/v1/crates"

# 24-hour TTL for registry lookups
REGISTRY_TTL = 86400


def compute_libyears(
    repo_path: Path,
    manifests: list[str],
    cache: ResponseCache | None = None,
) -> dict:
    """Compute dependency freshness in libyears.

    Returns {total_libyears, dep_count, freshness_score, details}.
    """
    deps: list[tuple[str, str, str]] = []  # (name, version, ecosystem)

    if "package.json" in manifests:
        deps.extend(_parse_npm_deps(repo_path / "package.json"))
    if "requirements.txt" in manifests:
        deps.extend(_parse_pip_deps(repo_path / "requirements.txt"))
    if "Cargo.toml" in manifests:
        deps.extend(_parse_cargo_deps(repo_path / "Cargo.toml"))
    if "pyproject.toml" in manifests:
        deps.extend(_parse_pyproject_deps(repo_path / "pyproject.toml"))

    if not deps:
        return {"total_libyears": None, "dep_count": 0, "freshness_score": None, "dependency_names": []}

    total_libyears = 0.0
    checked = 0

    for name, version, ecosystem in deps[:30]:  # Cap at 30 deps for speed
        age = _get_dep_age(name, version, ecosystem, cache)
        if age is not None:
            total_libyears += age
            checked += 1

    # Score: 0 libyears = 1.0, 10 = 0.5, 50+ = 0.0
    if checked == 0:
        freshness_score = None
    elif total_libyears <= 0:
        freshness_score = 1.0
    elif total_libyears <= 10:
        freshness_score = round(1.0 - (total_libyears / 20), 2)
    elif total_libyears <= 50:
        freshness_score = round(0.5 - ((total_libyears - 10) / 80), 2)
    else:
        freshness_score = 0.0

    return {
        "total_libyears": round(total_libyears, 1),
        "dep_count_checked": checked,
        "freshness_score": max(0.0, freshness_score) if freshness_score is not None else None,
        "dependency_names": [name for name, _, _ in deps],
        "dep_versions": [(name, version, ecosystem) for name, version, ecosystem in deps],
    }


def _parse_npm_deps(path: Path) -> list[tuple[str, str, str]]:
    """Parse package.json dependencies."""
    try:
        pkg = json.loads(path.read_text(errors="replace"))
        deps = []
        for section in ("dependencies", "devDependencies"):
            for name, version in pkg.get(section, {}).items():
                # Strip version prefixes: ^, ~, >=, etc.
                clean = re.sub(r"^[\^~>=<]+", "", version).strip()
                if clean and clean[0].isdigit():
                    deps.append((name, clean, "npm"))
        return deps
    except (json.JSONDecodeError, OSError):
        return []


def _parse_pip_deps(path: Path) -> list[tuple[str, str, str]]:
    """Parse requirements.txt pinned versions."""
    deps = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"([a-zA-Z0-9_-]+)==([0-9.]+)", line)
            if match:
                deps.append((match.group(1), match.group(2), "pypi"))
    except OSError:
        pass
    return deps


def _parse_cargo_deps(path: Path) -> list[tuple[str, str, str]]:
    """Parse Cargo.toml [dependencies] versions."""
    deps = []
    try:
        content = path.read_text(errors="replace")
        in_deps = False
        for line in content.splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                continue
            if line.strip().startswith("[") and in_deps:
                break
            if in_deps and "=" in line:
                match = re.match(r'(\S+)\s*=\s*"([0-9.]+)"', line.strip())
                if match:
                    deps.append((match.group(1), match.group(2), "crates"))
    except OSError:
        pass
    return deps


def _parse_pyproject_deps(path: Path) -> list[tuple[str, str, str]]:
    """Parse pyproject.toml dependencies list."""
    deps = []
    try:
        content = path.read_text(errors="replace")
        in_deps = False
        for line in content.splitlines():
            if "dependencies" in line and "=" in line and "[" in line:
                in_deps = True
                continue
            if in_deps and line.strip() == "]":
                break
            if in_deps:
                match = re.match(r'\s*"([a-zA-Z0-9_-]+)([><=~!]+)([0-9.]+)', line)
                if match:
                    deps.append((match.group(1), match.group(3), "pypi"))
    except OSError:
        pass
    return deps


def _get_dep_age(
    name: str,
    version: str,
    ecosystem: str,
    cache: ResponseCache | None,
) -> float | None:
    """Get age of a specific dependency version in years."""
    try:
        if ecosystem == "npm":
            return _npm_dep_age(name, version, cache)
        if ecosystem == "pypi":
            return _pypi_dep_age(name, version, cache)
        if ecosystem == "crates":
            return _crates_dep_age(name, version, cache)
    except Exception:
        return None
    return None


def _fetch_cached(url: str, cache: ResponseCache | None) -> dict | None:
    """Fetch JSON with optional caching."""
    if cache:
        cached = cache.get(url)
        if cached is not None:
            return cached

    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "github-repo-auditor"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        if cache:
            cache.put(url, None, data)
        return data
    except (requests.RequestException, ValueError):
        return None


def _npm_dep_age(name: str, version: str, cache: ResponseCache | None) -> float | None:
    """Get age of an npm package version."""
    data = _fetch_cached(f"{NPM_REGISTRY}/{name}", cache)
    if not data or "time" not in data:
        return None
    times = data["time"]
    latest_version = data.get("dist-tags", {}).get("latest")
    installed_date = times.get(version)
    latest_date = times.get(latest_version) if latest_version else None
    if installed_date and latest_date:
        try:
            inst = datetime.fromisoformat(installed_date.replace("Z", "+00:00"))
            lat = datetime.fromisoformat(latest_date.replace("Z", "+00:00"))
            return max(0, (lat - inst).days / 365.25)
        except (ValueError, TypeError):
            return None
    return None


def _pypi_dep_age(name: str, version: str, cache: ResponseCache | None) -> float | None:
    """Get age of a PyPI package version."""
    data = _fetch_cached(f"{PYPI_REGISTRY}/{name}/json", cache)
    if not data:
        return None
    latest_version = data.get("info", {}).get("version")
    releases = data.get("releases", {})
    installed_files = releases.get(version, [])
    latest_files = releases.get(latest_version, [])
    if installed_files and latest_files:
        try:
            inst_date = installed_files[0].get("upload_time_iso_8601", "")
            lat_date = latest_files[0].get("upload_time_iso_8601", "")
            inst = datetime.fromisoformat(inst_date.replace("Z", "+00:00"))
            lat = datetime.fromisoformat(lat_date.replace("Z", "+00:00"))
            return max(0, (lat - inst).days / 365.25)
        except (ValueError, TypeError, IndexError):
            return None
    return None


def _crates_dep_age(name: str, version: str, cache: ResponseCache | None) -> float | None:
    """Get age of a crates.io package version."""
    data = _fetch_cached(f"{CRATES_REGISTRY}/{name}", cache)
    if not data or "versions" not in data:
        return None
    versions = data.get("versions", [])
    installed_date = None
    latest_date = None
    for v in versions:
        if v.get("num") == version:
            installed_date = v.get("created_at")
        if not latest_date:
            latest_date = v.get("created_at")  # First = most recent
    if installed_date and latest_date:
        try:
            inst = datetime.fromisoformat(installed_date.replace("Z", "+00:00"))
            lat = datetime.fromisoformat(latest_date.replace("Z", "+00:00"))
            return max(0, (lat - inst).days / 365.25)
        except (ValueError, TypeError):
            return None
    return None
