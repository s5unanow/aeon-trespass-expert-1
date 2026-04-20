"""Rule D (required-check advisory) helpers for check_instruction_drift.py.

Extracted from the main scanner to keep both files under the 400-line limit.
Rule D is warning-only: it walks `.github/workflows/*.yml`, enumerates jobs,
and reports any job name/key that does not appear in CLAUDE.md § Quality
gates. It never changes exit code — the drift class this catches
(S5U-638 / S5U-653 / S5U-654) is a documentation/workflow-alignment problem
caught by reviewer attention, not a CI-blocking failure.

Degenerate inputs per `.claude/rules/guards.md` G1:
- Missing `.github/workflows/` → stderr warning; advisory skipped.
- Malformed YAML in a workflow → stderr warning naming the file + parse
  error; scanner continues on remaining files.
- Workflow with non-mapping top-level → stderr warning; skipped.
- Workflow missing `jobs:` key → silently skipped (legitimate: reusable-
  workflow callers).

Rule D is explicitly advisory (warning-only), so the G1 fail-closed
principle yields to the rule's own design constraint: changing exit code
would misrepresent warning-only semantics. The fail-closed discipline is
maintained by Rules A/B/C which run in the same scanner process.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOWS_DIR = Path(".github/workflows")


def gather_workflow_jobs(repo_root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Walk `.github/workflows/*.yml` and return (jobs, warnings).

    `jobs` is a list of (workflow_file_basename, job_key) tuples.
    `warnings` is a list of human-readable warning messages (malformed
    YAML, parse errors, missing directory). The function never raises —
    Rule D is advisory by design.
    """
    workflows_dir = repo_root / WORKFLOWS_DIR
    jobs: list[tuple[str, str]] = []
    warnings: list[str] = []
    if not workflows_dir.is_dir():
        warnings.append(
            f"Rule D: .github/workflows/ not found at {workflows_dir}; advisory skipped."
        )
        return jobs, warnings
    for wf_path in sorted(workflows_dir.glob("*.yml")):
        try:
            raw = wf_path.read_text(encoding="utf-8", errors="replace")
            data: Any = yaml.safe_load(raw)
        except (yaml.YAMLError, OSError) as exc:
            warnings.append(
                f"Rule D: failed to parse {wf_path.name}: {exc}. Skipping for advisory."
            )
            continue
        if not isinstance(data, dict):
            warnings.append(f"Rule D: {wf_path.name} top-level is not a mapping; skipping.")
            continue
        workflow_jobs = data.get("jobs")
        if not isinstance(workflow_jobs, dict):
            # No jobs key (e.g. reusable-workflow caller) — not an error.
            continue
        for job_key in workflow_jobs:
            if isinstance(job_key, str):
                jobs.append((wf_path.name, job_key))
    return jobs, warnings


def extract_quality_gates_section(text: str) -> str:
    """Return the Quality gates section of CLAUDE.md, or the full text if
    the heading isn't found. The advisory is loose by design; broader
    fallback scope keeps false-positives minimal."""
    m = re.search(
        r"##\s+Quality\s+gates\b(.+?)(?=\n##\s+|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m is None:
        return text
    return m.group(1)


def rule_d_advisory(
    repo_root: Path,
    claude_md_text: str,
) -> tuple[list[str], list[str]]:
    """Return (advisories, warnings) for Rule D. Never changes exit code.

    `advisories` are stdout-bound diagnostics naming workflow jobs absent
    from CLAUDE.md's Quality gates enumeration. `warnings` are stderr-
    bound (parse errors, missing directories).
    """
    jobs, warnings = gather_workflow_jobs(repo_root)
    advisories: list[str] = []
    section = extract_quality_gates_section(claude_md_text)
    for wf_name, job_key in jobs:
        wf_stem = wf_name[:-4] if wf_name.endswith(".yml") else wf_name
        # Loose match by design: either the workflow-file stem or the job
        # key appears somewhere in the Quality gates section.
        if wf_stem in section or job_key in section:
            continue
        advisories.append(
            f"Rule D: workflow job '{job_key}' (from {wf_name}) is not "
            "mentioned in CLAUDE.md § Quality gates."
        )
    return advisories, warnings
