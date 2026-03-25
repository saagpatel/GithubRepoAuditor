from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditDiff:
    """Diff between two audit runs."""

    previous_date: str
    current_date: str
    new_repos: list[str]
    removed_repos: list[str]
    tier_changes: list[dict]  # {name, old_tier, new_tier, old_score, new_score}
    score_changes: list[dict]  # {name, old_score, new_score, delta}
    average_score_delta: float
    tier_distribution_delta: dict[str, int]  # tier -> count change

    def to_dict(self) -> dict:
        return {
            "previous_date": self.previous_date,
            "current_date": self.current_date,
            "new_repos": self.new_repos,
            "removed_repos": self.removed_repos,
            "tier_changes": self.tier_changes,
            "score_improvements": [c for c in self.score_changes if c["delta"] > 0.05],
            "score_regressions": [c for c in self.score_changes if c["delta"] < -0.05],
            "average_score_delta": round(self.average_score_delta, 3),
            "tier_distribution_delta": self.tier_distribution_delta,
        }


def diff_reports(previous_path: Path, current_path: Path) -> AuditDiff:
    """Compare two audit-report JSON files and produce a diff."""
    prev = json.loads(previous_path.read_text())
    curr = json.loads(current_path.read_text())

    prev_map = {a["metadata"]["name"]: a for a in prev["audits"]}
    curr_map = {a["metadata"]["name"]: a for a in curr["audits"]}

    prev_names = set(prev_map.keys())
    curr_names = set(curr_map.keys())

    new_repos = sorted(curr_names - prev_names)
    removed_repos = sorted(prev_names - curr_names)

    # Score and tier changes for repos in both
    tier_changes: list[dict] = []
    score_changes: list[dict] = []

    for name in sorted(prev_names & curr_names):
        old = prev_map[name]
        new = curr_map[name]
        old_score = old["overall_score"]
        new_score = new["overall_score"]
        old_tier = old["completeness_tier"]
        new_tier = new["completeness_tier"]

        delta = new_score - old_score
        score_changes.append({
            "name": name,
            "old_score": round(old_score, 3),
            "new_score": round(new_score, 3),
            "delta": round(delta, 3),
        })

        if old_tier != new_tier:
            tier_changes.append({
                "name": name,
                "old_tier": old_tier,
                "new_tier": new_tier,
                "old_score": round(old_score, 3),
                "new_score": round(new_score, 3),
            })

    # Sort score changes by absolute delta descending
    score_changes.sort(key=lambda c: abs(c["delta"]), reverse=True)

    # Average score delta
    avg_delta = curr.get("average_score", 0) - prev.get("average_score", 0)

    # Tier distribution delta
    prev_tiers = prev.get("tier_distribution", {})
    curr_tiers = curr.get("tier_distribution", {})
    all_tiers = set(prev_tiers.keys()) | set(curr_tiers.keys())
    tier_dist_delta = {
        t: curr_tiers.get(t, 0) - prev_tiers.get(t, 0)
        for t in sorted(all_tiers)
        if curr_tiers.get(t, 0) != prev_tiers.get(t, 0)
    }

    return AuditDiff(
        previous_date=prev.get("generated_at", "unknown"),
        current_date=curr.get("generated_at", "unknown"),
        new_repos=new_repos,
        removed_repos=removed_repos,
        tier_changes=tier_changes,
        score_changes=score_changes,
        average_score_delta=avg_delta,
        tier_distribution_delta=tier_dist_delta,
    )


def format_diff_markdown(diff: AuditDiff) -> str:
    """Format an AuditDiff as readable Markdown."""
    lines: list[str] = []
    _w = lines.append

    _w("# Audit Diff Report")
    _w("")
    _w(f"**Previous:** {diff.previous_date}  ")
    _w(f"**Current:** {diff.current_date}")
    _w("")
    _w(f"**Average score change:** {diff.average_score_delta:+.3f}")
    _w("")

    if diff.tier_distribution_delta:
        _w("## Tier Changes (Distribution)")
        _w("")
        _w("| Tier | Change |")
        _w("|------|--------|")
        for tier, delta in diff.tier_distribution_delta.items():
            _w(f"| {tier} | {delta:+d} |")
        _w("")

    if diff.new_repos:
        _w(f"## New Repos ({len(diff.new_repos)})")
        _w("")
        for name in diff.new_repos:
            _w(f"- {name}")
        _w("")

    if diff.removed_repos:
        _w(f"## Removed Repos ({len(diff.removed_repos)})")
        _w("")
        for name in diff.removed_repos:
            _w(f"- {name}")
        _w("")

    if diff.tier_changes:
        _w(f"## Tier Transitions ({len(diff.tier_changes)})")
        _w("")
        _w("| Repo | Old Tier | New Tier | Old Score | New Score |")
        _w("|------|----------|----------|-----------|-----------|")
        for c in diff.tier_changes:
            _w(f"| {c['name']} | {c['old_tier']} | {c['new_tier']} | "
               f"{c['old_score']:.2f} | {c['new_score']:.2f} |")
        _w("")

    improvements = [c for c in diff.score_changes if c["delta"] > 0.05]
    regressions = [c for c in diff.score_changes if c["delta"] < -0.05]

    if improvements:
        _w(f"## Improved ({len(improvements)})")
        _w("")
        _w("| Repo | Old | New | Delta |")
        _w("|------|-----|-----|-------|")
        for c in improvements[:20]:
            _w(f"| {c['name']} | {c['old_score']:.2f} | {c['new_score']:.2f} | {c['delta']:+.3f} |")
        _w("")

    if regressions:
        _w(f"## Regressed ({len(regressions)})")
        _w("")
        _w("| Repo | Old | New | Delta |")
        _w("|------|-----|-----|-------|")
        for c in regressions[:20]:
            _w(f"| {c['name']} | {c['old_score']:.2f} | {c['new_score']:.2f} | {c['delta']:+.3f} |")
        _w("")

    return "\n".join(lines)
