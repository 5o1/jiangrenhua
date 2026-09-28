#!/usr/bin/env python3
"""Run one cold-context Codex evaluation for a proposed semantic version.

This is intentionally never called from normal commit or GitHub CI jobs.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "evals/artifacts"
SKILL = ROOT / "skills/write-project-paper"
FIXTURE = ROOT / "evals/fixtures/tiny-robot"
AUDITOR = SKILL / "scripts/audit_paper.py"
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
OUTPUT_FILES = ("paper.html", "paper.pdf", "paper_review.md", "paper_voice_review.json")
REVIEW_CHECKS = (
    "claims_grounded",
    "authorial_voice",
    "beginner_readability",
    "four_round_review",
    "pdf_visual",
)


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"expected A.B.C semantic version, got {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_commit() -> str:
    return git("rev-parse", "HEAD")


def artifact_dir(version: str, commit: str) -> Path:
    return ARTIFACTS / f"v{version}" / commit[:12]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def explicit_prompt() -> str:
    with (ROOT / "evals/prompts.csv").open(newline="", encoding="utf-8") as handle:
        cases = {row["id"]: row for row in csv.DictReader(handle)}
    if "explicit" not in cases:
        raise ValueError("evals/prompts.csv lacks the explicit case")
    return (
        cases["explicit"]["prompt"]
        + " 请先读取当前工作目录中的 .codex/skills/write-project-paper/SKILL.md"
        + " 及其明确要求的参考文件，并执行其中的工作流程。"
        + "这是合成、纯仿真的测试项目。只使用当前工作目录中的证据，"
        + "不要读取外部项目或猜测缺失的方法。请在工作目录根部生成且只生成"
        + " paper.html、paper.pdf、paper_review.md、paper_voice_review.json 四项论文产物。"
        + "后者采用 skill 规定的 retained_candidates JSON 格式；即使没有保留项也写空列表。"
        + "请在正文清楚报告 baseline 1/3、candidate 2/3，并说明样本不足以证明泛化或真机表现。"
    )


def check_prerequisites() -> None:
    if shutil.which("codex") is None:
        raise RuntimeError("codex CLI not found; no paid evaluation was started")
    for module in ("pypdf", "weasyprint"):
        if importlib.util.find_spec(module) is None:
            raise RuntimeError(
                f"{module} missing; install evals/requirements.txt before starting the paid evaluation"
            )


def run(version: str) -> Path:
    parse_version(version)
    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if parse_version(version) <= parse_version(current):
        raise ValueError(f"proposed version {version} must exceed current {current}")
    if git("status", "--porcelain"):
        raise RuntimeError("commit source changes before the cold-context evaluation")
    commit = source_commit()
    destination = artifact_dir(version, commit)
    summary_path = destination / "summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("source_commit") != commit or summary.get("version") != version:
            raise RuntimeError("cached evaluation does not match this source/version")
        if not summary.get("machine_pass"):
            raise RuntimeError("cached evaluation failed; fix and commit source before another run")
        print(f"Reusing one completed model run: {summary_path}")
        return destination
    if destination.exists():
        raise RuntimeError(f"incomplete run exists at {destination}; inspect it before retrying")
    check_prerequisites()
    destination.mkdir(parents=True)
    workspace = destination / "workspace"
    shutil.copytree(FIXTURE, workspace)
    local_skill = workspace / ".codex/skills/write-project-paper"
    local_skill.parent.mkdir(parents=True)
    shutil.copytree(SKILL, local_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    prompt = explicit_prompt()
    command = [
        "codex", "exec", "--json", "--ephemeral", "--ignore-user-config",
        "--sandbox", "workspace-write", "-C", str(workspace), prompt,
    ]
    started = datetime.now(timezone.utc).isoformat()
    cli_version = subprocess.check_output(["codex", "--version"], text=True).strip()
    exit_code = -1
    timed_out = False
    with (destination / "trace.jsonl").open("w", encoding="utf-8") as trace, (
        destination / "stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        try:
            exit_code = subprocess.run(
                command, cwd=workspace, stdout=trace, stderr=stderr,
                timeout=1200, check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
    missing = [name for name in OUTPUT_FILES if not (workspace / name).is_file()]
    audit_exit: int | None = None
    audit_report: dict[str, object] = {}
    if exit_code == 0 and not missing:
        result = subprocess.run(
            [sys.executable, str(AUDITOR), str(workspace / "paper.html"),
             "--pdf", str(workspace / "paper.pdf"),
             "--voice-review", str(workspace / "paper_voice_review.json"), "--json"],
            capture_output=True, text=True, check=False,
        )
        audit_exit = result.returncode
        (destination / "audit.json").write_text(result.stdout, encoding="utf-8")
        (destination / "audit.stderr.log").write_text(result.stderr, encoding="utf-8")
        if result.returncode == 0:
            audit_report = json.loads(result.stdout)
    html = (workspace / "paper.html").read_text(encoding="utf-8") if not missing and exit_code == 0 else ""
    basic_facts = all(value in html for value in ("1/3", "2/3", "仿真"))
    pdf_info = audit_report.get("pdf", {})
    pdf_checked = isinstance(pdf_info, dict) and not pdf_info.get("skipped") and pdf_info.get("page_count", 0) > 0
    machine_pass = exit_code == 0 and not missing and audit_exit == 0 and basic_facts and pdf_checked
    files = {name: file_hash(workspace / name) for name in OUTPUT_FILES if (workspace / name).is_file()}
    summary = {
        "schema": 1,
        "version": version,
        "source_commit": commit,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "codex_version": cli_version,
        "codex_exit": exit_code,
        "timed_out": timed_out,
        "missing_outputs": missing,
        "audit_exit": audit_exit,
        "basic_facts_present": basic_facts,
        "pdf_checked": pdf_checked,
        "machine_pass": machine_pass,
        "file_hashes": files,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if machine_pass:
        review = {
            "version": version,
            "source_commit": commit,
            "file_hashes": files,
            "reviewer": "",
            "checks": {check: {"pass": False, "evidence": ""} for check in REVIEW_CHECKS},
            "notes": "",
        }
        (destination / "human_review.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Model run and mechanical checks complete. Review text/PDF, then fill {destination / 'human_review.json'}")
    else:
        print(f"Evaluation failed; inspect {destination}. Version remains unchanged.", file=sys.stderr)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="proposed A.B.C version; no Git tag is created")
    args = parser.parse_args()
    try:
        destination = run(args.version)
        summary = json.loads((destination / "summary.json").read_text(encoding="utf-8"))
        return 0 if summary["machine_pass"] else 1
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
