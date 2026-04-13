from __future__ import annotations

from pathlib import Path


def test_docs_reflect_phase_90_canonical_action_sync_language() -> None:
    architecture = Path("docs/architecture.md").read_text()
    modes = Path("docs/modes.md").read_text()
    weekly = Path("docs/weekly-review.md").read_text()
    safety = Path("docs/writeback-safety-model.md").read_text()

    combined = "\n".join([architecture, modes, weekly, safety])

    assert "Action Sync Readiness" in combined
    assert "Apply Packet" in combined
    assert "Post-Apply Monitoring" in combined
    assert "Campaign Tuning" in combined
    assert "Next Tie-Break Candidate" in combined
    assert "Campaign Tuning Overlay" not in combined
    assert "Next Tuned Campaign" not in combined


def test_architecture_describes_three_action_sync_layers_plus_tuning() -> None:
    architecture = Path("docs/architecture.md").read_text()

    assert "Action Sync now has three operational layers plus one bounded recommendation overlay." in architecture
    assert "### 1. `Action Sync Readiness`" in architecture
    assert "### 2. `Apply Packet`" in architecture
    assert "### 3. `Post-Apply Monitoring`" in architecture
    assert "bounded recommendation overlay: `Campaign Tuning`" in architecture
