"""Report writers for the ensemble POC.

Pure functions: take ``PageResult`` records and write Markdown artefacts
under the output directory. Kept separate from ``ensemble_poc.py`` so the
orchestrator stays focused on the API-call workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .rules import BAD_GOOD_EXAMPLES, FORBIDDEN_PHRASES, GLOSSARY

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .ensemble_poc import PageResult


def write_report(results: list[PageResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_header = (
        "| Page | QA findings (v1) | QA findings (v2) | "
        "Sonnet wall (s) | Opus wall (s) | Total tokens |"
    )
    lines: list[str] = [
        "# S5U-776 — ensemble translation POC (LOCAL ONLY)",
        "",
        "This report is the deliverable for S5U-776. Per the issue owner's",
        "direction, all generated translations and this report stay local",
        "under `tmp/translation-eval/s5u-776-ensemble-poc/` (gitignored).",
        "",
        "Workflow: EN → Sonnet 3 variants → Opus synthesis → automated QA",
        "→ TranslateGemma omission witness → Opus minimal repair → final.",
        "",
        "## Per-page summary",
        "",
        summary_header,
        "| --: | --: | --: | --: | --: | --: |",
    ]
    for r in results:
        sonnet_wall = sum(c.wall_seconds for c in r.calls if c.stage.startswith("sonnet"))
        opus_wall = sum(c.wall_seconds for c in r.calls if c.stage.startswith("opus"))
        total_tokens = sum(c.input_tokens + c.output_tokens for c in r.calls)
        lines.append(
            f"| {r.page} | {len(r.qa_v1)} | {len(r.qa_v2)} | "
            f"{sonnet_wall:.1f} | {opus_wall:.1f} | {total_tokens} |"
        )
    lines.append("")

    for r in results:
        lines.extend(
            [
                f"## Page {r.page}",
                "",
                "### Stage timings / token usage",
                "",
                "| Stage | Model | Wall (s) | Input tokens | Output tokens |",
                "| -- | -- | --: | --: | --: |",
            ]
        )
        for c in r.calls:
            lines.append(
                f"| {c.stage} | {c.model} | {c.wall_seconds} | "
                f"{c.input_tokens} | {c.output_tokens} |"
            )
        lines.append("")

        lines.append(f"### QA findings on synth_v1 ({len(r.qa_v1)} total)")
        lines.append("")
        if r.qa_v1:
            for f in r.qa_v1:
                lines.append(f"- `{f.code}` — {f.detail}")
        else:
            lines.append("_(none)_")
        lines.append("")

        if r.synth_v2 and r.qa_v1:
            lines.append(f"### QA findings on synth_v2 ({len(r.qa_v2)} total)")
            lines.append("")
            if r.qa_v2:
                for f in r.qa_v2:
                    lines.append(f"- `{f.code}` — {f.detail}")
            else:
                lines.append("_(none — repair pass cleared all findings)_")
            lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_memory_candidates(results: list[PageResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# S5U-776 — memory-update candidates",
        "",
        "Reviewer to triage. Promote accepted entries into the project's",
        "translation glossary / phrase memory after human spot review.",
        "",
        "## Glossary (current canonical renderings, baseline for review)",
        "",
    ]
    for entry in GLOSSARY:
        suffix = f"  _(note: {entry.note})_" if entry.note else ""
        lines.append(f"- **{entry.en}** → {entry.ru}{suffix}")
    lines.extend(["", "## Forbidden phrases (currently enforced)", ""])
    for phrase in FORBIDDEN_PHRASES:
        lines.append(f"- `{phrase}`")
    lines.extend(["", "## Bad → Good phrase rewrites (used as few-shot examples)", ""])
    for ex in BAD_GOOD_EXAMPLES:
        lines.extend(
            [
                f"- EN: _{ex.en}_",
                f"  - BAD: `{ex.bad_ru}`",
                f"  - GOOD: `{ex.good_ru}`",
                f"  - WHY: {ex.why}",
            ]
        )
    lines.extend(
        [
            "",
            "## Per-page memory candidates",
            "",
            "_Reviewer: scan the v1 / v2 RU drafts for new phrase renderings",
            "that should be promoted to phrase memory, and for any newly_",
            "_observed bad outputs that should be added to forbidden phrases._",
            "",
        ]
    )
    for r in results:
        lines.extend([f"### Page {r.page}", ""])
        if r.qa_v1:
            lines.append("v1 findings to feed back into rules:")
            for f in r.qa_v1:
                lines.append(f"- `{f.code}` — {f.detail}")
        else:
            lines.append("_(no v1 QA findings)_")
        lines.append("")

    (out_dir / "memory-candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
