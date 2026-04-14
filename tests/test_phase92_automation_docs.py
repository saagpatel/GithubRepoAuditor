from __future__ import annotations

from pathlib import Path


def test_docs_reflect_bounded_automation_guidance_language() -> None:
    architecture = Path("docs/architecture.md").read_text()
    modes = Path("docs/modes.md").read_text()
    weekly = Path("docs/weekly-review.md").read_text()
    safety = Path("docs/writeback-safety-model.md").read_text()
    troubleshooting = Path("docs/operator-troubleshooting.md").read_text()
    roadmap = Path("docs/plans/2026-04-12-roadmap-phases-88-92.md").read_text()

    combined = "\n".join([architecture, modes, weekly, safety, troubleshooting, roadmap])

    assert "Automation Guidance" in combined
    assert "preview-safe" in combined
    assert "apply-manual" in combined
    assert "approval-first" in combined
    assert "follow-up-safe" in combined
    assert "quiet-safe" in combined
    assert "it never auto-runs `--writeback-apply`" in combined
