"""Check the distributable skill and synthetic eval fixture stay self-contained."""

from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/write-project-paper"


class ProjectLayoutTests(unittest.TestCase):
    def test_skill_metadata_and_local_references(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name: write-project-paper$")
        self.assertRegex(text, r"(?m)^description: .+$")
        for relative in re.findall(r"\]\((references/[^)]+)\)", text):
            self.assertTrue((SKILL / relative).is_file(), relative)

    def test_fixture_counts(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "evals/fixtures/tiny-robot/evaluate.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.splitlines(), ["baseline: 1/3", "candidate: 2/3"])


if __name__ == "__main__":
    unittest.main()
