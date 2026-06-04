"""Shared blocking-QA release gate for the publish/export paths (S5U-870).

Three paths build a web bundle and historically disagreed on QA enforcement:
``atr release`` gated via :func:`cli.commands.release._check_qa_gate`, while
``PublishStage`` and ``make export`` exported regardless of blocking findings.
This module is the single source of truth for the gate decision that the two
previously-ungated paths now share.

Fail-closed contract (`.claude/rules/guards.md` Rule G1): the gate refuses by
default and treats every degenerate input — a missing QA summary when a
decision is required, a blocking summary whose records cannot be loaded — as a
refusal, never as "pass by absent state". The single explicit escape hatch is
``review_only=True``, which must originate from a reviewer-visible CLI flag and
never from an ambient env var (an env-only toggle that flips the default is
itself a G1 violation).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1


class QAGateError(Exception):
    """Raised when blocking QA findings refuse a publish/export (default mode).

    The message names the blocking codes and pages so an operator can see
    exactly what to fix or waive. ``review_only=True`` converts the refusal
    into a loudly-labeled draft instead of raising.
    """


class QAGateResult(BaseModel):
    """Outcome of a QA gate evaluation.

    Returned only when the gate does *not* raise — i.e. the run is
    non-blocking, or it is blocking but ``review_only`` was explicitly set.
    """

    blocking: bool = False
    review_only: bool = False
    blocking_codes: list[str] = Field(default_factory=list)
    blocking_pages: list[str] = Field(default_factory=list)
    review_pack_ref: str = ""

    @property
    def is_draft(self) -> bool:
        """True when this bundle is a review-only draft built over blocking QA."""
        return self.blocking and self.review_only


def _blocking_records(records: list[QARecordV1], block_on: set[str]) -> list[QARecordV1]:
    """Records whose severity is in ``block_on`` and which are not waived.

    Mirrors the predicate used by ``QAStage`` to compute
    ``QASummaryV1.blocking`` (``severity in block_on and not r.waived``) so
    waiver semantics are preserved identically across all three paths.
    """
    return [r for r in records if r.severity.value in block_on and not r.waived]


def _summarize_blocking(
    records: list[QARecordV1], block_on: set[str]
) -> tuple[list[str], list[str]]:
    """Return (sorted unique blocking codes, sorted unique blocking pages)."""
    blocking = _blocking_records(records, block_on)
    codes = sorted({r.code for r in blocking if r.code})
    pages = sorted({r.page_id for r in blocking if r.page_id})
    return codes, pages


def _refusal_message(
    *,
    context: str,
    run_id: str,
    codes: list[str],
    pages: list[str],
) -> str:
    """Build the operator-facing refusal naming blocking codes/pages."""
    if codes or pages:
        codes_str = ", ".join(codes) if codes else "<none resolved>"
        pages_str = ", ".join(pages) if pages else "<no page ids>"
        detail = f"blocking codes: [{codes_str}]; pages: [{pages_str}]"
    else:
        # summary.blocking is True but no records resolved — still refuse
        # (G1: never pass by absent state). Name the degraded state explicitly.
        detail = (
            "QA summary reports blocking findings but the individual QA records "
            "could not be loaded to name them (record artifacts missing)"
        )
    return (
        f"{context} refused: blocking QA findings for run {run_id!r}. "
        f"{detail}. Fix or waive the findings, or pass --review-only to build a "
        f"clearly-marked draft bundle for human review."
    )


def evaluate_qa_gate(
    *,
    context: str,
    summary: QASummaryV1 | None,
    records: list[QARecordV1],
    block_on: set[str],
    review_only: bool,
    run_id: str = "",
) -> QAGateResult:
    """Decide whether a publish/export may proceed.

    Args:
        context: Human-readable name of the calling path (e.g. ``"Publish"``,
            ``"Export"``) used in the refusal message.
        summary: The resolved run's QA summary, or ``None`` when it could not
            be resolved while a gate decision is required.
        records: The QA records referenced by ``summary`` (for naming blocking
            codes/pages). May be empty if records could not be loaded.
        block_on: Severities that block publishing (e.g. ``{"error",
            "critical"}``), taken from ``QAConfig.block_publish_on``.
        review_only: Explicit escape hatch from a reviewer-visible CLI flag. A
            blocking run proceeds as a loudly-labeled draft when this is True.
        run_id: Run id for the refusal message.

    Returns:
        A :class:`QAGateResult` when the gate allows (non-blocking) or defers to
        review-only.

    Raises:
        QAGateError: when blocking QA findings refuse the build and
            ``review_only`` is False, OR when ``summary is None`` (fail-closed:
            a gate decision was required but no QA summary was resolvable).
    """
    resolved_run_id = run_id or (summary.run_id if summary else "")

    if summary is None:
        # G1 fail-closed: a decision was required but the QA summary could not
        # be resolved. Do NOT pass by absent state. review_only does not rescue
        # an unverifiable run — the operator must run QA first.
        msg = (
            f"{context} refused: no QA summary could be resolved for run "
            f"{resolved_run_id or '<unknown>'!r}; cannot verify the QA gate. "
            f"Run the QA stage before publishing/exporting (failing closed)."
        )
        raise QAGateError(msg)

    if not summary.blocking:
        return QAGateResult(
            blocking=False,
            review_only=review_only,
            review_pack_ref=summary.review_pack_ref,
        )

    codes, pages = _summarize_blocking(records, block_on)

    if not review_only:
        raise QAGateError(
            _refusal_message(
                context=context,
                run_id=resolved_run_id,
                codes=codes,
                pages=pages,
            )
        )

    return QAGateResult(
        blocking=True,
        review_only=True,
        blocking_codes=codes,
        blocking_pages=pages,
        review_pack_ref=summary.review_pack_ref,
    )
