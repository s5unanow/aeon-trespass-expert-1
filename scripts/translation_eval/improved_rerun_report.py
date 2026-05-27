# ruff: noqa: RUF001  — Cyrillic regex ranges are intentional.
"""Markdown reports for the S5U-802 improved calibration rerun."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .improved_rerun_core import (
    POC_ROOT,
    REPO_ROOT,
    PageRun,
    old_final_path,
    split_paragraphs,
)
from .qa_checks import QAFinding, all_checks, find_style_red_flags


def write_report(results: list[PageRun], out_dir: Path, model: str, effort: str) -> None:
    lines = [
        "# S5U-802 — improved S5U-776 rerun",
        "",
        f"Output folder: `{out_dir.relative_to(REPO_ROOT)}`",
        f"Model: `{model}` with Codex reasoning effort `{effort}`",
        "",
        "The original S5U-776 top-level artifacts were read-only inputs. "
        "`review-page-1.md` was not overwritten.",
        "",
        "Workflow: EN source -> 3 Codex translation variants -> Codex synthesis "
        "-> deterministic QA/style QA -> Codex editor -> Codex JSON style critic "
        "-> targeted paragraph repair -> final QA.",
        "",
        "## Summary",
        "",
        "| Page | QA v1 | QA editor | Critic findings | Repaired paragraphs | "
        "QA final | Wall (s) | Tokens |",
        "| --: | --: | --: | --: | -- | --: | --: | --: |",
    ]
    for result in results:
        wall = sum(call.wall_seconds for call in result.calls)
        tokens = sum(call.input_tokens + call.output_tokens for call in result.calls)
        repaired = ", ".join(result.repaired_ids) if result.repaired_ids else "none"
        lines.append(
            f"| {result.page} | {len(result.qa_v1)} | {len(result.qa_editor)} | "
            f"{result.critic_findings} | {repaired} | {len(result.qa_final)} | "
            f"{wall:.1f} | {tokens} |"
        )
    lines.extend(["", "## Artifacts", ""])
    lines.extend(
        [
            "- `inputs/page-{N}-en.txt` — copied source text.",
            "- `variants/page-{N}-{lens}.txt` — three independent Codex variants.",
            "- `synthesis/page-{N}-synth-v1.txt` — synthesized draft.",
            "- `editor/page-{N}-editor.txt` — final editor pass before critic.",
            "- `final/page-{N}-ru-final.txt` — post-repair final translation.",
            "- `qa/page-{N}-qa-{stage}.json` — deterministic QA/style findings.",
            "- `critic/page-{N}-critic.json` — S5U-800 style critic output.",
            "- `repair/page-{N}-repair-report.json` — S5U-801 targeted repair report.",
            "- `comparison.md` — old final vs improved final vs source/comments.",
            "",
        ]
    )
    for result in results:
        _append_page_report(lines, result)
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_page_report(lines: list[str], result: PageRun) -> None:
    lines.extend(
        [
            f"## Page {result.page}",
            "",
            "### Stage timings",
            "",
            "| Stage | Model | Wall (s) | Input tokens | Output tokens |",
            "| -- | -- | --: | --: | --: |",
        ]
    )
    for call in result.calls:
        lines.append(
            f"| {call.stage} | {call.model} | {call.wall_seconds} | "
            f"{call.input_tokens} | {call.output_tokens} |"
        )
    lines.extend(["", "### QA/style findings", ""])
    for label, findings in (
        ("v1", result.qa_v1),
        ("editor", result.qa_editor),
        ("final", result.qa_final),
    ):
        lines.append(f"{label}: {len(findings)}")
        lines.extend(format_findings(findings))
        lines.append("")


def format_findings(findings: list[QAFinding]) -> list[str]:
    if not findings:
        return ["_(none)_"]
    return [f"- `{finding.code}` — {finding.detail}" for finding in findings]


@dataclass(frozen=True)
class ReviewComment:
    paragraph_id: str
    en_text: str
    old_ru: str
    comment: str


def parse_review_comments(page: int) -> list[ReviewComment]:
    path = POC_ROOT / f"review-page-{page}.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^###\s+(P\d+)\s*$", text)
    comments: list[ReviewComment] = []
    for idx in range(1, len(sections), 2):
        paragraph_id = sections[idx]
        body = sections[idx + 1]
        comment = _extract_review_field(body, "Comment")
        if not comment or comment == "---":
            continue
        comments.append(
            ReviewComment(
                paragraph_id=paragraph_id,
                en_text=_extract_review_field(body, "EN"),
                old_ru=_extract_review_field(body, "RU"),
                comment=comment,
            )
        )
    return comments


def _extract_review_field(body: str, label: str) -> str:
    match = re.search(
        rf"\*\*{re.escape(label)}:\*\*\s*\n\n(?P<value>.*?)(?=\n\n\*\*|\n---|\Z)",
        body,
        re.DOTALL,
    )
    return match.group("value").strip() if match else ""


def write_comparison(results: list[PageRun], out_dir: Path) -> None:
    lines = [
        "# S5U-802 — comparison against S5U-776 review comments",
        "",
        "This artifact compares source text, old final text, improved final text, "
        "and existing human comments. Status is a deterministic aid based on "
        "text change plus style-QA removal; human review remains authoritative.",
        "",
    ]
    for result in results:
        _append_comparison_page(lines, result, out_dir)
    (out_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_comparison_page(lines: list[str], result: PageRun, out_dir: Path) -> None:
    old_paras = split_paragraphs(result.old_final)
    new_paras = split_paragraphs(result.final_text)
    comments = parse_review_comments(result.page)
    final_path = out_dir / "final" / f"page-{result.page}-ru-final.txt"
    lines.extend(
        [
            f"## Page {result.page}",
            "",
            f"Old final: `{old_final_path(result.page).relative_to(REPO_ROOT)}`",
            f"Improved final: `{final_path.relative_to(REPO_ROOT)}`",
            "",
            f"Final deterministic QA/style findings: {len(result.qa_final)}",
            "",
        ]
    )
    if not comments:
        lines.extend(["_(No existing human comments for this page.)_", ""])
        return
    for comment in comments:
        _append_comment_comparison(lines, comment, old_paras, new_paras)


def _append_comment_comparison(
    lines: list[str],
    comment: ReviewComment,
    old_paras: list[str],
    new_paras: list[str],
) -> None:
    index = int(comment.paragraph_id[1:]) - 1
    old_ru = old_paras[index] if index < len(old_paras) else comment.old_ru
    new_ru = new_paras[index] if index < len(new_paras) else ""
    status = comment_status(comment.comment, comment.en_text, old_ru, new_ru)
    lines.extend(
        [
            f"### {comment.paragraph_id} — {status}",
            "",
            "**Source:**",
            "",
            comment.en_text,
            "",
            "**Human comment / target:**",
            "",
            comment.comment,
            "",
            "**Old final:**",
            "",
            old_ru,
            "",
            "**Improved final:**",
            "",
            new_ru or "_(missing paragraph)_",
            "",
            "---",
            "",
        ]
    )


def comment_status(comment: str, en_text: str, old_ru: str, new_ru: str) -> str:
    if comment.strip().lower() == "all good":
        return "no change requested"
    if not new_ru:
        return "not improved: missing improved paragraph"
    old_flags = all_checks(en_text, old_ru)
    new_flags = all_checks(en_text, new_ru)
    old_style = len(find_style_red_flags(old_ru))
    new_style = len(find_style_red_flags(new_ru))
    if new_ru == old_ru:
        return "already matched human target" if comment_overlap(comment, old_ru) else "unchanged"
    if comment_overlap(comment, new_ru) > comment_overlap(comment, old_ru):
        return "improved toward human target"
    if comment_overlap(comment, new_ru) < comment_overlap(comment, old_ru):
        return "regressed away from human target"
    if len(new_flags) < len(old_flags) or new_style < old_style:
        return "improved by deterministic QA/style signal"
    if len(new_flags) > len(old_flags) or new_style > old_style:
        return "regressed by deterministic QA/style signal"
    return "changed; needs human spot-check"


def comment_overlap(comment: str, candidate: str) -> int:
    words = {
        word.lower()
        for word in re.findall(r"[А-Яа-яЁё]{5,}", comment)
        if word.lower() not in {"comment", "bad", "good", "note"}
    }
    candidate_lower = candidate.lower()
    return sum(1 for word in words if word in candidate_lower)
