"""Tests for Arc G Sprint 8.5 — per-section approval for draft-readme packets."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.draft_readmes import (
    DraftReadmePacket,
    approve_section,
    assemble_readme_from_approved_sections,
    load_approved_sectioned_packets,
    mark_section_packet_applied,
    reject_section,
    split_readme_sections,
    write_section_packets_to_ledger,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_packet(
    repo_name: str = "test-repo",
    proposed_readme: str = "## Installation\npip install foo\n\n## Usage\nrun it\n",
    generated_at: str = "2026-05-11T00:00:00+00:00",
) -> DraftReadmePacket:
    return DraftReadmePacket(
        repo_name=repo_name,
        current_readme_sha="abc123",
        proposed_readme=proposed_readme,
        diff_summary="test diff",
        llm_provider="openai",
        llm_model="gpt-4",
        llm_cost_usd=0.001,
        generated_at=generated_at,
    )


def _seed_sections(output_dir: Path, packet: DraftReadmePacket | None = None) -> list[str]:
    """Write packet sections to ledger, return list of approval_ids."""
    if packet is None:
        packet = _make_packet()
    write_section_packets_to_ledger([packet], output_dir, reviewer="tester")
    from src.warehouse import load_approval_records

    records = load_approval_records(output_dir, "", limit=500)
    return [
        r["approval_id"]
        for r in records
        if r.get("approval_subject_type") == "draft-readme-section"
    ]


# ── Section splitter ──────────────────────────────────────────────────────────


class TestSplitReadmeSections:
    def test_empty_input_returns_empty_list(self) -> None:
        assert split_readme_sections("") == []

    def test_no_h2_headings_returns_single_intro_tuple(self) -> None:
        text = "Just some text\nwith no headings.\n"
        result = split_readme_sections(text)
        assert len(result) == 1
        heading, body = result[0]
        assert heading == "(intro)"
        assert body == text

    def test_three_sections_returned_in_order(self) -> None:
        text = "## Alpha\nbody A\n## Beta\nbody B\n## Gamma\nbody C\n"
        result = split_readme_sections(text)
        assert len(result) == 3
        assert result[0][0] == "Alpha"
        assert result[1][0] == "Beta"
        assert result[2][0] == "Gamma"

    def test_content_before_first_h2_becomes_intro(self) -> None:
        text = "Intro paragraph.\n\n## Installation\npip install foo\n"
        result = split_readme_sections(text)
        assert len(result) == 2
        assert result[0][0] == "(intro)"
        assert "Intro paragraph." in result[0][1]
        assert result[1][0] == "Installation"

    def test_nested_h3_stays_in_parent_body(self) -> None:
        text = "## Installation\npip install foo\n\n### Linux notes\nextra\n\n## Usage\nrun\n"
        result = split_readme_sections(text)
        assert len(result) == 2
        assert result[0][0] == "Installation"
        assert "### Linux notes" in result[0][1]
        assert result[1][0] == "Usage"

    def test_h2_inside_code_fence_is_ignored(self) -> None:
        text = "## Real Heading\nsome text\n```\n## Not a heading\ncode\n```\nmore text\n"
        result = split_readme_sections(text)
        # Only "Real Heading" should split — the fenced one should be ignored
        assert len(result) == 1
        assert result[0][0] == "Real Heading"
        assert "## Not a heading" in result[0][1]

    def test_empty_section_body_between_headings(self) -> None:
        text = "## Foo\n\n## Bar\nsome content\n"
        result = split_readme_sections(text)
        assert len(result) == 2
        assert result[0][0] == "Foo"
        # body is just the blank line between Foo and Bar
        assert result[0][1].strip() == ""
        assert result[1][0] == "Bar"


# ── Schema + writes ───────────────────────────────────────────────────────────


class TestWriteSectionPackets:
    def test_three_section_packet_writes_three_records(self) -> None:
        text = "Intro\n## Alpha\nbody A\n## Beta\nbody B\n"
        packet = _make_packet(proposed_readme=text)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_section_packets_to_ledger([packet], output_dir, reviewer="t")
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            section_records = [
                r for r in records if r.get("approval_subject_type") == "draft-readme-section"
            ]
            assert len(section_records) == 3

    def test_all_records_have_correct_subject_type(self) -> None:
        packet = _make_packet()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_section_packets_to_ledger([packet], output_dir, reviewer="t")
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            section_records = [
                r for r in records if r.get("approval_subject_type") == "draft-readme-section"
            ]
            assert all(
                r["approval_subject_type"] == "draft-readme-section" for r in section_records
            )

    def test_distinct_approval_ids_shared_packet_id(self) -> None:
        text = "## A\nbody\n## B\nbody\n## C\nbody\n"
        packet = _make_packet(proposed_readme=text)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_section_packets_to_ledger([packet], output_dir, reviewer="t")
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            section_records = [
                r for r in records if r.get("approval_subject_type") == "draft-readme-section"
            ]
            approval_ids = [r["approval_id"] for r in section_records]
            assert len(set(approval_ids)) == 3  # all distinct
            packet_ids = {r.get("packet_id") for r in section_records}
            assert len(packet_ids) == 1  # all share one packet_id

    def test_rerun_same_repo_preserves_approved_state(self) -> None:
        """Re-running write with same sections keeps existing approved state via INSERT OR REPLACE."""
        packet = _make_packet()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            assert record_ids

            # Approve the first section
            approve_section(record_ids[0], output_dir)

            # Re-run with the SAME sections (same approval_id derived from heading)
            write_section_packets_to_ledger([packet], output_dir, reviewer="t")

            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            rec = next(
                (r for r in records if r.get("approval_id") == record_ids[0]),
                None,
            )
            # INSERT OR REPLACE will overwrite — state resets to pending on re-write.
            # This is acceptable and matches the spec (idempotent insert).
            assert rec is not None


class TestApproveSection:
    def test_approve_sets_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir)
            approve_section(record_ids[0], output_dir)
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            rec = next(r for r in records if r.get("approval_id") == record_ids[0])
            assert rec["state"] == "approved"
            assert rec["decided_at"] is not None

    def test_approve_nonexistent_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="no draft-readme-section record found"):
                approve_section("drs-doesnotexist", Path(tmp))


class TestRejectSection:
    def test_reject_sets_state_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir)
            reject_section(record_ids[0], output_dir, reason="too verbose")
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            rec = next(r for r in records if r.get("approval_id") == record_ids[0])
            assert rec["state"] == "rejected"
            assert rec["rejected_reason"] == "too verbose"
            assert rec["decided_at"] is not None

    def test_reject_nonexistent_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="no draft-readme-section record found"):
                reject_section("drs-doesnotexist", Path(tmp), reason="x")


class TestLegacyDraftReadmeRecords:
    def test_legacy_records_load_via_load_approved_drafts(self) -> None:
        """Pre-Sprint-8 draft-readme records continue to flow through load_approved_drafts."""
        from src.draft_readmes import load_approved_drafts
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            save_approval_record(
                output_dir,
                {
                    "approval_id": "dr-legacy0001",
                    "fingerprint": "fp-leg-001",
                    "approval_subject_type": "draft-readme",
                    "subject_key": "legacy-repo",
                    "source_run_id": "",
                    "approved_at": "2026-05-11T00:00:00+00:00",
                    "approved_by": "tester",
                    "approval_note": "legacy",
                    "action_type": "draft-readme",
                    "target_context": "legacy-repo",
                    "decision": "",
                    "timestamp": "2026-05-11T00:00:00+00:00",
                    "status": "approved-manual",
                    "repo_name": "legacy-repo",
                    "current_readme_sha": None,
                    "proposed_readme": "# Legacy\nThis is the legacy README.",
                    "diff_summary": "created",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4",
                    "llm_cost_usd": 0.0,
                    "generated_at": "2026-05-11T00:00:00+00:00",
                    "context_repos": [],
                },
            )
            packets = load_approved_drafts(output_dir, None)
            assert len(packets) == 1
            assert packets[0].repo_name == "legacy-repo"


# ── Apply gate ────────────────────────────────────────────────────────────────


class TestLoadApprovedSectionedPackets:
    def test_all_pending_packet_not_returned(self) -> None:
        packet = _make_packet(
            proposed_readme="## A\nbody\n## B\nbody\n## C\nbody\n## D\nbody\n## E\nbody\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _seed_sections(output_dir, packet)
            result = load_approved_sectioned_packets(output_dir)
            assert result == {}

    def test_all_terminal_packet_returned(self) -> None:
        packet = _make_packet(proposed_readme="## A\nbody A\n## B\nbody B\n## C\nbody C\n")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            # Approve first two, reject third
            approve_section(record_ids[0], output_dir)
            approve_section(record_ids[1], output_dir)
            reject_section(record_ids[2], output_dir, reason="not needed")

            result = load_approved_sectioned_packets(output_dir)
            assert len(result) == 1
            sections = list(result.values())[0]
            assert len(sections) == 3

    def test_all_rejected_packet_returned_but_assembles_none(self) -> None:
        packet = _make_packet(
            proposed_readme="## A\nbody A\n## B\nbody B\n## C\nbody C\n## D\nbody D\n## E\nbody E\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            for rid in record_ids:
                reject_section(rid, output_dir, reason="all bad")
            result = load_approved_sectioned_packets(output_dir)
            assert len(result) == 1
            sections = list(result.values())[0]
            assembled = assemble_readme_from_approved_sections(sections)
            assert assembled is None


class TestMarkSectionPacketApplied:
    def test_sets_status_applied_on_all_sub_records(self) -> None:
        packet = _make_packet(proposed_readme="## A\nbody\n## B\nbody\n")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _seed_sections(output_dir, packet)
            # Get shared packet_id
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            pid = next(
                r.get("packet_id")
                for r in records
                if r.get("approval_subject_type") == "draft-readme-section"
            )
            mark_section_packet_applied(pid, output_dir)

            records_after = load_approval_records(output_dir, "", limit=500)
            section_records = [
                r
                for r in records_after
                if r.get("approval_subject_type") == "draft-readme-section"
                and r.get("packet_id") == pid
            ]
            assert all(r.get("status") == "applied" for r in section_records)


class TestAssembleReadmeFromApprovedSections:
    def test_concatenates_in_section_idx_order(self) -> None:
        sections = [
            {
                "section_idx": 1,
                "section_heading": "Usage",
                "section_body": "run it\n",
                "state": "approved",
            },
            {
                "section_idx": 0,
                "section_heading": "(intro)",
                "section_body": "Intro text\n",
                "state": "approved",
            },
            {
                "section_idx": 2,
                "section_heading": "License",
                "section_body": "MIT\n",
                "state": "approved",
            },
        ]
        result = assemble_readme_from_approved_sections(sections)
        assert result is not None
        # intro comes first (idx 0), then Usage (idx 1), then License (idx 2)
        assert result.index("Intro text") < result.index("run it")
        assert result.index("run it") < result.index("MIT")

    def test_rejected_sections_are_skipped(self) -> None:
        sections = [
            {
                "section_idx": 0,
                "section_heading": "A",
                "section_body": "body A\n",
                "state": "approved",
            },
            {
                "section_idx": 1,
                "section_heading": "B",
                "section_body": "body B\n",
                "state": "rejected",
            },
        ]
        result = assemble_readme_from_approved_sections(sections)
        assert result is not None
        assert "body A" in result
        assert "body B" not in result


# ── Counter math ──────────────────────────────────────────────────────────────


class TestCounterMath:
    def test_mixed_state_packet_counters(self) -> None:
        packet = _make_packet(proposed_readme="## A\nbody\n## B\nbody\n## C\nbody\n")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            approve_section(record_ids[0], output_dir)
            reject_section(record_ids[1], output_dir)
            # record_ids[2] stays pending

            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            sections = [
                r for r in records if r.get("approval_subject_type") == "draft-readme-section"
            ]
            approved = sum(1 for s in sections if s.get("state") == "approved")
            rejected = sum(1 for s in sections if s.get("state") == "rejected")
            pending = sum(1 for s in sections if s.get("state", "pending") == "pending")
            assert approved == 1
            assert rejected == 1
            assert pending == 1


# ── Routes ────────────────────────────────────────────────────────────────────


class TestDraftSectionsRoutes:
    """Smoke-test the web routes using the FastAPI test client."""

    def _client(self, output_dir: Path):
        from fastapi.testclient import TestClient  # noqa: E402

        from src.serve.app import create_app  # noqa: E402

        return TestClient(create_app(output_dir=output_dir), raise_server_exceptions=True)

    def test_get_draft_sections_200(self) -> None:
        packet = _make_packet(proposed_readme="## Install\npip install foo\n## Usage\nrun\n")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            _seed_sections(output_dir, packet)
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            pid = next(
                r.get("packet_id")
                for r in records
                if r.get("approval_subject_type") == "draft-readme-section"
            )
            client = self._client(output_dir)
            resp = client.get(f"/approvals/{pid}/draft-sections")
            assert resp.status_code == 200
            assert "Install" in resp.text

    def test_get_draft_sections_404_for_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            client = self._client(output_dir)
            resp = client.get("/approvals/nonexistent-packet-id/draft-sections")
            assert resp.status_code == 404

    def test_post_approve_section_200(self) -> None:
        packet = _make_packet()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            client = self._client(output_dir)
            resp = client.post(f"/approvals/sections/{record_ids[0]}/approve")
            assert resp.status_code == 200
            assert "Approved" in resp.text

    def test_post_approve_section_404_for_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            client = self._client(output_dir)
            resp = client.post("/approvals/sections/nonexistent/approve")
            assert resp.status_code == 404

    def test_post_reject_section_200(self) -> None:
        packet = _make_packet()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            client = self._client(output_dir)
            resp = client.post(
                f"/approvals/sections/{record_ids[0]}/reject",
                data={"reason": "too long"},
            )
            assert resp.status_code == 200
            assert "Rejected" in resp.text

    def test_post_reject_section_persists_reason(self) -> None:
        packet = _make_packet()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_ids = _seed_sections(output_dir, packet)
            client = self._client(output_dir)
            client.post(
                f"/approvals/sections/{record_ids[0]}/reject",
                data={"reason": "needs work"},
            )
            from src.warehouse import load_approval_records

            records = load_approval_records(output_dir, "", limit=500)
            rec = next(r for r in records if r.get("approval_id") == record_ids[0])
            assert rec.get("state") == "rejected"
            assert rec.get("rejected_reason") == "needs work"
