#!/usr/bin/env python3
"""Non-blocking code erosion / verbosity drift report for main...HEAD.

Reports structural erosion, verbosity drift, hotspot ratchet, and budget
violations.  Complexity counting approximates ruff C901 via ast.
Advisory only — always exits 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

from _hotspot_budgets import (
    BudgetViolation,
    HotspotConfig,
    HotspotEntry,
    check_budgets,
    compute_ratchet,
    load_hotspot_config,
)

THRESHOLDS = {"complexity": 12, "branches": 12, "statements": 50, "args": 7}

PYTHON_DIRS = ("apps/pipeline/src", "packages/schemas/python", "scripts")
GROWTH_ABS = 50
GROWTH_PCT = 25.0


class FunctionMetrics(TypedDict):
    name: str
    line: int
    complexity: int
    branches: int
    statements: int
    args: int


class FunctionViolation(TypedDict):
    file: str
    function: str
    line: int
    complexity: int
    branches: int
    statements: int
    violations: list[str]


class GrowthEntry(TypedDict):
    file: str
    lines_base: int
    lines_head: int
    delta: int
    pct_growth: float


# -- AST analysis -------------------------------------------------------------
_BRANCH_TYPES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
)


def _count_branches(node: ast.AST) -> int:
    count = 0
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(child, _BRANCH_TYPES):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            count += 1 + len(child.ifs)
        stack.extend(ast.iter_child_nodes(child))
    return count


def analyze_source(source: str) -> list[FunctionMetrics]:
    """Parse *source* and return per-function metrics."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    results: list[FunctionMetrics] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        branches = _count_branches(node)
        end = getattr(node, "end_lineno", None) or node.lineno
        nargs = (
            len(node.args.posonlyargs)
            + len(node.args.args)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )
        results.append(
            FunctionMetrics(
                name=node.name,
                line=node.lineno,
                complexity=1 + branches,
                branches=branches,
                statements=end - node.lineno + 1,
                args=nargs,
            )
        )
    return results


# -- Git helpers ---------------------------------------------------------------


