from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from github_repo_auditor.portfolio_generation import (
    _terminal_observed_in_order,
    ArtifactInput,
    PortfolioGenerationError,
    ProducerBinding,
    SecurityBinding,
    publish_generation,
    read_pointer,
    resolve_current,
    swap_current_previous,
    writer_lock,
)


CREATED = datetime(2026, 8, 25, 17, 0, tzinfo=UTC)
COMMIT = "7fcd062c3ff2fa9ddda00b6a8aba5e03022f2cdf"


def producer() -> ProducerBinding:
    return ProducerBinding(
        repository="saagpatel/GithubRepoAuditor",
        commit=COMMIT,
        receipt_id="sha256:" + "a" * 64,
        receipt_sha256="b" * 64,
        verified_at="2026-08-25T16:59:00Z",
    )


def security(*, commit: str = COMMIT, valid: bool = True) -> SecurityBinding:
    return SecurityBinding(
        schema_version="GitHubSecurityCoverageReceiptV1",
        receipt_id="sha256:" + "c" * 64,
        content_sha256="d" * 64,
        produced_at="2026-08-25T16:30:00Z",
        evaluated_at="2026-08-25T17:00:00Z",
        valid_until=(
            "2026-08-25T17:30:00Z" if valid else "2026-08-25T16:45:00Z"
        ),
        max_age_hours=1,
        producer_repository="saagpatel/GithubRepoAuditor",
        producer_commit=commit,
        state="fresh",
        terminal_schema="AutomationTerminalStateV1",
        terminal_state="succeeded",
        terminal_content_sha256="e" * 64,
        terminal_observed_at="2026-08-25T17:00:00Z",
        terminal_automation_id="com.d.github-security-coverage.rehearsal",
        terminal_destination="/task/security.json",
        terminal_operator_commit="b63d437655b3316d2beb449ab6a3f6397680d67f",
        terminal_controlled=True,
    )


class PortfolioGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=os.environ.get("TMPDIR"), prefix="portfolio-generation-test-"
        )
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inputs(self, marker: str = "one") -> list[ArtifactInput]:
        truth = self.base / f"truth-{marker}.json"
        digest = self.base / f"digest-{marker}.json"
        markdown = self.base / f"digest-{marker}.md"
        truth.write_text(
            json.dumps({"schema_version": "0.12.0", "marker": marker})
        )
        digest.write_text(
            json.dumps(
                {
                    "contract_version": "portfolio_decision_digest_v2",
                    "marker": marker,
                }
            )
        )
        markdown.write_text(f"# Portfolio {marker}\n")
        return [
            ArtifactInput(
                "portfolio-truth.json",
                truth,
                "application/json",
                "ghra.portfolio_truth@0.12.0",
            ),
            ArtifactInput(
                "decision-queue-v2.json",
                digest,
                "application/json",
                "portfolio_decision_digest_v2",
            ),
            ArtifactInput(
                "portfolio-digest.md",
                markdown,
                "text/markdown",
                "portfolio_digest_markdown_v1",
            ),
        ]

    def publish(self, root: Path, marker: str, *, when: datetime):
        return publish_generation(
            root=root,
            artifacts=self.inputs(marker),
            producer=producer(),
            security=security(),
            created_at=when,
        )

    def test_publishes_content_derived_immutable_generation_and_atomic_pair(self):
        root = self.base / "managed"
        first = self.publish(root, "one", when=CREATED)
        second = self.publish(root, "two", when=CREATED + timedelta(minutes=1))
        self.assertNotEqual(first.generation_id, second.generation_id)
        pointer = read_pointer(root)
        self.assertEqual(pointer["current"]["generation_id"], second.generation_id)
        self.assertEqual(pointer["previous"]["generation_id"], first.generation_id)
        self.assertEqual(resolve_current(root).manifest_sha256, second.manifest_sha256)

    def test_process_death_never_leaves_an_invalid_pointer(self):
        steps = (
            "after_lock",
            "after_stage_created",
            "after_artifacts_written",
            "after_manifest_written",
            "after_stage_validated",
            "after_generation_visible",
            "after_pointer_staged",
            "after_pointer_replaced",
            "after_readback",
        )
        for step in steps:
            with self.subTest(step=step):
                root = self.base / f"managed-{step}"
                first = self.publish(root, f"one-{step}", when=CREATED)
                pid = os.fork()
                if pid == 0:
                    os.environ["PORTFOLIO_GENERATION_CRASH_AT"] = step
                    self.publish(
                        root,
                        f"two-{step}",
                        when=CREATED + timedelta(minutes=1),
                    )
                    os._exit(0)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 97)
                resolved = resolve_current(root)
                self.assertEqual(
                    resolved.generation_id,
                    read_pointer(root)["current"]["generation_id"],
                )
                if step not in {"after_pointer_replaced", "after_readback"}:
                    self.assertEqual(resolved.generation_id, first.generation_id)

    def test_concurrent_writer_is_refused(self):
        root = self.base / "managed"
        ready_read, ready_write = os.pipe()
        release_read, release_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(ready_read)
            os.close(release_write)
            with writer_lock(root):
                os.write(ready_write, b"1")
                os.read(release_read, 1)
            os._exit(0)
        os.close(ready_write)
        os.close(release_read)
        self.assertEqual(os.read(ready_read, 1), b"1")
        with self.assertRaisesRegex(PortfolioGenerationError, "writer lock is held"):
            with writer_lock(root):
                pass
        os.write(release_write, b"1")
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)

    def test_tampered_pointer_manifest_and_artifacts_are_rejected(self):
        root = self.base / "managed"
        result = self.publish(root, "one", when=CREATED)
        pointer_path = root / "pointer.json"
        original_pointer = pointer_path.read_bytes()
        pointer = json.loads(original_pointer)
        pointer["current"]["manifest_sha256"] = "0" * 64
        pointer_path.write_text(json.dumps(pointer))
        with self.assertRaisesRegex(PortfolioGenerationError, "manifest hash mismatch"):
            resolve_current(root)

        pointer_path.write_bytes(original_pointer)
        truth = result.generation_dir / "portfolio-truth.json"
        original_truth = truth.read_bytes()
        truth.write_bytes(b"{}")
        with self.assertRaisesRegex(
            PortfolioGenerationError, "artifact (size|hash) mismatch"
        ):
            resolve_current(root)

        truth.write_bytes(original_truth)
        manifest = result.generation_dir / "manifest.json"
        manifest.write_text("{}")
        with self.assertRaisesRegex(PortfolioGenerationError, "manifest hash mismatch"):
            resolve_current(root)

    def test_missing_artifact_and_current_previous_corruption_are_rejected(self):
        root = self.base / "managed"
        first = self.publish(root, "one", when=CREATED)
        self.publish(root, "two", when=CREATED + timedelta(minutes=1))
        (first.generation_dir / "portfolio-digest.md").unlink()
        with self.assertRaisesRegex(PortfolioGenerationError, "artifact .* is missing"):
            read_pointer(root)

        pointer_path = root / "pointer.json"
        pointer = json.loads(pointer_path.read_text())
        pointer["previous"] = pointer["current"]
        pointer_path.write_text(json.dumps(pointer))
        with self.assertRaisesRegex(PortfolioGenerationError, "identical"):
            read_pointer(root)

    def test_wrong_producer_stale_security_and_source_drift_fail_closed(self):
        root = self.base / "managed"
        with self.assertRaisesRegex(PortfolioGenerationError, "commits disagree"):
            publish_generation(
                root=root,
                artifacts=self.inputs("wrong"),
                producer=producer(),
                security=security(commit="9" * 40),
                created_at=CREATED,
            )
        with self.assertRaisesRegex(PortfolioGenerationError, "expired"):
            publish_generation(
                root=root,
                artifacts=self.inputs("stale"),
                producer=producer(),
                security=security(valid=False),
                created_at=CREATED,
            )
        first = self.publish(root, "one", when=CREATED)

        def drift() -> None:
            raise PortfolioGenerationError("source commit drift")

        with self.assertRaisesRegex(PortfolioGenerationError, "source commit drift"):
            publish_generation(
                root=root,
                artifacts=self.inputs("two"),
                producer=producer(),
                security=security(),
                created_at=CREATED + timedelta(minutes=1),
                pre_pointer_check=drift,
            )
        self.assertEqual(resolve_current(root).generation_id, first.generation_id)

    def test_rollback_and_roll_forward_swap_the_exact_pair(self):
        root = self.base / "managed"
        first = self.publish(root, "one", when=CREATED)
        second = self.publish(root, "two", when=CREATED + timedelta(minutes=1))
        rolled_back = swap_current_previous(
            root, updated_at=CREATED + timedelta(minutes=2)
        )
        self.assertEqual(rolled_back["current"]["generation_id"], first.generation_id)
        self.assertEqual(rolled_back["previous"]["generation_id"], second.generation_id)
        rolled_forward = swap_current_previous(
            root, updated_at=CREATED + timedelta(minutes=3)
        )
        self.assertEqual(rolled_forward["current"]["generation_id"], second.generation_id)
        self.assertEqual(rolled_forward["previous"]["generation_id"], first.generation_id)


if __name__ == "__main__":
    unittest.main()


class TerminalObservationOrderTests(unittest.TestCase):
    def test_same_second_terminal_is_accepted_and_earlier_second_is_refused(self) -> None:
        from datetime import UTC, datetime

        produced = datetime(2026, 9, 2, 12, 8, 8, 576236, tzinfo=UTC)
        now = datetime(2026, 9, 2, 12, 10, 0, tzinfo=UTC)
        same_second = datetime(2026, 9, 2, 12, 8, 8, tzinfo=UTC)
        earlier = datetime(2026, 9, 2, 12, 8, 7, tzinfo=UTC)
        later = datetime(2026, 9, 2, 12, 8, 9, tzinfo=UTC)
        future = datetime(2026, 9, 2, 12, 11, 0, tzinfo=UTC)
        self.assertTrue(_terminal_observed_in_order(same_second, produced, now))
        self.assertTrue(_terminal_observed_in_order(later, produced, now))
        self.assertFalse(_terminal_observed_in_order(earlier, produced, now))
        self.assertFalse(_terminal_observed_in_order(future, produced, now))
