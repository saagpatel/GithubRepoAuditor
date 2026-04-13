from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re

from src.analyzers.code_quality import TODO_PATTERN
from src.analyzers.dependencies import LOCKFILES, MANIFESTS
from src.analyzers.security import _find_dangerous_files, _scan_secrets
from src.models import RepoAudit

SKIP_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
    "venv",
}
CODE_EXTENSIONS = {
    ".bash",
    ".c",
    ".cpp",
    ".cs",
    ".ex",
    ".exs",
    ".go",
    ".h",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zig",
}
STRUCTURE_ENTRY_FILES = (
    "main.py",
    "app.py",
    "manage.py",
    "index.js",
    "index.ts",
    "src/main.py",
    "src/app.py",
    "src/index.ts",
    "src/index.js",
    "src/App.tsx",
    "App.tsx",
    "main.go",
    "src/main.rs",
    "config.ru",
    "Program.cs",
    "Package.swift",
)
BRANCH_KEYWORD_PATTERN = re.compile(r"\b(if|elif|else|for|while|try|except|case|match|with)\b")


def build_implementation_hotspots(repo_path: Path | None, audit: RepoAudit) -> list[dict]:
    if repo_path is None or not repo_path.exists():
        return []

    candidates: list[dict] = []
    candidates.extend(_python_complexity_candidates(repo_path))
    candidates.extend(_todo_density_candidates(repo_path))
    candidates.extend(_security_candidates(repo_path))
    candidates.extend(_dependency_candidates(repo_path, audit))
    candidates.extend(_structure_candidates(repo_path, audit))
    candidates.extend(_aggregate_module_candidates(candidates))
    candidates.sort(
        key=lambda item: (
            float(item.get("pressure_score", 0.0)),
            1 if item.get("scope") == "file" else 0,
            str(item.get("path", "")),
        ),
        reverse=True,
    )
    return _dedupe_hotspots(candidates, limit=5)


def build_portfolio_implementation_hotspots(audits: list[RepoAudit]) -> list[dict]:
    items: list[dict] = []
    for audit in audits:
        for hotspot in audit.implementation_hotspots:
            items.append({"repo": audit.metadata.name, "tier": audit.completeness_tier, **hotspot})
    items.sort(key=lambda item: float(item.get("pressure_score", 0.0)), reverse=True)
    return items[:20]


def build_implementation_hotspots_summary(audits: list[RepoAudit]) -> dict:
    portfolio_items = build_portfolio_implementation_hotspots(audits)
    repos_with_hotspots = [audit.metadata.name for audit in audits if audit.implementation_hotspots]
    suggestion_counts = Counter(item.get("suggestion_type", "refactor") for item in portfolio_items)
    category_counts = Counter(item.get("category", "unknown") for item in portfolio_items)
    if not portfolio_items:
        summary = "No meaningful implementation hotspots are currently surfaced."
    else:
        sample = portfolio_items[0]
        start_label = _hotspot_display_label(sample)
        summary = (
            f"{len(repos_with_hotspots)} repos have concrete implementation pressure. "
            f"Start with {sample.get('repo', 'the top repo')} in {start_label}."
        )
    return {
        "summary": summary,
        "total_hotspots": len(portfolio_items),
        "repos_with_hotspots": len(repos_with_hotspots),
        "top_paths": [
            {
                "repo": item.get("repo", ""),
                "path": item.get("path", ""),
                "category": item.get("category", ""),
                "pressure_score": item.get("pressure_score", 0.0),
                "suggestion_type": item.get("suggestion_type", ""),
            }
            for item in portfolio_items[:5]
        ],
        "categories": dict(category_counts),
        "suggestion_types": dict(suggestion_counts),
    }


