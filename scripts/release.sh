#!/usr/bin/env bash
# scripts/release.sh — PyPI publish workflow for github-repo-auditor
#
# Prerequisites:
#   pip install build twine shiv   (or: pip install ".[build]")
#
# Required env vars (one of):
#   TWINE_API_TOKEN        — PyPI API token (preferred)
#   TWINE_USERNAME + TWINE_PASSWORD  — legacy username/password
#
# Usage:
#   bash scripts/release.sh           # build + check + upload to PyPI
#   bash scripts/release.sh --dry-run # build + check only, skip upload
#
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== github-repo-auditor release workflow ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# 1. Clean previous artifacts
echo "[1/4] Cleaning dist/"
rm -rf dist/ build/ src/*.egg-info
echo "      Done."

# 2. Build wheel + sdist
echo "[2/4] Building wheel + sdist..."
python3 -m build
echo "      Built:"
ls -1 dist/

# 3. Twine check
echo "[3/4] Running twine check..."
python3 -m twine check dist/*
echo "      All checks passed."

# 4. Upload (unless --dry-run)
if [ "$DRY_RUN" = "true" ]; then
    echo "[4/4] --dry-run set — skipping upload."
    echo ""
    echo "=== Dry run complete. Artifacts in dist/ ==="
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
echo ""
echo "Next steps:"
echo "  1. Tag this release:   git tag v$(python3 -c "import importlib.metadata; print(importlib.metadata.version('github-repo-auditor'))" 2>/dev/null || grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)"
echo "  2. Push the tag:       git push origin --tags"
echo "  3. Create GitHub Release and attach dist/audit.pyz (if built)"
echo ""
