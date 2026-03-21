---
description: Extraction work rules — applies to extraction-related pipeline code
globs: apps/pipeline/src/pipeline/extraction/**,apps/pipeline/tests/**/test_extract*
---

- All extraction issues (S5U-191 epic, S5U-274 evaluation track) follow `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`
- Read the playbook before starting any extraction ticket
- Strict sequencing — do not start an issue until all its blockers are Done
- Fixtures mandatory for every extraction change
- Golden refreshes must be in separate commits with before/after metric diffs
- Threshold loosening requires justification
- Use `docs/EXTRACTION_TICKET_TEMPLATE.md` as checklist for new extraction issues