def get_changed_files(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            capture_output=True,
            text=True,
            check=False,
        )
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def get_file_at_ref(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


# -- Metric computation --------------------------------------------------------


def _in_scope(path: str) -> bool:
    return path.endswith(".py") and any(path.startswith(d) for d in PYTHON_DIRS)


def _violations_for(m: FunctionMetrics) -> list[str]:
    v: list[str] = []
    if m["complexity"] > THRESHOLDS["complexity"]:
        v.append("C901")
    if m["branches"] > THRESHOLDS["branches"]:
        v.append("PLR0912")
    if m["statements"] > THRESHOLDS["statements"]:
        v.append("PLR0915")
    if m["args"] > THRESHOLDS["args"]:
        v.append("PLR0913")
    return v


def compute_structural_erosion(
    changed: list[str], head: str
) -> tuple[list[FunctionViolation], int]:
    funcs: list[FunctionViolation] = []
    score = 0
    for path in changed:
        if not _in_scope(path):
            continue
        source = get_file_at_ref(head, path)
        if source is None:
            continue
        for m in analyze_source(source):
            vs = _violations_for(m)
            if not vs:
                continue
            over = sum(
                max(0, m[k] - THRESHOLDS[k])  # type: ignore[literal-required]
                for k in ("complexity", "branches", "statements", "args")
            )
            score += over
            funcs.append(
                FunctionViolation(
                    file=path,
                    function=m["name"],
                    line=m["line"],
                    complexity=m["complexity"],
                    branches=m["branches"],
                    statements=m["statements"],
                    violations=vs,
                )
            )
    funcs.sort(key=lambda f: -f["complexity"])
    return funcs, score


def compute_verbosity_drift(
    changed: list[str], base: str, head: str
) -> tuple[list[GrowthEntry], int, float]:
    growth: list[GrowthEntry] = []
    new_funcs: list[int] = []
    for path in changed:
        if not _in_scope(path):
            continue
        head_src = get_file_at_ref(head, path)
        if head_src is None:
            continue
        head_lines = len(head_src.splitlines())
        base_src = get_file_at_ref(base, path)
        base_lines = len(base_src.splitlines()) if base_src else 0
        delta = head_lines - base_lines
        pct = (delta / base_lines * 100) if base_lines > 0 else 0.0
        if delta > GROWTH_ABS or pct > GROWTH_PCT:
            growth.append(
                GrowthEntry(
                    file=path,
                    lines_base=base_lines,
                    lines_head=head_lines,
                    delta=delta,
                    pct_growth=round(pct, 1),
                )
            )
        base_names = {m["name"] for m in analyze_source(base_src)} if base_src else set()
        for m in analyze_source(head_src):
            if m["name"] not in base_names:
                new_funcs.append(m["statements"])
    growth.sort(key=lambda g: -g["delta"])
    avg = round(sum(new_funcs) / len(new_funcs), 1) if new_funcs else 0.0
    return growth, len(new_funcs), avg


def _gather_hotspot_metrics(
    config: HotspotConfig, base: str, head: str
) -> dict[str, tuple[int, int, int, int]]:
    """Gather (base_worst, head_worst, base_lines, head_lines) per hotspot."""
    result: dict[str, tuple[int, int, int, int]] = {}
    for hotspot in config["hotspots"]:
        path = hotspot["path"]
        base_src = get_file_at_ref(base, path)
        head_src = get_file_at_ref(head, path)
        bw = max((m["complexity"] for m in analyze_source(base_src or "")), default=0)
        hw = max((m["complexity"] for m in analyze_source(head_src or "")), default=0)
        bl = len(base_src.splitlines()) if base_src else 0
        hl = len(head_src.splitlines()) if head_src else 0
        result[path] = (bw, hw, bl, hl)
    return result


# -- Report formatting ---------------------------------------------------------


def build_report(
    base: str,
    head: str,
    changed: list[str],
    erosion: tuple[list[FunctionViolation], int],
    drift: tuple[list[GrowthEntry], int, float],
    ratchet: list[HotspotEntry],
    budget_violations: list[BudgetViolation],
) -> dict[str, object]:
    erosion_funcs, erosion_score = erosion
    growth, new_func_count, avg_new_func_len = drift
    return {
        "base": base,
        "head": head,
        "files_changed": len(changed),
        "files_in_scope": sum(1 for p in changed if _in_scope(p)),
        "structural_erosion": {
            "over_threshold_functions": erosion_funcs,
            "total_erosion_score": erosion_score,
        },
        "verbosity_drift": {
            "significant_growth": growth,
            "new_functions": new_func_count,
            "avg_new_function_length": avg_new_func_len,
        },
        "hotspot_ratchet": ratchet,
        "budget_violations": budget_violations,
    }


def print_report(report: dict[str, object]) -> None:
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

    print("\n---\nAdvisory only — does not block CI. Tracked by S5U-465.\n")


# -- CLI -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Non-blocking code erosion report.")
    parser.add_argument("--base", default="main", help="Base ref (default: main)")
    parser.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    parser.add_argument("--output-json", dest="output_json", help="Write JSON to file")
    args = parser.parse_args(argv)

    config = load_hotspot_config()
    changed = get_changed_files(args.base, args.head)
    erosion = compute_structural_erosion(changed, args.head)
    drift = compute_verbosity_drift(changed, args.base, args.head)

    metrics = _gather_hotspot_metrics(config, args.base, args.head)
    ratchet = compute_ratchet(config, metrics)
    head_metrics = {p: (hw, hl) for p, (_bw, hw, _bl, hl) in metrics.items()}
    budget_violations = check_budgets(changed, config, head_metrics=head_metrics)

    report = build_report(args.base, args.head, changed, erosion, drift, ratchet, budget_violations)
    print_report(report)

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"JSON report written to {args.output_json}")
    # Advisory only — change to `return 1 if budget_violations else 0` when
    # budget calibration is confirmed and blocking is desired.
    return 0


if __name__ == "__main__":
    sys.exit(main())
