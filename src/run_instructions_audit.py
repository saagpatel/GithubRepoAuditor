"""External audit of the snapshot's run_instructions_present claim (pre-step).

Stage 0 (stratified pilot selection) + Stage 1 (evidence prep + live tool_today
recompute) run here as a deterministic, read-only pre-step. The compact JSON this
emits is consumed as `args` by scripts/run-instructions-audit.workflow.js, whose
Haiku subagents read the repo files and judge. Never writes repos/snapshot/git.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from src.portfolio_context_contract import (
    analyze_project_context,
    choose_primary_context_file,
)
from src.portfolio_truth_sources import _collect_context_files

# The six presence claims the snapshot derives per repo, in logical reading order.
# These names match both snapshot `derived.<field>` and ContextAnalysis attributes.
CLAIM_FIELDS = (
    "project_summary_present",
    "current_state_present",
    "stack_present",
    "run_instructions_present",
    "known_risks_present",
    "next_recommended_move_present",
)

FORK_JUNK_PATTERNS = (
    r"-security-fix",
    r"-cve-",
    r"-backup-",
    r"\.bundle$",
    r"-openssl-",
)
DEFAULT_PER_TIER = {
    "none": 3,
    "boilerplate": 4,
    "minimum-viable": 4,
    "standard": 4,
    "full": 4,
}


def is_fork_junk(path: str) -> bool:
    return any(re.search(pattern, path) for pattern in FORK_JUNK_PATTERNS)


def assign_bucket(tool_today: bool, verdict: bool, evidence_in_primary: bool) -> str:
    if tool_today == verdict:
        return "agree_present" if verdict else "agree_absent"
    if verdict and not tool_today:
        return "fn_alias_gap" if evidence_in_primary else "fn_blind_spot"
    return "fp_overclaim"


def assign_drift_bucket(
    snapshot_claim: bool, tool_today: bool, repo_drifted: bool
) -> str:
    if snapshot_claim == tool_today:
        return "claim_same"
    return "claim_changed_drift" if repo_drifted else "claim_changed_nodrift"


def select_pilot(
    projects: list[dict], *, per_tier: dict[str, int] = DEFAULT_PER_TIER
) -> list[dict]:
    eligible = [
        p
        for p in projects
        if not p["derived"]["archived"] and not is_fork_junk(p["identity"]["path"])
    ]
    selected: list[dict] = []
    for tier, count in per_tier.items():
        tier_projects = sorted(
            (p for p in eligible if p["derived"]["context_quality"] == tier),
            key=lambda p: p["identity"]["project_key"],
        )
        selected.extend(tier_projects[:count])
    return selected


def build_record(project: dict, workspace_root: str) -> dict:
    path = project["identity"]["path"]
    derived = project["derived"]
    context_files = derived["context_files"]
    return {
        "project_key": project["identity"]["project_key"],
        "display_name": project["identity"]["display_name"],
        "abs_path": str(Path(workspace_root) / path),
        "primary_file_name": choose_primary_context_file(context_files),
        "context_files": context_files,
        "snapshot_claims": {
            field: bool(derived.get(field, False)) for field in CLAIM_FIELDS
        },
    }


def compute_tool_today(abs_path: str) -> dict:
    project_path = Path(abs_path)
    analysis = analyze_project_context(
        project_path, _collect_context_files(project_path)
    )
    return {field: bool(getattr(analysis, field)) for field in CLAIM_FIELDS}


def is_after(commit_iso: str, generated_at_iso: str) -> bool:
    return datetime.fromisoformat(commit_iso) > datetime.fromisoformat(generated_at_iso)


def compute_drifted(abs_path: str, generated_at: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", abs_path, "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    commit_iso = result.stdout.strip()
    if result.returncode != 0 or not commit_iso:
        return False
    return is_after(commit_iso, generated_at)


def prepare_pilot(
    snapshot_path: str, *, per_tier: dict[str, int] = DEFAULT_PER_TIER
) -> dict:
    snapshot = json.loads(Path(snapshot_path).read_text())
    workspace_root = snapshot["workspace_root"]
    generated_at = snapshot["generated_at"]
    records: list[dict] = []
    errors: list[dict] = []
    for project in select_pilot(snapshot["projects"], per_tier=per_tier):
        record = build_record(project, workspace_root)
        if not Path(record["abs_path"]).is_dir():
            errors.append(
                {
                    "project_key": record["project_key"],
                    "abs_path": record["abs_path"],
                    "error": "missing_dir",
                }
            )
            continue
        record["tool_today"] = compute_tool_today(record["abs_path"])
        record["drifted"] = compute_drifted(record["abs_path"], generated_at)
        records.append(record)
    return {
        "generated_at": generated_at,
        "workspace_root": workspace_root,
        "records": records,
        "errors": errors,
    }


def main() -> None:
    import sys

    snapshot_path = (
        sys.argv[1] if len(sys.argv) > 1 else "output/portfolio-truth-latest.json"
    )
    print(json.dumps(prepare_pilot(snapshot_path), indent=2))


if __name__ == "__main__":
    main()
