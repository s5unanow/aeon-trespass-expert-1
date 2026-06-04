#!/usr/bin/env python3
"""Read-only analytics aggregator -> ``artifacts/analytics/latest.json``.

Consolidates scattered project-health signals into one typed JSON artifact an
agent or dashboard can read in a single fetch:

* Run health      — recent runs, status counts, stage durations (var/registry.db)
* QA health       — blocking counts, clean-page rate, severity/layer/code
                    distribution (latest qa_metrics.json)
* Code erosion    — structural erosion / verbosity drift (code-erosion-review.json)
* Agent throughput— shipped/attempted + failed branches (run-issues-*.log)
* Network signals — best-effort git stale-branch + gh CI status (offline-safe)

Usage::

    python scripts/analytics_snapshot.py [--document-id ato_core_v1_1]
        [--registry var/registry.db] [--artifact-root artifacts]
        [--output artifacts/analytics/latest.json] [--print]

Design constraints (S5U-873):

* **Pure read-only.** The registry is opened ``mode=ro``; no artifact or DB
  row is ever mutated.
* **Offline-safe.** git/gh signals are best-effort; their failure marks only
  that field unavailable and never aborts the snapshot.
* **Fail-closed on core signals.** If run-health or QA-health is *degraded*
  (registry unreadable / schema mismatch, qa_metrics malformed) the snapshot
  is still written (clearly marked ``available=False`` + ``degraded=True``)
  **and** the process exits non-zero, so a degraded snapshot can never
  masquerade as a healthy empty success.
* Atomic write via ``atomic_write_text``; this file stays under the 400-line
  gate by delegating the source readers to ``_analytics_sources``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from _analytics_network import NetworkSignals, read_network_signals
from _analytics_sources import (
    AgentThroughput,
    CodeErosion,
    QAHealth,
    RunHealth,
    find_latest_qa_metrics,
    find_latest_run_issues_log,
    now_iso,
    read_agent_throughput,
    read_code_erosion,
    read_qa_health,
    read_run_health,
)
from pydantic import BaseModel, Field

logger = logging.getLogger("atr.analytics_snapshot")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT_ID = "ato_core_v1_1"
DEFAULT_REGISTRY = REPO_ROOT / "var" / "registry.db"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "analytics" / "latest.json"
DEFAULT_EROSION_REVIEW = REPO_ROOT / "artifacts" / "code-erosion-review.json"

SCHEMA_VERSION = "analytics_snapshot.v1"


class AnalyticsSnapshot(BaseModel):
    """Typed aggregate of project-health signals.

    ``degraded`` is the single fail-closed flag the caller keys its exit code
    on: it is True iff a *core* signal (run health or QA health) reported an
    error. Best-effort network signals never set ``degraded``.
    """

    schema_version: str = SCHEMA_VERSION
    generated_at: str
    document_id: str
    degraded: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)
    run_health: RunHealth
    qa_health: QAHealth
    code_erosion: CodeErosion
    agent_throughput: AgentThroughput
    network: NetworkSignals


def build_snapshot(
    *,
    document_id: str,
    registry_path: Path,
    artifact_root: Path,
    erosion_review_path: Path,
    repo_root: Path,
    include_network: bool,
) -> AnalyticsSnapshot:
    """Assemble the snapshot from the read-only source readers."""
    run_health = read_run_health(registry_path)
    qa_metrics_path = find_latest_qa_metrics(artifact_root, document_id)
    qa_health = read_qa_health(qa_metrics_path)
    code_erosion = read_code_erosion(erosion_review_path)
    throughput = read_agent_throughput(find_latest_run_issues_log(artifact_root))
    network = read_network_signals(repo_root) if include_network else NetworkSignals()

    degraded_reasons = _core_degradation_reasons(run_health, qa_health)
    return AnalyticsSnapshot(
        generated_at=now_iso(),
        document_id=document_id,
        degraded=bool(degraded_reasons),
        degraded_reasons=degraded_reasons,
        run_health=run_health,
        qa_health=qa_health,
        code_erosion=code_erosion,
        agent_throughput=throughput,
        network=network,
    )


def _core_degradation_reasons(run_health: RunHealth, qa_health: QAHealth) -> list[str]:
    """Collect fail-closed reasons from the two core signals.

    A core signal is degraded only when it carries an ``error`` (registry
    unreadable / schema mismatch, qa_metrics malformed). A benign "no data
    yet" state (missing qa_metrics, fresh registry with zero runs) carries no
    error and is *not* degraded.
    """
    reasons: list[str] = []
    if run_health.error:
        reasons.append(f"run_health: {run_health.error}")
    if qa_health.error:
        reasons.append(f"qa_health: {qa_health.error}")
    return reasons


def _write_snapshot(snapshot: AnalyticsSnapshot, output_path: Path) -> None:
    # Import here so the module imports cleanly even if run from a checkout
    # where the pipeline package path is added late (parametrized in tests).
    from atr_pipeline.store.atomic_write import atomic_write_text

    payload = snapshot.model_dump_json(indent=2)
    atomic_write_text(output_path, payload + "\n")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate run/QA/erosion/throughput signals into one JSON."
    )
    parser.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--erosion-review", type=Path, default=DEFAULT_EROSION_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Skip best-effort git/gh signals (forces offline mode).",
    )
    parser.add_argument(
        "--print",
        dest="print_stdout",
        action="store_true",
        help="Also print the snapshot JSON to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)

    snapshot = build_snapshot(
        document_id=args.document_id,
        registry_path=args.registry,
        artifact_root=args.artifact_root,
        erosion_review_path=args.erosion_review,
        repo_root=REPO_ROOT,
        include_network=not args.no_network,
    )

    _write_snapshot(snapshot, args.output)

    # Intended stdout output of the CLI (not a diagnostic) — print is fine.
    if args.print_stdout:
        print(snapshot.model_dump_json(indent=2))
    logger.info("analytics snapshot written to %s", args.output)

    if snapshot.degraded:
        for reason in snapshot.degraded_reasons:
            logger.error("degraded core signal -> %s", reason)
        logger.error(
            "snapshot is DEGRADED (written, but marked degraded=True); exiting non-zero "
            "so it cannot be mistaken for a healthy success"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
