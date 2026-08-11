"""Cross-repo similarity detection via file content hashing."""
from __future__ import annotations

import hashlib
from pathlib import Path

SKIP_DIRS = frozenset({
    ".git", "node_modules", "vendor", "__pycache__", ".venv",
    "venv", ".tox", "dist", "build", ".next",
})

CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".swift",
    ".java", ".c", ".cpp", ".h", ".rb", ".php", ".gd",
})


def compute_file_hashes(repo_path: Path, max_files: int = 200) -> set[str]:
    """SHA-256 hash of first 4KB of each source file."""
    hashes: set[str] = set()
    count = 0

    for path in repo_path.rglob("*"):
        if count >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in CODE_EXTENSIONS:
            continue

        try:
            content = path.read_bytes()[:4096]
            if len(content) < 50:  # Skip tiny files
                continue
            h = hashlib.sha256(content).hexdigest()
            hashes.add(h)
            count += 1
        except OSError:
            continue

    return hashes


def find_similar_repos(
    repo_hashes: dict[str, set[str]],
    threshold: float = 0.5,
) -> list[dict]:
    """Find repo pairs sharing >threshold fraction of files.

    Returns [{repo_a, repo_b, overlap_pct, shared_files}] sorted by overlap descending.
    """
    names = list(repo_hashes.keys())
    similar: list[dict] = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            hashes_a, hashes_b = repo_hashes[a], repo_hashes[b]

            if not hashes_a or not hashes_b:
                continue

            shared = hashes_a & hashes_b
            smaller = min(len(hashes_a), len(hashes_b))

            if smaller == 0:
                continue

            overlap = len(shared) / smaller
            if overlap >= threshold:
                similar.append({
                    "repo_a": a,
                    "repo_b": b,
                    "overlap_pct": round(overlap * 100, 1),
                    "shared_files": len(shared),
                })

    similar.sort(key=lambda s: s["overlap_pct"], reverse=True)
    return similar


def classify_similarity(
    pair: dict,
    metadata_map: dict[str, dict],
) -> dict:
    """Classify a similar repo pair and add actionable suggestion.

    metadata_map: {repo_name: {fork: bool, archived: bool, size_kb: int, language: str}}
    """
    result = dict(pair)
    overlap = pair.get("overlap_pct", 0)
    repo_a = pair.get("repo_a", "")
    repo_b = pair.get("repo_b", "")
    meta_a = metadata_map.get(repo_a, {})
    meta_b = metadata_map.get(repo_b, {})

    a_fork = meta_a.get("fork", False)
    b_fork = meta_b.get("fork", False)
    a_archived = meta_a.get("archived", False)
    b_archived = meta_b.get("archived", False)
    a_size = meta_a.get("size_kb", 0)
    b_size = meta_b.get("size_kb", 0)
    same_lang = meta_a.get("language") == meta_b.get("language") and meta_a.get("language")

    if overlap > 90 and (a_fork or b_fork):
        result["classification"] = "fork_candidate"
        result["suggestion"] = f"Consider archiving the fork — {repo_a if a_fork else repo_b} appears to be a fork"
    elif overlap > 60 and not a_archived and not b_archived and a_size < 5000 and b_size < 5000:
        result["classification"] = "merge_candidate"
        result["suggestion"] = f"Consider merging {repo_a} and {repo_b} into a single repo"
    elif 50 <= overlap <= 80 and same_lang:
        result["classification"] = "shared_boilerplate"
        result["suggestion"] = f"Extract shared boilerplate from {repo_a} and {repo_b} into a template"
    else:
        result["classification"] = "similar"
        result["suggestion"] = f"{repo_a} and {repo_b} share {overlap:.0f}% of files"

    return result
