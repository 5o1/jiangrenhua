#!/usr/bin/env python3
"""Gate a local semantic-version release on one reviewed cold-context run.

Normal commits never run an agent. This command does not push to a remote.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
from run_local import (  # noqa: E402
    OUTPUT_FILES,
    REVIEW_CHECKS,
    artifact_dir,
    file_hash,
    parse_version,
    run as run_eval,
    source_commit,
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_review(destination: Path, version: str, commit: str) -> None:
    """Reject an absent, stale, incomplete, or negative semantic review."""
    summary_path = destination / "summary.json"
    review_path = destination / "human_review.json"
    if not summary_path.is_file():
        raise ValueError(f"no completed local evaluation: {summary_path}")
    if not review_path.is_file():
        raise ValueError(f"semantic review is missing: {review_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or not isinstance(review, dict):
        raise ValueError("evaluation records must be JSON objects")
    for record in (summary, review):
        if record.get("version") != version or record.get("source_commit") != commit:
            raise ValueError("evaluation/review does not match this version and source commit")
    if summary.get("machine_pass") is not True:
        raise ValueError("model run or mechanical audit failed")
    if (summary.get("codex_exit") != 0 or summary.get("audit_exit") != 0
            or summary.get("pdf_checked") is not True
            or summary.get("basic_facts_present") is not True
            or summary.get("timed_out") is not False
            or summary.get("missing_outputs") != []):
        raise ValueError("mechanical pass record is incomplete or inconsistent")
    hashes = summary.get("file_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(OUTPUT_FILES):
        raise ValueError("generated output hashes are incomplete")
    for name in OUTPUT_FILES:
        output = destination / "workspace" / name
        if not output.is_file() or file_hash(output) != hashes[name]:
            raise ValueError(f"generated output changed after evaluation: {output}")
    if review.get("file_hashes") != hashes:
        raise ValueError("semantic review does not cover these exact generated files")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError("semantic review needs an identified reviewer")
    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(REVIEW_CHECKS):
        raise ValueError(f"semantic review must cover all checks: {', '.join(REVIEW_CHECKS)}")
    for name in REVIEW_CHECKS:
        result = checks[name]
        if not isinstance(result, dict) or result.get("pass") is not True:
            raise ValueError(f"generated text has not passed semantic check: {name}")
        if not isinstance(result.get("evidence"), str) or not result["evidence"].strip():
            raise ValueError(f"semantic check needs specific textual/page evidence: {name}")


def test_suite() -> None:
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, check=True,
    )


def release(version: str) -> None:
    parse_version(version)
    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if parse_version(version) <= parse_version(current):
        raise ValueError(f"proposed version {version} must exceed current {current}")
    if git("status", "--porcelain"):
        raise ValueError("commit source changes before requesting a release")
    tag = f"v{version}"
    if subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0:
        raise ValueError(f"tag already exists: {tag}")
    commit = source_commit()
    test_suite()
    destination = artifact_dir(version, commit)
    if not (destination / "summary.json").is_file():
        run_eval(version)
    verify_review(destination, version, commit)
    (ROOT / "VERSION").write_text(version + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", "VERSION"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", f"Release {tag}"], cwd=ROOT, check=True)
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=ROOT, check=True)
    print(f"Local release {tag} created. No push was performed.")


def verify_staged_version() -> None:
    """Used by the local pre-commit hook for any staged VERSION change."""
    staged = git("diff", "--cached", "--name-only")
    if staged.splitlines() != ["VERSION"]:
        raise ValueError("a version commit may stage only VERSION")
    current = git("show", "HEAD:VERSION")
    proposed = git("show", ":VERSION")
    if parse_version(proposed) <= parse_version(current):
        raise ValueError("staged VERSION must increase")
    verify_review(artifact_dir(proposed, source_commit()), proposed, source_commit())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="proposed A.B.C version")
    parser.add_argument("--verify-staged", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.verify_staged:
            verify_staged_version()
        elif args.version:
            release(args.version)
        else:
            parser.error("provide a proposed A.B.C version")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release blocked: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
