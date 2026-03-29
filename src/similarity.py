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
