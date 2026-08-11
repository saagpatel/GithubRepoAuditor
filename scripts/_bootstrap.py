from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def ensure_project_root() -> Path:
    """Make repo-local imports work when scripts are run directly."""
    source_root_text = str(SOURCE_ROOT)
    if source_root_text not in sys.path:
        sys.path.insert(0, source_root_text)
    return ROOT
