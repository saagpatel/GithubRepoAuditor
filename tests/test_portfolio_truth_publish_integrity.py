from __future__ import annotations

from pathlib import Path

import pytest

import src.portfolio_truth_publish as publish_mod


@pytest.mark.parametrize("replaced_count", [1, 2, 3, 4, 5])
def test_publish_journal_recovers_process_death_after_each_replacement(
    tmp_path: Path, replaced_count: int
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    snapshot = output_dir / "portfolio-truth-2026-07-17T120000Z.json"
    latest = output_dir / "portfolio-truth-latest.json"
    registry = tmp_path / "project-registry.md"
    report = tmp_path / "PORTFOLIO-AUDIT-REPORT.md"
    project_registry = output_dir / "project-registry.json"
    targets = [snapshot, latest, registry, report, project_registry]
    prior = {
        snapshot: None,
        latest: "old latest\n",
        registry: "old registry\n",
        report: "old report\n",
        project_registry: "old project registry\n",
    }
    for path, content in prior.items():
        if content is not None:
            path.write_text(content, encoding="utf-8")

    staged = {
        path: publish_mod._stage_text(path, f"new generation {index}\n")
        for index, path in enumerate(targets)
    }
    backups = {
        path: (
            publish_mod._stage_bytes(path, path.read_bytes())
            if path.exists()
            else None
        )
        for path in targets
    }
    journal = output_dir / publish_mod._PUBLISH_JOURNAL_NAME
    publish_mod._write_publish_journal(
        journal, temp_files=staged, backups=backups
    )
    for path in targets[:replaced_count]:
        staged[path].replace(path)

    publish_mod._recover_interrupted_publication(
        output_dir,
        allowed_targets={latest, registry, report, project_registry},
    )

    for path, content in prior.items():
        if content is None:
            assert not path.exists()
        else:
            assert path.read_text(encoding="utf-8") == content
    assert not journal.exists()
    assert not any(path.exists() for path in staged.values())
    assert not any(path is not None and path.exists() for path in backups.values())


def test_publish_cleanup_retires_journal_before_deleting_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / publish_mod._PUBLISH_JOURNAL_NAME
    staged = tmp_path / "staged.tmp"
    backup = tmp_path / "target.bak"
    for path in (journal, staged, backup):
        path.write_text("data", encoding="utf-8")

    removed: list[Path] = []
    original_unlink = Path.unlink

    def recording_unlink(path: Path, *args, **kwargs) -> None:
        removed.append(path)
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", recording_unlink)

    publish_mod._cleanup_publish_transaction(journal, [staged], [backup])

    assert removed == [journal, staged, backup]
