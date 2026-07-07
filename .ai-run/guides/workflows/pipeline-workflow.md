# Extraction & Pipeline Workflow

Domain workflow for extraction-related pipeline changes. Full governance doc: `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`. Ticket checklist: `docs/EXTRACTION_TICKET_TEMPLATE.md`.

---

## Before Starting an Extraction Issue

Verify all `blockedBy` Linear relations are Done before starting (`.claude/rules/extraction.md`). The extraction subsystem was redesigned under epic S5U-191 with evaluation infrastructure under S5U-274 — that redesign is complete; current work is maintenance/enhancement against the rules in the playbook (`docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md:8-13`).

---

## Fixture Requirements by Change Type

| Change type | Required fixtures |
|-------------|-------------------|
| New schema (e.g. `PageEvidenceV1`) | Roundtrip fixture, ≥1 positive + 1 negative example per variant |
| New/modified extraction primitive | Golden page fixture, before/after, ≥1 page per affected layout class |
| Region graph / reading-order change | Golden fixture for multi-column, sidebar, full-width-interrupt |
| Symbol/asset resolution change | Golden fixture for an icon-dense page with known symbol set |
| Confidence scoring/routing change | Fixture per confidence band (primary, hard-route, QA-required, publish-blocking) |
| Evaluation metric/threshold change | Updated golden expectations with explicit before/after metric diff |

Full detail: `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` § 2.

---

## Golden Refresh Governance

Golden refreshes must ship in a separate commit from the code change, with a before/after metric diff. Threshold loosening requires explicit justification in the PR body — `check_golden_refresh.py` and `check_threshold_changes.py` gate this in CI when extraction scope is detected (`check_extraction_scope.py`).

---

## Pipeline Verification Commands

| Action | Command |
|--------|---------|
| Verify extraction invariants | `make verify` (`uv run atr verify-extraction --doc ato_core_v1_1`) |
| Verify cross-stage refs | `uv run atr verify-refs --doc ato_core_v1_1` |
| Export artifacts to web | `make export` |
| Export EN-only for review | `make export-en` |
| Validate fixture manifest | `make validate-fixtures` |

---

## Quick Reference

| Need | Location |
|------|----------|
| Full extraction playbook | `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` |
| Ticket checklist template | `docs/EXTRACTION_TICKET_TEMPLATE.md` |
| Review workflow | `docs/EXTRACTION_REVIEW_WORKFLOW.md` |
| Extraction path-rules | `.claude/rules/extraction.md` |
