from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.analyst_views import (
    build_profile_leaderboard,
    collection_membership_map,
    summarize_scenario_preview,
)


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
    repo_changes: list[dict] = field(default_factory=list)
    lens_deltas: dict[str, float] = field(default_factory=dict)
    profile_leaderboards: dict = field(default_factory=dict)
    hotspot_changes: list[dict] = field(default_factory=list)
    security_changes: list[dict] = field(default_factory=list)
    collection_changes: list[dict] = field(default_factory=list)
    scenario_preview: dict = field(default_factory=dict)
    profile_name: str = "default"
    collection_name: str | None = None

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
            "repo_changes": self.repo_changes,
            "lens_deltas": self.lens_deltas,
            "profile_leaderboards": self.profile_leaderboards,
            "hotspot_changes": self.hotspot_changes,
            "security_changes": self.security_changes,
            "collection_changes": self.collection_changes,
            "scenario_preview": self.scenario_preview,
            "compare_summary": {
                "profile_name": self.profile_name,
                "collection_name": self.collection_name,
                "lens_deltas": self.lens_deltas,
                "profile_leaderboards": self.profile_leaderboards,
                "scenario_preview": self.scenario_preview,
            },
        }


def diff_reports(
    previous_path: Path,
    current_path: Path,
    *,
    portfolio_profile: str = "default",
    collection_name: str | None = None,
) -> AuditDiff:
    """Compare two audit-report JSON files and produce a diff."""
    prev = json.loads(previous_path.read_text())
    curr = json.loads(current_path.read_text())

    prev_map = {a["metadata"]["name"]: a for a in prev["audits"]}
    curr_map = {a["metadata"]["name"]: a for a in curr["audits"]}
    prev_collections = collection_membership_map(prev)
    curr_collections = collection_membership_map(curr)

    prev_names = set(prev_map.keys())
    curr_names = set(curr_map.keys())

    new_repos = sorted(curr_names - prev_names)
    removed_repos = sorted(prev_names - curr_names)

    # Score and tier changes for repos in both
    tier_changes: list[dict] = []
    score_changes: list[dict] = []
    repo_changes: list[dict] = []
    hotspot_changes: list[dict] = []
    security_changes: list[dict] = []
    collection_changes: list[dict] = []

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

        old_lenses = old.get("lenses", {})
        new_lenses = new.get("lenses", {})
        all_lenses = sorted(set(old_lenses.keys()) | set(new_lenses.keys()))
        lens_delta_map = {
            lens_name: round(
                new_lenses.get(lens_name, {}).get("score", 0.0)
                - old_lenses.get(lens_name, {}).get("score", 0.0),
                3,
            )
            for lens_name in all_lenses
        }

        old_security = old.get("security_posture", {})
        new_security = new.get("security_posture", {})
        security_change = {
            "name": name,
            "old_label": old_security.get("label", "unknown"),
            "new_label": new_security.get("label", "unknown"),
            "old_score": round(old_security.get("score", 0.0), 3),
            "new_score": round(new_security.get("score", 0.0), 3),
            "delta": round(new_security.get("score", 0.0) - old_security.get("score", 0.0), 3),
        }
        if (
            security_change["old_label"] != security_change["new_label"]
            or abs(security_change["delta"]) >= 0.01
        ):
            security_changes.append(security_change)

        old_hotspots = old.get("hotspots", [])
        new_hotspots = new.get("hotspots", [])
        hotspot_change = {
            "name": name,
            "old_count": len(old_hotspots),
            "new_count": len(new_hotspots),
            "old_primary": old_hotspots[0].get("title", "") if old_hotspots else "",
            "new_primary": new_hotspots[0].get("title", "") if new_hotspots else "",
        }
        if hotspot_change["old_count"] != hotspot_change["new_count"] or hotspot_change["old_primary"] != hotspot_change["new_primary"]:
            hotspot_changes.append(hotspot_change)

        old_memberships = sorted(prev_collections.get(name, []))
        new_memberships = sorted(curr_collections.get(name, []))
        collection_change = {
            "name": name,
            "old": old_memberships,
            "new": new_memberships,
        }
        if collection_change["old"] != collection_change["new"]:
            collection_changes.append(collection_change)

        repo_changes.append({
            "name": name,
            "old_score": round(old_score, 3),
            "new_score": round(new_score, 3),
            "delta": round(delta, 3),
            "old_tier": old_tier,
            "new_tier": new_tier,
            "lens_deltas": lens_delta_map,
            "security_change": security_change,
            "hotspot_change": hotspot_change,
            "collection_change": collection_change,
        })

    # Sort score changes by absolute delta descending
    score_changes.sort(key=lambda c: abs(c["delta"]), reverse=True)
    repo_changes.sort(key=lambda c: abs(c["delta"]), reverse=True)

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

    prev_lenses = prev.get("lenses", {})
    curr_lenses = curr.get("lenses", {})
    all_lens_names = sorted(set(prev_lenses.keys()) | set(curr_lenses.keys()))
    lens_deltas = {
        lens_name: round(
            curr_lenses.get(lens_name, {}).get("average_score", 0.0)
            - prev_lenses.get(lens_name, {}).get("average_score", 0.0),
            3,
        )
        for lens_name in all_lens_names
        if round(
            curr_lenses.get(lens_name, {}).get("average_score", 0.0)
            - prev_lenses.get(lens_name, {}).get("average_score", 0.0),
            3,
        ) != 0
    }

    prev_board = build_profile_leaderboard(prev, portfolio_profile, collection_name)
    curr_board = build_profile_leaderboard(curr, portfolio_profile, collection_name)
    prev_names_ranked = {entry["name"] for entry in prev_board.get("leaders", [])}
    curr_names_ranked = {entry["name"] for entry in curr_board.get("leaders", [])}
    profile_leaderboards = {
        curr_board.get("profile_name", portfolio_profile): {
            "current": curr_board.get("leaders", []),
            "previous": prev_board.get("leaders", []),
            "entered": sorted(curr_names_ranked - prev_names_ranked),
            "exited": sorted(prev_names_ranked - curr_names_ranked),
            "collection_name": collection_name,
        }
    }

    scenario_preview = summarize_scenario_preview(curr, portfolio_profile, collection_name)

    return AuditDiff(
        previous_date=prev.get("generated_at", "unknown"),
        current_date=curr.get("generated_at", "unknown"),
        new_repos=new_repos,
        removed_repos=removed_repos,
        tier_changes=tier_changes,
        score_changes=score_changes,
        average_score_delta=avg_delta,
        tier_distribution_delta=tier_dist_delta,
        repo_changes=repo_changes,
        lens_deltas=lens_deltas,
        profile_leaderboards=profile_leaderboards,
        hotspot_changes=hotspot_changes,
        security_changes=security_changes,
        collection_changes=collection_changes,
        scenario_preview=scenario_preview,
        profile_name=portfolio_profile,
        collection_name=collection_name,
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

    if diff.lens_deltas:
        _w("## Lens Deltas")
        _w("")
        _w("| Lens | Delta |")
        _w("|------|-------|")
        for lens_name, delta in diff.lens_deltas.items():
            _w(f"| {lens_name} | {delta:+.3f} |")
        _w("")

    if diff.security_changes:
        _w("## Security Changes")
        _w("")
        _w("| Repo | Old Label | New Label | Delta |")
        _w("|------|-----------|-----------|-------|")
        for change in diff.security_changes[:10]:
            _w(f"| {change['name']} | {change['old_label']} | {change['new_label']} | {change['delta']:+.3f} |")
        _w("")

    if diff.profile_leaderboards:
        leaderboard = next(iter(diff.profile_leaderboards.values()))
        _w(f"## Profile Leaders ({diff.profile_name})")
        _w("")
        for entry in leaderboard.get("current", []):
            _w(f"- {entry['name']} — {entry['profile_score']:.3f}")
        _w("")

    preview = diff.scenario_preview.get("portfolio_projection", {})
    if preview:
        _w("## Scenario Preview")
        _w("")
        _w(f"- Selected repos: {preview.get('selected_repo_count', 0)}")
        _w(f"- Projected average score delta: {preview.get('projected_average_score_delta', 0):+.3f}")
        _w(f"- Projected tier promotions: {preview.get('projected_tier_promotions', 0)}")
        _w("")

    return "\n".join(lines)


def print_diff_summary(diff: AuditDiff) -> None:
    """Print colored diff summary to stderr using Rich."""
    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)

    # Score delta
    delta = diff.average_score_delta
    color = "green" if delta >= 0 else "red"
    sign = "+" if delta >= 0 else ""
    console.print(f"\n[bold]Portfolio Score Delta:[/bold] [{color}]{sign}{delta:.3f}[/{color}]")

    # Tier changes
    if diff.tier_changes:
        table = Table(title="Tier Changes", show_lines=False)
        table.add_column("Repo")
        table.add_column("Old Tier")
        table.add_column("New Tier")
        table.add_column("Direction")
        for tc in diff.tier_changes[:10]:
            old = tc.get("old_tier", "")
            new = tc.get("new_tier", "")
            direction = "[green]↑ Promoted[/green]" if tc.get("promoted") else "[red]↓ Demoted[/red]"
            table.add_row(tc.get("name", ""), old, new, direction)
        console.print(table)

    # Top movers
    improvements = [s for s in diff.score_changes if s.get("delta", 0) > 0][:5]
    regressions = [s for s in diff.score_changes if s.get("delta", 0) < 0][:5]

    if improvements:
        console.print("\n[bold green]Top Improvements:[/bold green]")
        for s in improvements:
            console.print(f"  [green]↑ {s['name']}: +{s['delta']:.3f}[/green]")

    if regressions:
        console.print("\n[bold red]Top Regressions:[/bold red]")
        for s in regressions:
            console.print(f"  [red]↓ {s['name']}: {s['delta']:.3f}[/red]")

    # Summary counts
    console.print(f"\n[dim]New repos: {len(diff.new_repos)} | Removed: {len(diff.removed_repos)}[/dim]")