def _python_complexity_candidates(repo_path: Path, *, max_files: int = 60) -> list[dict]:
    candidates: list[dict] = []
    files_analyzed = 0
    for py_file in repo_path.rglob("*.py"):
        if files_analyzed >= max_files or _should_skip(py_file, repo_path):
            continue
        source = _read_text(py_file)
        if not source.strip():
            continue
        files_analyzed += 1
        metrics = _python_complexity_metrics(source)
        if metrics["pressure_score"] < 0.45:
            continue
        rel_path = str(py_file.relative_to(repo_path))
        score = metrics["pressure_score"]
        candidates.append(
            _build_hotspot(
                scope="file",
                path=rel_path,
                module=_module_name(rel_path),
                category="code-complexity",
                pressure_score=score,
                suggestion_type="refactor",
                why_it_matters=(
                    f"{rel_path} carries concentrated branching or function complexity, "
                    "which makes safe edits slower and regressions easier to miss."
                ),
                suggested_first_move=(
                    "Split the heaviest function into a few narrower helpers and add one focused regression test around the branchiest path."
                ),
                signal_summary=(
                    f"Complexity pressure {score:.2f} across {metrics['complex_blocks']} complex blocks, "
                    f"worst function score {metrics['worst_complexity']}."
                ),
            )
        )
    return candidates


def _todo_density_candidates(repo_path: Path, *, max_files: int = 160) -> list[dict]:
    candidates: list[dict] = []
    files_scanned = 0
    for path in repo_path.rglob("*"):
        if files_scanned >= max_files or not path.is_file() or path.suffix not in CODE_EXTENSIONS:
            continue
        if _should_skip(path, repo_path):
            continue
        source = _read_text(path)
        lines = source.splitlines()
        if not lines:
            continue
        files_scanned += 1
        todo_count = sum(1 for line in lines if TODO_PATTERN.search(line))
        if todo_count == 0:
            continue
        density = (todo_count / max(len(lines), 1)) * 1000
        pressure = min(1.0, 0.22 + min(todo_count, 8) * 0.08 + min(density, 25) * 0.02)
        if pressure < 0.5:
            continue
        rel_path = str(path.relative_to(repo_path))
        candidates.append(
            _build_hotspot(
                scope="file",
                path=rel_path,
                module=_module_name(rel_path),
                category="todo-density",
                pressure_score=round(pressure, 3),
                suggestion_type="refactor",
                why_it_matters=(
                    f"{rel_path} is carrying visible TODO/FIXME debt, which usually signals unfinished behavior or cleanup drag in the exact place you will edit next."
                ),
                suggested_first_move="Convert the oldest TODO/FIXME into one concrete cleanup task or test, then remove or rewrite the stale notes around it.",
                signal_summary=f"{todo_count} TODO/FIXME markers across {len(lines)} lines ({density:.1f} per 1k LOC).",
            )
        )
    return candidates


def _security_candidates(repo_path: Path) -> list[dict]:
    candidates: list[dict] = []
    dangerous_files = _find_dangerous_files(repo_path)
    secret_hits = _scan_secrets(repo_path)
    secret_paths = defaultdict(list)
    for label, rel_path in secret_hits:
        secret_paths[rel_path].append(label)

    for rel_path in dangerous_files:
        rel_path_str = str(rel_path)
        score = 0.82 if Path(rel_path_str).suffix in {".pem", ".key", ".p12", ".pfx"} else 0.75
        candidates.append(
            _build_hotspot(
                scope="file",
                path=rel_path_str,
                module=_module_name(rel_path_str),
                category="security-exposure",
                pressure_score=round(score, 3),
                suggestion_type="security",
                why_it_matters=f"{rel_path_str} looks like a committed sensitive file, which raises immediate security and cleanup risk.",
                suggested_first_move="Remove or rotate the sensitive material, replace it with an example/template file, and document the safe local setup path.",
                signal_summary="Dangerous committed file detected by the local security scan.",
            )
        )

    for rel_path, labels in secret_paths.items():
        score = min(1.0, 0.76 + len(labels) * 0.05)
        label_summary = ", ".join(labels[:2])
        candidates.append(
            _build_hotspot(
                scope="file",
                path=rel_path,
                module=_module_name(rel_path),
                category="security-exposure",
                pressure_score=round(score, 3),
                suggestion_type="security",
                why_it_matters=f"{rel_path} contains content that matches exposed-secret patterns, so it should be reviewed before further promotion or reuse.",
                suggested_first_move="Verify whether the secret is real, rotate anything live, and move the remaining placeholder material into a safe example file.",
                signal_summary=f"Potential secret patterns detected: {label_summary}.",
            )
        )

    return candidates


