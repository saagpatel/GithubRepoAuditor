from __future__ import annotations

from pathlib import Path


def test_docs_reflect_phase_93_approval_workflow_language() -> None:
    combined = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/architecture.md").read_text(),
            Path("docs/modes.md").read_text(),
            Path("docs/weekly-review.md").read_text(),
            Path("docs/writeback-safety-model.md").read_text(),
            Path("docs/operator-troubleshooting.md").read_text(),
            Path("docs/plans/2026-04-13-roadmap-phases-93-97.md").read_text(),
        ]
    )

    assert "Approval Workflow" in combined
    assert "Next Approval Review" in combined
    assert "Approved But Manual" in combined
    assert "--approval-center" in combined
    assert "--approve-governance" in combined
    assert "--approve-packet" in combined
    assert "it never auto-runs `--writeback-apply`" in combined or "it never auto-runs `--writeback-apply`" in combined.replace("—", "-")
