"""Markdown report writer for the S5U-803 DOCX rollout."""

from __future__ import annotations

from pathlib import Path

from .improved_rerun_core import REPO_ROOT, CodexOptions, PageRun


def write_report(
    result: PageRun,
    out_dir: Path,
    options: CodexOptions,
    source_path: Path,
    style_reference_path: Path | None,
) -> None:
    wall = sum(call.wall_seconds for call in result.calls)
    tokens = sum(call.input_tokens + call.output_tokens for call in result.calls)
    repaired = ", ".join(result.repaired_ids) or "none"
    lines = [
        "# S5U-803 — stabilized DOCX translation rollout",
        "",
        f"Output folder: `{out_dir.relative_to(REPO_ROOT)}`",
        f"Source: `{source_path}`",
        f"Model: `{options.model}` with Codex reasoning effort `{options.reasoning_effort}`",
        (
            f"Style reference: `{style_reference_path}`"
            if style_reference_path
            else "Style reference: none"
        ),
        "",
        "Workflow: DOCX extracted source -> 3 Codex translation variants -> "
        "Codex synthesis -> deterministic QA/style QA -> Codex editor -> "
        "Codex JSON style critic -> targeted paragraph repair -> final QA.",
        "",
        "| QA v1 | QA editor | Critic findings | Repaired paragraphs | "
        "QA final | Wall (s) | Tokens |",
        "| --: | --: | --: | -- | --: | --: | --: |",
        f"| {len(result.qa_v1)} | {len(result.qa_editor)} | {result.critic_findings} | "
        f"{repaired} | {len(result.qa_final)} | {wall:.1f} | {tokens} |",
        "",
        "## Stage timings",
        "",
        "| Stage | Model | Wall (s) | Input tokens | Output tokens |",
        "| -- | -- | --: | --: | --: |",
    ]
    for call in result.calls:
        lines.append(
            f"| {call.stage} | {call.model} | {call.wall_seconds} | "
            f"{call.input_tokens} | {call.output_tokens} |"
        )
    lines.extend(["", "## Artifacts", ""])
    lines.extend(
        [
            "- `inputs/source-en-clean.txt` — copied extracted DOCX text.",
            "- `variants/{literal-fidelity,literary-prose,idiomatic-natural}.txt` "
            "— Codex variants.",
            "- `synthesis/synth-v1.txt` — synthesized draft.",
            "- `editor/editor.txt` — editor pass before critic.",
            "- `final/synth-v2.txt` — post-repair final translation.",
            "- `qa/qa-{v1,editor,final}.json` — deterministic QA/style findings.",
            "- `critic/critic.json` — Codex style critic output.",
            "- `repair/repair-report.json` — targeted repair report.",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
