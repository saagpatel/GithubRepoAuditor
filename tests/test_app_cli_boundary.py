"""Architecture guardrail for the CLI-to-application dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).parent.parent / "src" / "app"


def _cli_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            violations.extend(alias.name for alias in node.names if alias.name == "src.cli")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "src.cli":
                violations.append("from src.cli")
            elif node.module == "src" and any(alias.name == "cli" for alias in node.names):
                violations.append("from src import cli")
    return violations


def test_app_layer_does_not_depend_on_cli() -> None:
    """CLI dispatches into app flows; app flows must not import the dispatcher."""
    violations = {
        path.relative_to(APP_ROOT).as_posix(): _cli_imports(path)
        for path in APP_ROOT.rglob("*.py")
        if _cli_imports(path)
    }
    assert violations == {}
