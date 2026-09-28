"""Deterministic checks for the skill's HTML and review gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/write-project-paper/scripts/audit_paper.py"
spec = importlib.util.spec_from_file_location("audit_paper", SCRIPT)
assert spec is not None and spec.loader is not None
audit_paper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_paper)


class AuditPaperTests(unittest.TestCase):
    def test_researcher_and_reference_are_not_candidates(self) -> None:
        html = (
            "<h2>方法</h2><p>我们选择方案 A。</p>"
            "<h2 id='references'>参考文献</h2><p>[1] 作者选择方案 B。</p>"
        )
        voice = audit_paper.audit_authorial_voice(html)
        self.assertEqual(voice["candidates"], [])
        self.assertEqual(voice["sections"]["方法"]["with_explicit_author"], 1)

    def test_unresolved_candidate_fails_gate(self) -> None:
        voice = audit_paper.audit_authorial_voice("<h2>方法</h2><p>配置选择方案 A。</p>")
        self.assertEqual(len(voice["candidates"]), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.json"
            path.write_text('{"retained_candidates": []}', encoding="utf-8")
            report, failed = audit_paper.audit_voice_review(voice, path)
        self.assertTrue(failed)
        self.assertEqual(len(report["unresolved_candidates"]), 1)

    def test_review_must_match_current_paragraph(self) -> None:
        html = "<h2>方法</h2><p>配置选择方案 A。</p>"
        voice = audit_paper.audit_authorial_voice(html)
        candidate = voice["candidates"][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.json"
            path.write_text(json.dumps({"retained_candidates": [
                {"fingerprint": candidate["fingerprint"], "reason": "这里是在陈述已有配置，而非研究者选择。"}
            ]}, ensure_ascii=False), encoding="utf-8")
            report, failed = audit_paper.audit_voice_review(voice, path)
            self.assertFalse(failed)
            self.assertEqual(report["unresolved_candidates"], [])
            changed = audit_paper.audit_authorial_voice("<h2>方法</h2><p>配置选择方案 B。</p>")
            stale_report, stale_failed = audit_paper.audit_voice_review(changed, path)
        self.assertTrue(stale_failed)
        self.assertEqual(len(stale_report["unresolved_candidates"]), 1)
        self.assertEqual(len(stale_report["stale_review_fingerprints"]), 1)

    def test_missing_citation_is_failure(self) -> None:
        html = "<h2>方法</h2><p>我们采用方法 [2]。</p><h2 id='references'>参考文献</h2><p>[1] 条目</p>"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.html"
            path.write_text(html, encoding="utf-8")
            report, failed = audit_paper.audit_html(path)
        self.assertTrue(failed)
        self.assertEqual(report["missing_reference_definitions"], [2])
        self.assertEqual(report["uncited_reference_entries"], [1])


if __name__ == "__main__":
    unittest.main()
