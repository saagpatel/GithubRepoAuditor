from __future__ import annotations

import json
from pathlib import Path

from src.excel_export_truth_helpers import load_risk_truth


def test_load_risk_truth_keys_by_slug_and_display_name(tmp_path: Path) -> None:
    truth = {
        "projects": [
            {
                "identity": {
                    "display_name": "Signal & Noise",
                    "repo_full_name": "saagpatel/signal-noise",
                },
                "risk": {"risk_tier": "elevated"},
            }
        ]
    }
    (tmp_path / "portfolio-truth-latest.json").write_text(json.dumps(truth))
    risk_lookup, posture = load_risk_truth(tmp_path)
    # Findable by both the local-dir display name and the GitHub slug.
    assert risk_lookup["Signal & Noise"] == "elevated"
    assert risk_lookup["signal-noise"] == "elevated"
    # The slug alias must NOT double-count the aggregate posture.
    assert posture["elevated"] == 1


def test_load_risk_truth_no_slug_when_repo_full_name_absent(tmp_path: Path) -> None:
    truth = {
        "projects": [{"identity": {"display_name": "PlainRepo"}, "risk": {"risk_tier": "moderate"}}]
    }
    (tmp_path / "portfolio-truth-latest.json").write_text(json.dumps(truth))
    risk_lookup, posture = load_risk_truth(tmp_path)
    assert risk_lookup == {"PlainRepo": "moderate"}
    assert posture["moderate"] == 1
