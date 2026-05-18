#!/usr/bin/env bash
# scripts/release.sh — distribution artifact workflow for github-repo-auditor
#
# Prerequisites:
#   pip install build twine shiv   (or: pip install ".[build]")
#
# Required env vars for --publish-pypi (one of):
#   TWINE_API_TOKEN        — PyPI API token (preferred)
#   TWINE_USERNAME + TWINE_PASSWORD  — legacy username/password
#
# Usage:
#   bash scripts/release.sh                # build + check only
#   bash scripts/release.sh --publish-pypi # build + check + upload to PyPI
#   bash scripts/release.sh --dry-run      # compatibility alias for build + check only
#
set -euo pipefail

PUBLISH_PYPI=false
SKIP_CLEAN=false
for arg in "$@"; do
    case "$arg" in
        --publish-pypi) PUBLISH_PYPI=true ;;
        --dry-run) PUBLISH_PYPI=false ;;
        --skip-clean) SKIP_CLEAN=true ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: bash scripts/release.sh [--publish-pypi] [--dry-run] [--skip-clean]"
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== github-repo-auditor release workflow ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# 1. Clean previous artifacts
echo "[1/4] Cleaning build artifacts..."
if [ "$SKIP_CLEAN" = "true" ]; then
    echo "      Skipped."
else
    python3 - <<'PY'
from pathlib import Path
import shutil

for path in [Path("dist"), Path("build"), *Path("src").glob("*.egg-info")]:
    if path.exists():
        shutil.rmtree(path)
PY
    echo "      Done."
fi

# 2. Build wheel + sdist
echo "[2/4] Building wheel + sdist..."
python3 -m build
echo "      Built:"
ls -1 dist/

# 3. Twine check
echo "[3/4] Running twine check..."
python3 -m twine check dist/*
echo "      All checks passed."

# 4. Upload only when explicitly requested.
if [ "$PUBLISH_PYPI" != "true" ]; then
    echo "[4/4] PyPI publish not requested — skipping upload."
    echo ""
    echo "=== Distribution check complete. Artifacts in dist/ ==="
    exit 0
fi

echo "[4/4] Uploading to PyPI..."
if [ -n "${TWINE_API_TOKEN:-}" ]; then
    # Use API token auth
    TWINE_USERNAME=__token__ TWINE_PASSWORD="$TWINE_API_TOKEN" \
        python3 -m twine upload dist/*
elif [ -n "${TWINE_USERNAME:-}" ] && [ -n "${TWINE_PASSWORD:-}" ]; then
    python3 -m twine upload dist/*
else
    echo ""
    echo "ERROR: No PyPI credentials found."
    echo "  Set TWINE_API_TOKEN (recommended) or TWINE_USERNAME + TWINE_PASSWORD."
    echo "  To upload manually: python3 -m twine upload dist/*"
    exit 1
fi

echo ""
echo "=== Upload complete! ==="
