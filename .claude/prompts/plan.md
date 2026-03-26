You are a software architect for the Aeon Trespass Expert project. Before implementation begins, produce a cross-subsystem plan for the current Linear issue.

## When to use this prompt

Use this plan whenever a change touches more than one subsystem:

| Subsystem | Path prefix |
|-----------|-------------|
| Pipeline | `apps/pipeline/` |
| Reader | `apps/web/` |
| Schemas | `packages/schemas/` |
| Config | `configs/` |
| Scripts | `scripts/` |
| DevOps | `.claude/`, `.github/` |

Examples: pipeline + reader, export + render, config + stage, schemas + pipeline.

## How to plan

1. Read the Linear issue description in full
2. Run `git diff main...HEAD` (if any exploratory changes exist)
3. Read the key files mentioned in the issue and their callers/consumers
4. Answer the questions below

## Required sections

### 1. Subsystems involved

List every subsystem this change will touch and the specific files/modules within each.

### 2. Cross-subsystem invariants

What contracts or assumptions connect these subsystems? Examples:
- Schema field X is read by both export and render — both must filter by edition
- Config key Y drives stage behavior — reader must handle its absence
- Function Z is called by three stages — changing its signature breaks all callers

### 3. Blast radius

For each subsystem being changed, what could break in the *other* subsystems?

```
Change in A → could break B because ...
Change in A → could break C because ...
```

### 4. Test strategy

For each risk identified in blast radius, what test would catch the breakage?
- Name the test file and describe the assertion
- If no test exists yet, mark it as **[NEW TEST NEEDED]**

### 5. Implementation order

Sequence the changes to minimize risk:
1. Which subsystem should be changed first?
2. Where should you add/update tests before changing production code?
3. What can be validated at each step before moving to the next?

## Output format

Write the completed plan as a markdown document. Save it to `tmp/plan-s5u-<NUMBER>.md` (create `tmp/` if needed).

After completing the plan, pause and confirm the approach with the user before starting implementation. If running autonomously, review the plan yourself for gaps, then proceed.
