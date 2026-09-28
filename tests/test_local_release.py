"""Release-gate tests use synthetic records; they never invoke an agent."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.release import OUTPUT_FILES, REVIEW_CHECKS, file_hash, parse_version, verify_review


class LocalReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.destination = Path(self.tmp.name)
        workspace = self.destination / "workspace"
        workspace.mkdir()
        for name in OUTPUT_FILES:
            (workspace / name).write_bytes(f"synthetic {name}".encode())
        self.hashes = {name: file_hash(workspace / name) for name in OUTPUT_FILES}
        self.summary = {
            "version": "0.1.0", "source_commit": "abc123", "machine_pass": True,
            "codex_exit": 0, "audit_exit": 0, "pdf_checked": True,
            "basic_facts_present": True, "timed_out": False,
            "missing_outputs": [], "file_hashes": self.hashes,
        }
        self.review = {
            "version": "0.1.0", "source_commit": "abc123",
            "file_hashes": copy.deepcopy(self.hashes), "reviewer": "Test reviewer",
            "checks": {
                name: {"pass": True, "evidence": f"paper.html: {name} paragraph checked"}
                for name in REVIEW_CHECKS
            },
        }
        self.write_records()

    def write_records(self) -> None:
        (self.destination / "summary.json").write_text(json.dumps(self.summary), encoding="utf-8")
        (self.destination / "human_review.json").write_text(json.dumps(self.review), encoding="utf-8")

    def test_semver_and_valid_review(self) -> None:
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        with self.assertRaises(ValueError):
            parse_version("01.2.3")
        verify_review(self.destination, "0.1.0", "abc123")

    def test_text_rejection_blocks_release(self) -> None:
        self.review["checks"]["authorial_voice"]["pass"] = False
        self.write_records()
        with self.assertRaisesRegex(ValueError, "authorial_voice"):
            verify_review(self.destination, "0.1.0", "abc123")

    def test_empty_evidence_blocks_release(self) -> None:
        self.review["checks"]["claims_grounded"]["evidence"] = " "
        self.write_records()
        with self.assertRaisesRegex(ValueError, "specific textual/page evidence"):
            verify_review(self.destination, "0.1.0", "abc123")

    def test_changed_generated_text_invalidates_review(self) -> None:
        (self.destination / "workspace/paper.html").write_text("altered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after evaluation"):
            verify_review(self.destination, "0.1.0", "abc123")

    def test_stale_commit_blocks_release(self) -> None:
        with self.assertRaisesRegex(ValueError, "source commit"):
            verify_review(self.destination, "0.1.0", "different")

    def test_machine_pass_alone_is_not_enough(self) -> None:
        (self.destination / "human_review.json").unlink()
        with self.assertRaisesRegex(ValueError, "semantic review is missing"):
            verify_review(self.destination, "0.1.0", "abc123")


if __name__ == "__main__":
    unittest.main()
