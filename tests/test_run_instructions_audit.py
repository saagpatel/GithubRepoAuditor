import json
import os
import subprocess

from src.run_instructions_audit import (
    CLAIM_FIELDS,
    assign_bucket,
    assign_drift_bucket,
    build_record,
    compute_drifted,
    compute_tool_today,
    is_after,
    is_fork_junk,
    prepare_pilot,
    select_pilot,
)


def test_is_fork_junk_flags_known_patterns():
    assert is_fork_junk("AssistSupport-openssl-cve-2026-42327")
    assert is_fork_junk("BrowserHistoryVisualizer-security-fix")
    assert is_fork_junk("ApplyKit-private-history-backup-20260517.bundle")
    assert not is_fork_junk("Fun:GamePrjs/BattleGrid")
    assert not is_fork_junk("mcpforge")


def test_assign_bucket_truth_table():
    # agreement
    assert assign_bucket(True, True, True) == "agree_present"
    assert assign_bucket(False, False, False) == "agree_absent"
    # false negatives (tool said absent, verifier found it)
    assert assign_bucket(False, True, True) == "fn_alias_gap"  # evidence in primary file
    assert assign_bucket(False, True, False) == "fn_blind_spot"  # evidence only in README/other
    # false positive (tool over-claimed)
    assert assign_bucket(True, False, False) == "fp_overclaim"
    assert assign_bucket(True, False, True) == "fp_overclaim"


def test_assign_drift_bucket():
    # snapshot still matches today's recompute → no field drift
    assert assign_drift_bucket(True, True, True) == "claim_same"
    assert assign_drift_bucket(False, False, False) == "claim_same"
    # field value changed AND repo has commits since snapshot → explained by drift
    assert assign_drift_bucket(False, True, True) == "claim_changed_drift"
    # field value changed with NO commits since snapshot → unexplained (snapshot was wrong)
    assert assign_drift_bucket(False, True, False) == "claim_changed_nodrift"


def _project(key, quality, *, status="active", path=None):
    return {
        "identity": {"project_key": key, "path": path or key, "display_name": key.split("/")[-1]},
        "derived": {
            "registry_status": status,
            "context_quality": quality,
            "context_files": ["CLAUDE.md"],
            "run_instructions_present": False,
        },
    }


def test_select_pilot_stratifies_sorts_and_filters():
    projects = (
        [_project(f"b{i}", "boilerplate") for i in range(6)]
        + [_project("n1", "none"), _project("n2", "none")]
        + [_project("arch", "full", status="archived")]
        + [_project("junk-security-fix", "full")]
        + [_project("z-full", "full"), _project("a-full", "full")]
    )
    selected = select_pilot(projects, per_tier={"none": 3, "boilerplate": 4, "full": 4})
    keys = [p["identity"]["project_key"] for p in selected]

    # archived + fork-junk excluded
    assert "arch" not in keys and "junk-security-fix" not in keys
    # boilerplate capped at 4 of 6
    assert sum(k.startswith("b") for k in keys) == 4
    # full sorted by project_key → a-full before z-full
    assert keys.index("a-full") < keys.index("z-full")
    # both 'none' present (only 2 available, asked for 3)
    assert {"n1", "n2"} <= set(keys)


def test_build_record_resolves_path_and_all_six_claims():
    project = {
        "identity": {
            "project_key": "Fun:GamePrjs/BattleGrid",
            "path": "Fun:GamePrjs/BattleGrid",
            "display_name": "BattleGrid",
        },
        "derived": {
            "context_files": ["AGENTS.md", "README.md"],
            "run_instructions_present": False,
            "project_summary_present": True,  # one set True to prove per-field mapping
        },
    }
    record = build_record(project, "/Users/d/Projects")

    assert record["abs_path"] == "/Users/d/Projects/Fun:GamePrjs/BattleGrid"
    assert record["primary_file_name"] == "AGENTS.md"  # no CLAUDE.md → AGENTS.md
    assert record["context_files"] == ["AGENTS.md", "README.md"]
    assert record["project_key"] == "Fun:GamePrjs/BattleGrid"
    # snapshot_claims is now a dict over all 6 fields; missing derived fields default False
    assert set(record["snapshot_claims"]) == set(CLAIM_FIELDS)
    assert record["snapshot_claims"]["run_instructions_present"] is False
    assert record["snapshot_claims"]["project_summary_present"] is True
    assert record["snapshot_claims"]["known_risks_present"] is False  # absent in derived → False


