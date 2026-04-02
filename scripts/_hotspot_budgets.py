"""Hotspot budget configuration, ratchet computation, and budget checking.

Loads the versioned watchlist from configs/qa/hotspot_budgets.toml, computes
ratchet verdicts, and checks touched hotspot files against their budgets.
"""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import TypedDict

_BUDGET_CONFIG_PATH = "configs/qa/hotspot_budgets.toml"


# -- Types ---------------------------------------------------------------------


class HotspotBudget(TypedDict):
    path: str
    tracking_issue: str
    max_complexity: int
    max_lines: int


class HotspotWaiver(TypedDict):
    path: str
    issue: str
    reason: str
    expires: date
    budget_override_complexity: int
    budget_override_lines: int


class HotspotConfig(TypedDict):
    version: int
    hotspots: list[HotspotBudget]
    waivers: list[HotspotWaiver]


class HotspotEntry(TypedDict):
    file: str
    issue: str
    verdict: str
    base_worst_complexity: int
    head_worst_complexity: int
    base_lines: int
    head_lines: int
    budget_complexity: int
    budget_lines: int
    budget_exceeded: bool
    waiver_issue: str
    waiver_expires: str


class BudgetViolation(TypedDict):
    file: str
    tracking_issue: str
    metric: str
    current: int
    budget: int
    waiver_issue: str
    waiver_active: bool


# -- Config loading ------------------------------------------------------------


def _find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for parent in [current, *current.parents]:
        if (parent / "configs").is_dir() and (parent / ".git").exists():
            return parent
    return current


def load_hotspot_config(repo_root: Path | None = None) -> HotspotConfig:
    """Load hotspot budget config from TOML."""
    root = repo_root or _find_repo_root()
    path = root / _BUDGET_CONFIG_PATH
    if not path.exists():
        return HotspotConfig(version=0, hotspots=[], waivers=[])
    with open(path, "rb") as f:
        data = tomllib.load(f)
    waivers: list[HotspotWaiver] = []
    for w in data.get("waivers", []):
        waivers.append(
            HotspotWaiver(
                path=w["path"],
                issue=w["issue"],
                reason=w["reason"],
                expires=w["expires"],
                budget_override_complexity=w.get("budget_override_complexity", 0),
                budget_override_lines=w.get("budget_override_lines", 0),
            )
        )
    return HotspotConfig(
        version=data.get("version", 1),
        hotspots=[
            HotspotBudget(
                path=h["path"],
                tracking_issue=h["tracking_issue"],
                max_complexity=h["max_complexity"],
                max_lines=h["max_lines"],
            )
            for h in data.get("hotspots", [])
        ],
        waivers=waivers,
    )


# -- Ratchet computation -------------------------------------------------------


def _active_waivers(config: HotspotConfig) -> dict[str, HotspotWaiver]:
    today = date.today()
    return {w["path"]: w for w in config["waivers"] if w["expires"] >= today}


def compute_ratchet(
    config: HotspotConfig,
    file_metrics: dict[str, tuple[int, int, int, int]],
) -> list[HotspotEntry]:
    """Compute ratchet verdicts for all hotspots.

    *file_metrics* maps path -> (base_worst, head_worst, base_lines, head_lines).
    Uses waiver-adjusted budgets for ``budget_exceeded`` so the ratchet and
    budget-violations sections stay consistent.
    """
    waivers = _active_waivers(config)
    entries: list[HotspotEntry] = []
    for hotspot in config["hotspots"]:
        path = hotspot["path"]
        base_worst, head_worst, base_lines, head_lines = file_metrics.get(path, (0, 0, 0, 0))
        if head_worst > base_worst or head_lines > base_lines:
            verdict = "WORSENED"
        elif head_worst < base_worst or head_lines < base_lines:
            verdict = "IMPROVED"
        else:
            verdict = "UNCHANGED"
        waiver = waivers.get(path)
        eff_c = (
            waiver["budget_override_complexity"]
            if waiver and waiver["budget_override_complexity"] > 0
            else hotspot["max_complexity"]
        )
        eff_l = (
            waiver["budget_override_lines"]
            if waiver and waiver["budget_override_lines"] > 0
            else hotspot["max_lines"]
        )
        exceeded = (eff_c > 0 and head_worst > eff_c) or (eff_l > 0 and head_lines > eff_l)
        entries.append(
            HotspotEntry(
                file=path,
                issue=hotspot["tracking_issue"],
                verdict=verdict,
                base_worst_complexity=base_worst,
                head_worst_complexity=head_worst,
                base_lines=base_lines,
                head_lines=head_lines,
                budget_complexity=eff_c,
                budget_lines=eff_l,
                budget_exceeded=exceeded,
                waiver_issue=waiver["issue"] if waiver else "",
                waiver_expires=str(waiver["expires"]) if waiver else "",
            )
        )
    return entries


# -- Budget checking -----------------------------------------------------------


def check_budgets(
    changed_files: list[str],
    config: HotspotConfig,
    *,
    head_metrics: dict[str, tuple[int, int]],
) -> list[BudgetViolation]:
    """Check hotspot files against their budgets.

    Only checks hotspot files that appear in *changed_files*.
    *head_metrics* maps file path -> (worst_complexity, line_count).
    """
    waivers = _active_waivers(config)
    changed_set = set(changed_files)
    violations: list[BudgetViolation] = []

    for hotspot in config["hotspots"]:
        path = hotspot["path"]
        if path not in changed_set:
            continue
        metrics = head_metrics.get(path)
        if metrics is None:
            continue
        head_worst, head_lines = metrics
        waiver = waivers.get(path)
        eff_complexity = (
            waiver["budget_override_complexity"]
            if waiver and waiver["budget_override_complexity"] > 0
            else hotspot["max_complexity"]
        )
        eff_lines = (
            waiver["budget_override_lines"]
            if waiver and waiver["budget_override_lines"] > 0
            else hotspot["max_lines"]
        )
        waiver_issue = waiver["issue"] if waiver else ""

        if hotspot["max_complexity"] > 0 and head_worst > eff_complexity:
            violations.append(
                BudgetViolation(
                    file=path,
                    tracking_issue=hotspot["tracking_issue"],
                    metric="complexity",
                    current=head_worst,
                    budget=eff_complexity,
                    waiver_issue=waiver_issue,
                    waiver_active=bool(waiver),
                )
            )
        if hotspot["max_lines"] > 0 and head_lines > eff_lines:
            violations.append(
                BudgetViolation(
                    file=path,
                    tracking_issue=hotspot["tracking_issue"],
                    metric="lines",
                    current=head_lines,
                    budget=eff_lines,
                    waiver_issue=waiver_issue,
                    waiver_active=bool(waiver),
                )
            )

    return violations