def _dependency_candidates(repo_path: Path, audit: RepoAudit) -> list[dict]:
    details = _dimension_details(audit).get("dependencies", {})
    manifests = list(details.get("manifests") or [])
    lockfiles = list(details.get("lockfiles") or [])
    dep_count = int(details.get("dep_count") or 0)
    if not manifests:
        return []

    pressure = 0.0
    signals: list[str] = []
    if not lockfiles:
        pressure += 0.4
        signals.append("no lockfile")
    if dep_count >= 120:
        pressure += min(0.35, dep_count / 600)
        signals.append(f"{dep_count} declared dependencies")
    dependency_score = _dimension_scores(audit).get("dependencies", 1.0)
    if dependency_score < 0.6:
        pressure += 0.2
        signals.append(f"dependencies score {dependency_score:.2f}")
    if pressure < 0.35:
        return []

    target_path = manifests[0] if manifests else (lockfiles[0] if lockfiles else "")
    return [
        _build_hotspot(
            scope="file",
            path=target_path,
            module=_module_name(target_path),
            category="dependency-fragility",
            pressure_score=round(min(1.0, 0.25 + pressure), 3),
            suggestion_type="dependency",
            why_it_matters=(
                f"{target_path} is carrying dependency-management pressure, which makes builds harder to trust and upgrades harder to reason about."
            ),
            suggested_first_move="Refresh the primary manifest/lockfile pair first, then capture one reproducible install path in the README or CI config.",
            signal_summary="Dependency signals: " + ", ".join(signals) + ".",
        )
    ]


def _structure_candidates(repo_path: Path, audit: RepoAudit) -> list[dict]:
    score_map = _dimension_scores(audit)
    details_map = _dimension_details(audit)
    ship_readiness = audit.lenses.get("ship_readiness", {}).get("score", audit.overall_score)
    structure_details = details_map.get("structure", {})
    code_quality_details = details_map.get("code_quality", {})
    testing_score = score_map.get("testing", 0.0)
    candidates: list[dict] = []

    if ship_readiness < 0.55 and not code_quality_details.get("entry_point"):
        target = _first_existing(repo_path, structure_details.get("source_dirs") or []) or _first_existing(repo_path, structure_details.get("config_files") or []) or "."
        candidates.append(
            _build_hotspot(
                scope="module",
                path=target,
                module=_module_name(target),
                category="entry-surface",
                pressure_score=round(min(1.0, 0.52 + (0.55 - ship_readiness)), 3),
                suggestion_type="structure",
                why_it_matters="The repo is missing a clear entry surface, so new contributors have to infer how the project actually starts or runs.",
                suggested_first_move="Define one canonical run path or entry file and reference it in the README and the first test or smoke command.",
                signal_summary="Ship-readiness is weak and no clear entry point was detected.",
            )
        )

    if ship_readiness < 0.55 and testing_score < 0.45:
        target = _first_existing(repo_path, structure_details.get("source_dirs") or []) or "."
        candidates.append(
            _build_hotspot(
                scope="module",
                path=target,
                module=_module_name(target),
                category="test-gap",
                pressure_score=round(min(1.0, 0.48 + (0.45 - testing_score) * 0.8), 3),
                suggestion_type="testing",
                why_it_matters="The repo still needs a reliable first safety net in the core source area before larger cleanup work will feel safe.",
                suggested_first_move="Add one smoke or happy-path test around the main entry flow before tackling larger refactors in this area.",
                signal_summary=f"Testing score is {testing_score:.2f} while ship-readiness is still below a comfortable threshold.",
            )
        )

    return candidates