def test_build_record_prefers_claude_md():
    project = {
        "identity": {"project_key": "x", "path": "x", "display_name": "x"},
        "derived": {"context_files": ["AGENTS.md", "CLAUDE.md"], "run_instructions_present": True},
    }
    assert build_record(project, "/w")["primary_file_name"] == "CLAUDE.md"


def test_is_after_compares_tz_aware_iso():
    assert is_after("2026-05-25T19:25:00-07:00", "2026-05-17T05:01:39+00:00")
    assert not is_after("2026-05-10T00:00:00+00:00", "2026-05-17T05:01:39+00:00")


def test_compute_tool_today_returns_all_six_claims_true_when_alias_matches(tmp_path):
    # "## Usage" IS a run_instructions alias → run_instructions_present True
    (tmp_path / "CLAUDE.md").write_text(
        "# Proj\n\n## Usage\n\nRun the dev server with `npm run dev`. It serves on :3000.\n"
    )
    result = compute_tool_today(str(tmp_path))
    assert set(result) == set(CLAIM_FIELDS)  # dict over all 6 claims
    assert result["run_instructions_present"] is True
    assert result["known_risks_present"] is False  # not documented → False


def test_compute_tool_today_false_when_run_heading_outside_alias(tmp_path):
    # "## Running" is NOT in the alias list → the tool misses it (alias-gap case)
    (tmp_path / "CLAUDE.md").write_text(
        "# Proj\n\n## Running\n\nStart it with `npm run dev`. This is genuine run guidance.\n"
    )
    assert compute_tool_today(str(tmp_path))["run_instructions_present"] is False


def _git_commit_at(path, iso):
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": iso,
        "GIT_COMMITTER_DATE": iso,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, env=env, check=True
    )


def test_compute_drifted_true_when_commit_after_snapshot(tmp_path):
    _git_commit_at(tmp_path, "2026-05-25T00:00:00+00:00")
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is True


def test_compute_drifted_false_when_commit_before_snapshot(tmp_path):
    _git_commit_at(tmp_path, "2026-05-01T00:00:00+00:00")
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is False


def test_compute_drifted_false_for_non_git_dir(tmp_path):
    assert compute_drifted(str(tmp_path), "2026-05-17T05:01:39+00:00") is False


def test_prepare_pilot_builds_records_and_reports_missing_dirs(tmp_path):
    workspace = tmp_path / "ws"
    real = workspace / "RealRepo"
    real.mkdir(parents=True)
    (real / "CLAUDE.md").write_text("# R\n\n## Usage\n\nRun `npm run dev` to start the server.\n")

    snapshot = {
        "workspace_root": str(workspace),
        "generated_at": "2026-05-17T05:01:39+00:00",
        "projects": [
            {
                "identity": {
                    "project_key": "RealRepo",
                    "path": "RealRepo",
                    "display_name": "RealRepo",
                },
                "derived": {
                    "registry_status": "active",
                    "context_quality": "full",
                    "context_files": ["CLAUDE.md"],
                    "run_instructions_present": True,
                },
            },
            {
                "identity": {
                    "project_key": "GhostRepo",
                    "path": "GhostRepo",
                    "display_name": "GhostRepo",
                },
                "derived": {
                    "registry_status": "active",
                    "context_quality": "full",
                    "context_files": ["CLAUDE.md"],
                    "run_instructions_present": False,
                },
            },
        ],
    }
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snapshot))

    result = prepare_pilot(str(snap_path), per_tier={"full": 4})

    assert result["workspace_root"] == str(workspace)
    assert len(result["records"]) == 1
    assert len(result["errors"]) == 1
    record = result["records"][0]
    assert record["project_key"] == "RealRepo"
    # tool_today + snapshot_claims are now dicts over all 6 claims
    assert record["tool_today"]["run_instructions_present"] is True  # live recompute on fixture
    assert record["snapshot_claims"]["run_instructions_present"] is True
    assert set(record["tool_today"]) == set(CLAIM_FIELDS)
    assert record["drifted"] is False  # no git repo → not drifted
    assert result["errors"][0]["error"] == "missing_dir"
    assert result["errors"][0]["project_key"] == "GhostRepo"
