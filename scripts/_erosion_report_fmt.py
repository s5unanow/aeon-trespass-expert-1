"""Human-readable formatting for the code erosion report."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _hotspot_budgets import BudgetViolation
    from _repo_summary import RepoMetricsSnapshot
    from check_code_erosion import FunctionViolation, GrowthEntry


def _fmt_delta(val: int | float, d: int | float) -> str:
    sign = "+" if d >= 0 else ""
    return f"{val} ({sign}{d})"


def _print_repo_summary(summary: dict[str, object]) -> None:
    head: RepoMetricsSnapshot = summary["head"]  # type: ignore[assignment]
    delta: RepoMetricsSnapshot = summary["delta"]  # type: ignore[assignment]
    trend: str = summary["trend"]  # type: ignore[assignment]

    print(f"\n## Repo-Wide Summary  (trend: {trend})")
    print(f"  Functions: {_fmt_delta(head['total_functions'], delta['total_functions'])}")
    print(
        f"  Complexity (total): {_fmt_delta(head['total_complexity'], delta['total_complexity'])}"
    )
    print(f"  Complexity (mean): {_fmt_delta(head['mean_complexity'], delta['mean_complexity'])}")
    print(f"  Complexity (p90): {_fmt_delta(head['p90_complexity'], delta['p90_complexity'])}")
    print(f"  Lines: {_fmt_delta(head['total_lines'], delta['total_lines'])}")
    print(
        f"  Over C901 threshold: "
        f"{_fmt_delta(head['functions_over_threshold'], delta['functions_over_threshold'])}"
    )


def _print_budget_violations(report: dict[str, object]) -> None:
    violations: list[BudgetViolation] = report.get("budget_violations", [])  # type: ignore[assignment]
    print("\n## Budget Violations")
    if violations:
        for v in violations:
            waiver = f" (waiver: {v['waiver_issue']})" if v["waiver_active"] else ""
            print(
                f"  {Path(v['file']).name} ({v['tracking_issue']}):"
                f" {v['metric']} {v['current']} > budget {v['budget']}{waiver}"
            )
    else:
        print("  No budget violations in touched hotspots.")


def print_report(report: dict[str, object]) -> None:
    """Print human-readable erosion report to stdout."""
    erosion = report["structural_erosion"]
    drift = report["verbosity_drift"]
    ratchet = report["hotspot_ratchet"]
    assert isinstance(erosion, dict) and isinstance(drift, dict) and isinstance(ratchet, list)

    print(f"\nCode Erosion Report ({report['base']}...{report['head']})\n{'=' * 52}")
    print(f"\n  Files changed: {report['files_changed']}, in scope: {report['files_in_scope']}")

    funcs: list[FunctionViolation] = erosion["over_threshold_functions"]
    print(f"\n## Structural Erosion  (score: {erosion['total_erosion_score']})")
    if funcs:
        print(f"  Over-threshold functions: {len(funcs)}")
        for f in funcs:
            print(f"\n  {f['file']}\n    {f['function']} (line {f['line']})")
            print(
                f"      complexity={f['complexity']}  branches={f['branches']}"
                f"  stmts={f['statements']}  [{', '.join(f['violations'])}]"
            )
    else:
        print("  No over-threshold functions in changed files.")

    print("\n## Verbosity Drift")
    growth_list: list[GrowthEntry] = drift["significant_growth"]
    if growth_list:
        for g in growth_list:
            print(
                f"    {g['file']}: {g['lines_base']} -> {g['lines_head']}"
                f" (+{g['delta']}, {g['pct_growth']}%)"
            )
    else:
        print("  No significant file growth.")
    print(
        f"  New functions: {drift['new_functions']}"
        f", avg length: {drift['avg_new_function_length']} lines"
    )

    print("\n## Hotspot Ratchet")
    for h in ratchet:
        assert isinstance(h, dict)
        dc = h["head_worst_complexity"] - h["base_worst_complexity"]
        dl = h["head_lines"] - h["base_lines"]
        print(f"  {Path(h['file']).name} ({h['issue']}): {h['verdict']}")
        print(
            f"    complexity: {h['base_worst_complexity']}"
            f" -> {h['head_worst_complexity']} ({'+' if dc >= 0 else ''}{dc})"
        )
        print(f"    lines: {h['base_lines']} -> {h['head_lines']} ({'+' if dl >= 0 else ''}{dl})")
        if h["budget_complexity"] > 0 or h["budget_lines"] > 0:
            status = "EXCEEDED" if h["budget_exceeded"] else "within budget"
            waiver_note = ""
            if h["waiver_issue"]:
                waiver_note = f"  waiver={h['waiver_issue']} expires={h['waiver_expires']}"
            print(
                f"    budget: complexity<={h['budget_complexity']}"
                f"  lines<={h['budget_lines']}  [{status}]{waiver_note}"
            )

    _print_budget_violations(report)

    summary = report.get("repo_summary")
    if summary is not None:
        assert isinstance(summary, dict)
        _print_repo_summary(summary)

    print("\n---\nAdvisory only — does not block CI. Tracked by S5U-465.\n")
