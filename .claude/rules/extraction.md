---
description: Extraction work rules — applies to extraction-related pipeline code
globs: apps/pipeline/src/pipeline/extraction/**,apps/pipeline/tests/**/test_extract*
---

- All extraction work follows `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`
- Read the playbook before starting any extraction ticket
- Check Linear `blockedBy` relations before starting an issue
- Fixtures mandatory for every extraction change
- Golden refreshes must be in separate commits with before/after metric diffs
- Threshold loosening requires justification
- Use `docs/EXTRACTION_TICKET_TEMPLATE.md` as checklist for new extraction issues
