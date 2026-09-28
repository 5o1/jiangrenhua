#!/usr/bin/env python3
"""Audit common structural and PDF issues in an HTML project paper."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys


STYLE_PHRASES = (
    "不是",
    "而是",
    "并非",
    "而非",
    "值得注意的是",
    "这意味着",
)

AUTHORIAL_MARKERS = ("我们", "本研究", "本文")
AGENCY_CUES = (
    "采用", "选择", "设计", "比较", "分析", "评估", "检验", "判断",
    "认为", "提出", "解释", "归纳", "决定", "计划", "设置", "报告",
    "记录", "观察", "讨论", "限制", "不能宣称", "需要", "应",
    "冻结", "训练", "加入", "重放", "构建", "使用", "计算", "保留",
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


class ParagraphExtractor(HTMLParser):
    """Collect prose blocks with their section and source line for human review."""

    def __init__(self) -> None:
        super().__init__()
        self.section = "开篇"
        self.paragraphs: list[dict[str, object]] = []
        self._capture: tuple[str, int, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture is not None:
            return
        classes = dict(attrs).get("class") or ""
        block = "abstract" if tag == "div" and "abstract" in classes.split() else tag
        if tag in {"h1", "h2", "h3"} or (tag == "p" and not any(
            name in classes.split() for name in ("meta", "caption")
        )) or (tag == "div" and any(
            name in classes.split() for name in ("abstract", "callout")
        )):
            self._capture = (block, self.getpos()[0], [])

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture is None or not (
            self._capture[0] == tag or tag == "div" and self._capture[0] == "abstract"
        ):
            return
        block, line, parts = self._capture
        value = " ".join(" ".join(parts).split())
        self._capture = None
        if block in {"h1", "h2", "h3"}:
            self.section = value
        elif value and "参考文献" not in self.section:
            self.paragraphs.append({
                "section": "摘要" if block == "abstract" else self.section,
                "line": line,
                "text": value,
            })


def audit_authorial_voice(html: str) -> dict[str, object]:
    """Return review candidates; lexical cues cannot decide rhetorical agency."""
    extractor = ParagraphExtractor()
    extractor.feed(html)
    sections: dict[str, dict[str, int]] = {}
    candidates: list[dict[str, object]] = []
    for paragraph in extractor.paragraphs:
        section = str(paragraph["section"])
        value = str(paragraph["text"])
        has_author = any(marker in value for marker in AUTHORIAL_MARKERS)
        counts = sections.setdefault(section, {"paragraphs": 0, "with_explicit_author": 0})
        counts["paragraphs"] += 1
        counts["with_explicit_author"] += int(has_author)
        cues = [cue for cue in AGENCY_CUES if cue in value]
        if cues and not has_author:
            candidates.append({
                "section": section,
                "line": paragraph["line"],
                "fingerprint": hashlib.sha256(f"{section}\n{value}".encode("utf-8")).hexdigest()[:16],
                "cues": cues,
                "excerpt": value[:150],
            })
    return {
        "note": "Candidates require paragraph-level human review, not pronoun quotas or automatic failure.",
        "sections": sections,
        "candidates": candidates,
    }


def audit_voice_review(voice: dict[str, object], path: Path) -> tuple[dict[str, object], bool]:
    """Gate unresolved candidates while leaving their semantic disposition to reviewers."""
    review = json.loads(path.read_text(encoding="utf-8"))
    entries = review.get("retained_candidates")
    if not isinstance(entries, list):
        raise ValueError("voice review needs a retained_candidates list")
    retained: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each retained candidate must be an object")
        fingerprint, reason = entry.get("fingerprint"), entry.get("reason")
        if not isinstance(fingerprint, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("each retained candidate needs a fingerprint and nonempty reason")
        if fingerprint in retained:
            raise ValueError(f"duplicate voice review fingerprint: {fingerprint}")
        retained[fingerprint] = reason.strip()
    candidates = voice["candidates"]
    assert isinstance(candidates, list)
    current = {str(candidate["fingerprint"]) for candidate in candidates}
    unresolved = [candidate for candidate in candidates if candidate["fingerprint"] not in retained]
    stale = sorted(set(retained) - current)
    result: dict[str, object] = {
        "file": str(path),
        "retained_candidate_count": len(retained),
        "unresolved_candidates": unresolved,
        "stale_review_fingerprints": stale,
    }
    return result, bool(unresolved or stale)


def audit_html(path: Path) -> tuple[dict[str, object], bool]:
    html = path.read_text(encoding="utf-8")
    reference_marker = re.search(r'<h[1-6][^>]*id=["\']references["\']', html, re.I)
    if reference_marker:
        body = html[: reference_marker.start()]
        references = html[reference_marker.start() :]
    else:
        body, references = html, ""

    used = {int(value) for value in re.findall(r"\[(\d+)\]", visible_text(body))}
    defined = {
        int(value)
        for value in re.findall(r"<(?:p|li)[^>]*>\s*\[(\d+)\]", references, re.I)
    }
    text = visible_text(body)
    phrases = {phrase: text.count(phrase) for phrase in STYLE_PHRASES}
    external_links = re.findall(r'href=["\']https?://[^"\']+["\']', html, re.I)
    headings = [
        re.sub(r"<[^>]+>", "", title).strip()
        for title in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.I | re.S)
    ]
    empty_cells = len(re.findall(r"<(?:td|th)[^>]*>\s*</(?:td|th)>", html, re.I))
    missing = sorted(used - defined)
    unused = sorted(defined - used)
    result: dict[str, object] = {
        "file": str(path),
        "headings": headings,
        "citation_numbers_used": sorted(used),
        "reference_numbers_defined": sorted(defined),
        "missing_reference_definitions": missing,
        "uncited_reference_entries": unused,
        "external_link_count": len(external_links),
        "style_phrase_counts": phrases,
        "authorial_voice": audit_authorial_voice(html),
        "empty_table_cells": empty_cells,
    }
    failed = bool(missing or unused or empty_cells)
    return result, failed


def audit_pdf(path: Path) -> tuple[dict[str, object], bool]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return {
            "file": str(path),
            "skipped": "Install pypdf in a temporary environment to enable PDF inspection.",
        }, False

    reader = PdfReader(str(path))
    page_text = [(page.extract_text() or "").strip() for page in reader.pages]
    empty_pages = [index + 1 for index, text in enumerate(page_text) if not text]
    annotations = sum(len(page.get("/Annots") or []) for page in reader.pages)
    result: dict[str, object] = {
        "file": str(path),
        "page_count": len(reader.pages),
        "empty_pages": empty_pages,
        "link_annotation_count": annotations,
        "metadata_title": reader.metadata.title,
    }
    return result, bool(empty_pages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--voice-review", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.html.is_file():
        parser.error(f"HTML file not found: {args.html}")
    report: dict[str, object] = {}
    report["html"], failed = audit_html(args.html)
    if args.voice_review:
        if not args.voice_review.is_file():
            parser.error(f"Voice review file not found: {args.voice_review}")
        try:
            report["authorial_voice_review"], voice_failed = audit_voice_review(
                report["html"]["authorial_voice"], args.voice_review
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            parser.error(f"Invalid voice review: {error}")
        failed = failed or voice_failed
    if args.pdf:
        if not args.pdf.is_file():
            parser.error(f"PDF file not found: {args.pdf}")
        report["pdf"], pdf_failed = audit_pdf(args.pdf)
        failed = failed or pdf_failed

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("\nResult:", "FAIL" if failed else "PASS")
        print("Style and authorial-voice findings are review prompts, not automatic failures.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