def _aggregate_module_candidates(candidates: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        module = str(item.get("module") or "root")
        if module == Path(str(item.get("path", ""))).name:
            continue
        grouped[module].append(item)

    aggregated: list[dict] = []
    for module, items in grouped.items():
        if len(items) < 2:
            continue
        categories = Counter(str(item.get("category", "")) for item in items)
        suggestion_types = Counter(str(item.get("suggestion_type", "")) for item in items)
        top_item = max(items, key=lambda item: float(item.get("pressure_score", 0.0)))
        avg_score = sum(float(item.get("pressure_score", 0.0)) for item in items) / len(items)
        aggregated.append(
            _build_hotspot(
                scope="module",
                path=module,
                module=module,
                category=categories.most_common(1)[0][0],
                pressure_score=round(min(1.0, avg_score + min(0.12, len(items) * 0.03)), 3),
                suggestion_type=suggestion_types.most_common(1)[0][0],
                why_it_matters=(
                    f"{module} is accumulating pressure from multiple files, so it is a better cleanup boundary than tackling one symptom in isolation."
                ),
                suggested_first_move=(
                    f"Start with {top_item.get('path', module)} first, then use that cleanup to simplify the rest of the {module} module."
                ),
                signal_summary=f"{len(items)} hotspot signals cluster in this module across {', '.join(list(categories.keys())[:3])}.",
            )
        )
    return aggregated


def _dedupe_hotspots(items: list[dict], *, limit: int) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []
    for item in items:
        key = (str(item.get("scope")), str(item.get("path")), str(item.get("category")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _dimension_scores(audit: RepoAudit) -> dict[str, float]:
    scores = {result.dimension: float(result.score or 0.0) for result in audit.analyzer_results}
    security_score = audit.security_posture.get("score")
    if security_score is not None:
        scores["security"] = float(security_score or 0.0)
    return scores


def _dimension_details(audit: RepoAudit) -> dict[str, dict]:
    return {result.dimension: dict(result.details or {}) for result in audit.analyzer_results}


def _python_complexity_metrics(source: str) -> dict[str, float]:
    try:
        from radon.complexity import cc_visit
    except ImportError:
        return _fallback_python_complexity_metrics(source)

    worst = 0
    complex_blocks = 0
    total = 0
    for block in cc_visit(source):
        total += 1
        worst = max(worst, int(block.complexity))
        if block.complexity >= 10:
            complex_blocks += 1
    pressure = min(1.0, 0.22 + min(worst, 25) * 0.04 + complex_blocks * 0.12 + total * 0.004)
    return {
        "worst_complexity": worst,
        "complex_blocks": complex_blocks,
        "pressure_score": round(pressure, 3),
    }


def _fallback_python_complexity_metrics(source: str) -> dict[str, float]:
    lines = source.splitlines()
    function_boundaries = [index for index, line in enumerate(lines, 1) if line.lstrip().startswith("def ")]
    worst_span = 0
    for idx, start in enumerate(function_boundaries):
        end = function_boundaries[idx + 1] if idx + 1 < len(function_boundaries) else len(lines) + 1
        span = end - start
        worst_span = max(worst_span, span)
    branch_hits = len(BRANCH_KEYWORD_PATTERN.findall(source))
    complex_blocks = max(0, branch_hits // 6)
    worst_complexity = max(1, branch_hits // 2, worst_span // 10)
    pressure = min(1.0, 0.2 + min(worst_complexity, 20) * 0.04 + complex_blocks * 0.12)
    return {
        "worst_complexity": int(worst_complexity),
        "complex_blocks": int(complex_blocks),
        "pressure_score": round(pressure, 3),
    }


def _build_hotspot(
    *,
    scope: str,
    path: str,
    module: str,
    category: str,
    pressure_score: float,
    suggestion_type: str,
    why_it_matters: str,
    suggested_first_move: str,
    signal_summary: str,
) -> dict:
    return {
        "scope": scope,
        "path": path,
        "module": module,
        "category": category,
        "pressure_score": round(float(pressure_score), 3),
        "suggestion_type": suggestion_type,
        "why_it_matters": why_it_matters,
        "suggested_first_move": suggested_first_move,
        "signal_summary": signal_summary,
    }


def _hotspot_display_label(hotspot: dict) -> str:
    scope = hotspot.get("scope", "file")
    path = hotspot.get("path", "the repo root")
    return f"{scope} {path}".strip()


def _module_name(rel_path: str) -> str:
    path = Path(rel_path)
    if path.parent == Path("."):
        if path.name in set(MANIFESTS) | set(LOCKFILES) | set(STRUCTURE_ENTRY_FILES):
            return "root-artifacts"
        return "root"
    return str(path.parent)


def _should_skip(path: Path, repo_path: Path) -> bool:
    try:
        rel_parts = path.relative_to(repo_path).parts
    except ValueError:
        rel_parts = path.parts
    if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
        return True
    try:
        return path.stat().st_size > 1_000_000
    except OSError:
        return True


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _first_existing(repo_path: Path, candidates: list[str]) -> str:
    for item in candidates:
        if (repo_path / item).exists():
            return item
    return candidates[0] if candidates else "."
