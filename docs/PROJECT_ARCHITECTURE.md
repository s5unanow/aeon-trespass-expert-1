1. Executive recommendation

Do a full rewrite. Do not keep markdown at the center of the system.

Build an IR-first modular monolith in Python that treats the PDF as two evidence streams—native PDF objects and layout/OCR evidence—and fuses them into a typed, immutable page IR. Icons, figures, glossary concepts, source anchors, QA findings, and provenance must be first-class objects. Translation should run on structured block-level units with schema-constrained outputs, translation memory, and deterministic terminology enforcement. The frontend should be a static React application that renders typed nodes, not markdown. This is the best fit because it attacks your real failure modes at the root: icon loss, reading-order corruption, term drift, idempotency bugs, and manual QA sprawl.

The highest-leverage design choices are:

IR-first, not markdown-first. Markdown becomes an export/debug format only.

Dual-evidence extraction. PyMuPDF is the native truth source; Docling and a hard-page OCR/layout fallback provide structural evidence, not canonical text. PyMuPDF’s plain-text order can differ from natural reading order, while Docling and PaddleOCR add layout, reading order, and structured document signals.

First-class symbol system. Build a curated symbol catalog once, then recover inline icons via native image objects plus deterministic template matching.

Immutable artifacts + patch layers. Every stage output is versioned, content-addressed, validated, and never edited in place. Human corrections are checked in as typed patches.

Translate structure, not prose blobs. Use block-level structured outputs, translation memory, glossary concepts, and deterministic validators. Use LLMs where they add value; keep them out of extraction unless they are adjudicating bounded alternatives.

2. System requirements
Functional requirements

The rewritten system must:

ingest an original English Aeon Trespass PDF rulebook

extract text, structure, inline symbols, figures, captions, and page geometry

remove headers, footers, and furniture contamination

recover headings, lists, callouts, tables, and reading order

translate content into Russian

enforce consistent glossary/concept terminology

preserve icons and figure references as typed render objects

build a digital reader with navigation, glossary, search, and source-faithful presentation

produce QA reports, review packs, and publishable static artifacts

support deterministic reruns, partial replay, and page-scoped reprocessing

Non-functional requirements

The system must optimize for:

source fidelity

determinism where possible

reproducibility

idempotency

traceability to source page coordinates

low operational overhead

clean modular boundaries

schema-first interfaces

selective LLM use

low-maintenance normal operation

agent-friendly implementation

cost awareness

Key constraints

Personal-scale workload, not SaaS.

No microservice sprawl.

Minimal always-on infrastructure.

Static-hosting-friendly reader.

Hard pages must use selective fallbacks without hallucination-heavy extraction.

Manual review must be exception handling, not the main workflow.

Assumptions

I am making these assumptions and designing against them:

The source PDF is primarily a digital PDF, not a fully scanned book.

The inline game icon vocabulary is finite and reusable across pages.

You can tolerate a one-time curation step to build the symbol catalog and glossary concept registry.

The reader does not need to be a literal Russian re-typeset clone of the original PDF page geometry. It needs source-faithful structure, icon/figure fidelity, and a source-inspired visual system.

Distribution/legal rights for the translated rulebook are handled separately from the architecture.

GPU is optional. The system must run on CPU, with faster hard-page fallbacks if GPU is available.

3. Architecture options considered
Option A — Conservative evolution of the current markdown pipeline

Shape: Keep Python pipeline, keep markdown as canonical, improve extraction, normalization, and QA around it.

Pros

Fastest migration path.

Reuses current mental model and some existing code.

Lower short-term implementation cost.

Cons

Wrong substrate.

Icons stay as tokens or hacks.

Structure remains lossy.

Translation keeps operating on blobs instead of typed nodes.

Idempotency remains fragile because text mutation and cleanup order stay central.

Hard-page fallbacks still collapse into markdown, losing evidence traceability.

Operational complexity: Low.

Fit: Poor. This may reduce pain, but it will not solve the class of problems you listed.

Option B — IR-first modular monolith with typed stages (recommended)

Shape: Python modular monolith, immutable artifacts, typed schemas, page/block/inline IR, deterministic stage runner, static React reader.

Pros

Directly addresses all ten known problems.

Best traceability and replay story.

Supports selective hard-page routing without contaminating the main path.

Keeps ops boring.

Easy for coding agents: strict contracts, bounded packages, golden fixtures.

Cons

Higher initial design cost.

Requires a new canonical schema and migration mindset.

Forces discipline around patches, manifests, and schema versioning.

Operational complexity: Low to medium.

Fit: Excellent. This is the production-shaped architecture you want.

Option C — Workflow-orchestrated architecture with workers (Prefect/Dagster/Temporal style)

Shape: Separate orchestration layer, worker processes, queues, flow UI, task states.

Pros

Strong retry, state tracking, concurrency, and observability out of the box.

Good if this becomes multi-document, team-operated, or cloud-scheduled later.

Cons

Overhead for a personal-scale rules reader.

Adds another control plane before the core extraction/IR problems are actually solved.

Encourages infrastructure before data model correctness.

Prefect’s tasks are explicitly cacheable, retryable, stateful, and concurrent, which is useful—but those features are not your primary bottleneck right now.

Operational complexity: Medium to high.

Fit: Acceptable later, wrong now.

Primary recommendation

Choose Option B. Build the hard part once: typed evidence fusion, symbol anchoring, deterministic artifacts, and structured translation. That gives you the biggest quality jump with the lowest long-term maintenance cost.

4. Final recommended architecture
4.1 Main components
A. Source registry and document config

Registers each source PDF edition, fingerprints it, records page count, language, glossary profile, symbol catalog profile, and build configuration.

B. Immutable artifact store

Stores every validated stage output as an immutable artifact keyed by:

document id

stage name

scope (document, page, asset, batch)

schema version

pipeline version

config hash

input hash

C. Run registry

SQLite database that records runs, stage invocations, artifact refs, timings, metrics, QA summaries, and failure states.

D. Extractor ensemble

Runs:

native PDF extraction

page rasterization

layout analysis

OCR/layout fallback on hard pages

symbol/asset extraction

E. Evidence fusion + structure engine

Fuses raw evidence into canonical English PageIR:

reading order

block typing

section hints

figure/caption linkage

header/footer removal

inline icon anchoring

F. Glossary / concept registry

The canonical source of terminology, icon bindings, aliases, phrase templates, allowed target forms, and validation severity.

G. Translation subsystem

Builds translation jobs from source IR, runs structured model calls, validates outputs, applies terminology enforcement, and emits translated target IR.

H. Patch / override system

Stores typed, versioned patches for the unavoidable exceptions:

source extraction patch

target translation patch

asset binding patch

QA waiver

Artifacts are never edited manually. Patches are applied as deterministic inputs.

I. Render builder

Transforms target IR into static reader payloads:

page payloads

nav tree

glossary

search docs/index

asset manifest

release manifest

J. QA and review system

Runs layered QA and builds selective review packs for flagged pages only.

K. Static reader frontend

Typed renderer for blocks, inline icons, figures, glossary links, navigation, and search.

4.2 Architectural stance

This architecture is deliberately not a server-rendered document CMS, not an OCR microservice mesh, and not a smarter markdown generator.

It is a document compiler:

input: source PDF + config + glossary + symbol catalog + optional patches

output: versioned static digital edition + QA evidence

That is the correct mental model.

4.3 Interactions and stage boundaries

Document-scoped stages: ingest, furniture detection, section tree build, glossary build, search build, publish

Page-scoped stages: native extract, layout evidence, symbol detection, structure recovery, translation, page QA

Batch-scoped stages: translation calls, visual regression baselines

Asset-scoped stages: figure extraction, image optimization, sprite generation

Each stage:

reads immutable upstream artifacts

validates inputs

writes a new immutable output

emits metrics/events

never mutates prior artifacts

4.4 Data flow

Register source PDF and render page images.

Extract native PDF text/image/font evidence.

Extract layout evidence and classify page difficulty.

Detect repeated furniture and strip it from content zones.

Extract/match inline symbols and figures.

Recover canonical English PageIR.

Build translation jobs from translatable blocks.

Translate with structured outputs.

Enforce terminology/style; emit Russian PageIR.

Build reader payloads, glossary, nav, and search.

Run QA and visual regression.

Publish static edition if all blocking gates pass.

4.5 Control flow

Runner builds a plan first.

For each stage, it computes scope-local cache keys.

Page tasks run in parallel.

Aggregate stages wait on all required upstream scopes.

If a page fails, the run continues for other pages but the document is marked degraded.

Publish is blocked until all blocking QA failures are resolved or waived.

4.6 Failure / retry model
Deterministic stages

Examples: ingest, native extract, furniture detection, symbol matching, render build.

Retry only on transient I/O/process failure.

No semantic retry loop.

If validation fails, mark the artifact invalid and stop that scope.

Non-deterministic stages

Examples: translation, optional structure adjudication.

Use temperature=0.

Require strict structured output.

Retry once with a repair prompt if schema/validation fails.

Retry failed segments only, never whole documents.

Escalate to secondary provider only for failed scopes.

Persist both raw model response and validated normalized output.

4.7 Idempotency model

Idempotency is a first-class property.

For every stage invocation:

cache_key = hash(stage_name + stage_impl_version + schema_version + config_hash + input_artifact_hashes + patch_hashes + provider/model/prompt_version if applicable)

Rules:

Outputs are written to temp paths and atomically committed.

Re-running a stage with the same cache key returns the same artifact ref.

Patches participate in the key, so fixes are reproducible.

No cleanup stage ever rewrites upstream files.

“Latest successful build” is only a pointer/ref, never the actual storage location.

This eliminates the duplicate-token / stale-icon class of bugs.

4.8 Versioning model

Track four separate versions:

Schema version
page_ir.v1, render_page.v1, qa_record.v1

Pipeline version
2.0.0

Prompt/profile version
translate_rules_ru.v1

Content version
hash of canonical translated IR + asset refs + glossary version

Do not collapse these into one number.

4.9 Caching / checkpoint model

Artifact cache: immutable stage outputs

Translation memory: exact-match source block hash -> approved target block

LLM raw response cache: request hash -> validated structured response

Prompt caching: keep long stable prompt prefixes to exploit provider-side cache hits; both OpenAI and Anthropic document prompt caching benefits.

4.10 Mermaid diagrams
System context / containers

flowchart LR
    A[Source PDF] --> B[Python Pipeline Runner]
    B --> C[(Artifact Store)]
    B --> D[(SQLite Run Registry)]
    B --> E[LLM Provider Adapter]
    C --> F[Render Builder]
    F --> G[Static Reader Build]
    G --> H[Published Static Edition]
    C --> I[QA Engine]
    I --> J[Review Pack / Patch Files]
    J --> B
    H --> K[Reader Browser]

Pipeline / processing flow
flowchart TD
    A[ingest] --> B[native PDF extract]
    A --> C[page rasterize]
    B --> D[layout evidence]
    C --> D
    B --> E[symbol + asset detection]
    D --> F[furniture detection]
    E --> G[structure recovery]
    F --> G
    G --> H[source PageIR EN]
    H --> I[translation planning]
    I --> J[structured translation]
    J --> K[terminology + style enforcement]
    K --> L[target PageIR RU]
    L --> M[render model build]
    M --> N[search/nav/glossary build]
    N --> O[static site build]
    O --> P[QA + visual regression]
    P --> Q[publish]

Major data artifacts
flowchart LR
    A[source.pdf] --> B[source_manifest.json]
    A --> C[native_pages/*.json]
    A --> D[page_renders/*.png]
    C --> E[layout_pages/*.json]
    D --> E
    C --> F[symbol_matches/*.json]
    E --> G[page_ir.en/*.json]
    F --> G
    G --> H[translation_jobs/*.jsonl]
    H --> I[page_ir.ru/*.json]
    G --> J[assets/*.json]
    I --> K[render_pages/*.json]
    J --> K
    K --> L[search_index.json]
    K --> M[glossary.json]
    K --> N[nav.json]
    K --> O[dist/]
    I --> P[qa_reports/*.json]
    O --> Q[release_manifest.json]

5. Core architectural principles

IR-first design
Canonical state is typed JSON artifacts, not markdown, HTML, or LLM prose.

Markdown is a render/export target only
Keep optional markdown export for debugging, diffs, and external use. Never use it as the source of truth.

Text, icons, figures, and layout anchors are distinct node types
An inline icon is not a token string. A figure is not just an image path. A heading is not just bold text.

Native PDF evidence beats OCR when available
OCR exists to fill gaps and validate difficult pages, not to replace digital PDF text extraction.

Use multiple evidence sources, then fuse
Do not trust any single extractor on all pages.

Pure stages where possible
Deterministic stages take validated input artifacts and emit validated output artifacts with no side effects beyond logs/metrics.

Immutable artifacts, mutable refs
Outputs are immutable; only refs such as latest-success move.

Patches are data
Human fixes are committed as typed patches and become replayable inputs.

Contract-first interfaces
Persisted artifacts are schema-versioned; internal APIs consume/produce explicit models.

Deterministic QA gates
Publish is blocked by machine-enforced criteria, not “looks okay”.

Selective LLM usage
Use LLMs for translation and bounded adjudication. Do not use them as unconstrained extractors.

Every rendered node is traceable to source evidence
Every translated block should be explainable in terms of source page ids, source block ids, and evidence refs.

Pydantic discriminated unions are a good fit here because they are explicitly recommended as more predictable and performant than untagged unions for complex typed variants.

6. Technology stack recommendation
Backend language / core framework

Choose: Python 3.12, no always-on web backend in v1, package the system as a Python library plus Typer CLI.

Why

Python has the strongest practical ecosystem for PDF handling, OCR, layout tooling, and LLM integrations.

Typer gives you type-hint-based CLIs and clean subcommands, which is exactly what a stage runner wants.

Rejected

FastAPI as the core backend: wrong center of gravity; this is a compiler pipeline, not an API service.

Node-only backend: weaker PDF/doc tooling for this workload.

Workflow / orchestration

Choose: Custom in-process stage runner with manifests and scope-aware caching.

Why

Lowest ops.

Strongest control over artifact keys, replay, and validation.

Easier for agents to reason about than a hidden orchestrator state machine.

Rejected

Prefect/Dagster/Temporal in v1: useful later, unnecessary now. Prefect’s cache/retry/state model is real, but it is infrastructure you do not need until the core IR is solved.

Storage

Choose:

filesystem for immutable artifacts

SQLite for run/event registry and small operational metadata

JSON for nested IR artifacts

Parquet for wide metrics/evidence tables

DuckDB for QA analytics and diff tooling

Why

SQLite now has JSON support built in by default. DuckDB reads and writes Parquet efficiently and supports projection/predicate pushdown, which is ideal for fast local QA queries over page metrics and evidence tables.

Rejected

Postgres: overkill for personal-scale immutable artifacts.

MongoDB/document store: worse for reproducible file-based diffs and commits.

One giant JSONL datastore: too coarse for replay and page-scoped debugging.

Environment / packaging

Choose: uv for Python dependency/project management, pnpm for frontend workspace, Docker for reproducible CI/runtime image.

Why

uv gives you a universal lockfile and workspace/project management with low friction.

Rejected

Poetry/Pip-tools stack: more moving pieces for no gain here.

Schema / validation

Choose: Pydantic v2 models + generated JSON Schema + jsonschema validation in CI.

Why

Strong Python ergonomics, discriminated unions, and schema export.

JSON Schema becomes the contract shared with frontend and test fixtures. Pydantic explicitly recommends discriminated unions for predictability; jsonschema gives standards-based validation of serialized artifacts.

Rejected

msgspec as the primary model layer: faster, but weaker for the schema-first developer experience you need.

ad hoc dataclasses: insufficient runtime validation.

PDF / layout extraction

Choose:

PyMuPDF as the native extractor

Docling as the structured layout/document evidence engine

PaddleOCR layout/OCR as the hard-page fallback

Tesseract as tertiary OCR fallback for structured hOCR/ALTO evidence

OpenCV template matching for symbol anchoring

Why

PyMuPDF exposes words, blocks, images, and coordinates, but its plain text order can follow creator order instead of natural reading order; that is exactly why it should be the low-level evidence layer, not the final structure layer.

Docling adds advanced PDF understanding, reading order, tables, and a unified lossless JSON-ish document representation.

PaddleOCR’s layout module explicitly detects document elements and sorts them into reading order with a pointer network, which makes it the right hard-page fallback for multi-column and complex regions.

Tesseract remains valuable as a deterministic tertiary OCR layer because it can emit hOCR, ALTO, PAGE, TSV, and plain text.

Rejected

Docling-only extraction: not enough low-level control and traceability.

PyMuPDF-only extraction: insufficient on multi-column and stylized pages.

Surya as primary: I would avoid introducing a GPL-3 primary dependency when Docling/Paddle/Tesseract cover the use case.

LLM providers / models by task

Choose:

Primary translation provider: OpenAI Responses API with gpt-5.4

Hard-segment repair / arbitration: gpt-5.4-pro

Secondary provider adapter: Anthropic native API with claude-sonnet-4-6 and claude-opus-4-6

Why

OpenAI’s Structured Outputs are designed to adhere to developer-supplied JSON Schema, and Responses is the recommended API for new projects. GPT-5.4 is the documented default model for complex professional/document-heavy workflows, while GPT-5.4 Pro is the deeper-reasoning escalation path.

Anthropic also supports guaranteed structured outputs and current Claude 4.6 models, with Sonnet 4.6 positioned as the speed/intelligence balance and Opus 4.6 as the complex-task tier. Anthropic also documents prompt caching and automatic caching support.

Rejected

Free-form markdown prompts to any provider: unacceptable.

Single-provider lock-in without adapter: avoidable strategic risk.

Gemini in the critical path for v1: I would keep it as an evaluation adapter, not the default production path.

Russian language tooling

Choose: pymorphy3 for morphology/inflection validation and lemma handling.

Why

It is the maintained continuation of pymorphy2 and provides Russian inflection/morphology under MIT.

Rejected

Pure prompt-only inflection control: too opaque.

Full Russian NLP stack as core dependency: too heavy for your needs.

Frontend

Choose: React + TypeScript + Vite + React Router + CSS Modules.

Why

Static-hosting-friendly.

Strong ecosystem.

Simple build story.

No server requirement.

Rejected

Next.js / SSR-first stack: unnecessary complexity.

Markdown renderers: wrong render substrate.

Search

Choose: Precomputed normalized search documents + MiniSearch in the browser.

Why

MiniSearch is explicitly designed to run comfortably in the browser. Your corpus is small enough that client-side search is a feature, not a liability.

This preserves the IR-first design. Search indexes your typed content, not your generated HTML.

Rejected

Pagefind as primary: good static search tool, and it supports multilingual post-build indexing, but it expects built static HTML to index after generation. That couples your architecture to HTML-first output. I would keep it as a lean-variant option only.

External search service: unjustified.

Testing / visual regression / accessibility

Choose:

pytest for backend

Vitest + Testing Library for frontend units

Storybook for component isolation and visual fixture states

Playwright for E2E and screenshot baselines

axe-core in Playwright/Storybook for accessibility checks

Why

Playwright supports screenshot baselines and can apply a deterministic stylesheet during capture.

Storybook is built for isolated UI development/testing.

axe-core integrates into standard test environments and automates accessibility checks.

Deployment

Choose: Build static edition artifacts and deploy to any static host; use Dockerized CI and store release bundles in an S3-compatible bucket or local artifact archive.

Why

Keeps runtime zero-ops.

Supports private/local hosting just as well as public CDN hosting.

Preserves versioned editions cleanly.

Observability

Choose: Structured JSON logs + SQLite event tables + HTML/JSON QA dashboards. Optional OpenTelemetry adapter later.

Why

Personal-scale systems do not need an observability platform to be observable.

Run manifests, per-stage timings, and QA dashboards will give you the debugging surface you actually need.

7. Canonical data model
7.1 Canonical IR overview

The canonical model has these layers:

Source evidence artifacts

native PDF words/spans/images

layout zones

OCR evidence

symbol matches

Canonical PageIR

typed blocks, inline nodes, assets, section hints, provenance

Target PageIR

translated version of PageIR, same structure ids where possible

Render artifacts

frontend-ready, presentation-shaped payloads

QA / provenance artifacts

issues, metrics, waivers, run metadata

7.2 Page-level schema (PageIRV1)

Core fields:

Field	Type	Notes
schema_version	string	page_ir.v1
document_id	string	stable source edition id
page_id	string	p0001 style
page_number	int	source PDF page number
language	enum	en or ru
dimensions_pt	object	source page size
section_hint	object	heading path and inferred section id
zones	array	body/sidebar/footer/figure/etc
blocks	array of block unions	canonical content
assets	array of asset refs	figures/symbol instances used on page
reading_order	array of block ids	final block order
confidence	object	per-page confidence metrics
qa_state	object	page-level blocking/warning summary
provenance	object	extractor versions, evidence refs, patch refs
7.3 Block-level schema

Use a discriminated union on type.

Supported block types:

heading

paragraph

list

list_item

table

table_row

callout

figure

caption

rule_quote

divider

unknown (allowed only pre-publish)

Common block fields:

Field	Type	Notes
block_id	string	stable within doc
type	enum	discriminated union tag
bbox	[x0,y0,x1,y1]	source page bbox
style_hint	object	font/spacing/classification hints
source_ref	object	page evidence refs
children	array	inline nodes or nested blocks
translatable	bool	false for decorative/non-text blocks
continuation	object/null	continuation across pages if needed
annotations	object	glossary hits, numbering, callout kind
7.4 Inline node schema

Supported inline types:

text

icon

figure_ref

xref

line_break

term_mark

TextInlineV1
{
  "type": "text",
  "text": "Gain 1 ",
  "marks": ["bold"],
  "lang": "en",
  "source_word_ids": ["w104", "w105"]
}
IconInlineV1
{
  "type": "icon",
  "symbol_id": "sym.progress",
  "instance_id": "syminst.p0042.01",
  "bbox": [108.2, 119.1, 121.8, 132.7],
  "display_hint": {
    "inline": true,
    "baseline_shift_em": -0.1,
    "size_em": 1.0
  },
  "source_asset_id": "asset.inline.p0042.07"
}
FigureRefInlineV1
{
  "type": "figure_ref",
  "asset_id": "asset.fig.p0042.titan-diagram",
  "label": "Figure 3"
}

7.5 Asset schema (AssetV1)
Field	Type	Notes
asset_id	string	stable id
kind	enum	figure_image, inline_symbol, decorative, page_crop
mime_type	string	image/png etc
source_page_id	string	page origin
bbox	rect	source location
sha256	string	content hash
phash	string	perceptual hash
pixel_size	object	width/height
catalog_binding	object/null	symbol catalog mapping
variants	array	original, web, thumb, sprite
placement_hint	object	render placement
caption_block_id	string/null	if linked
7.6 Glossary / concept schema (ConceptV1)
Field	Type	Notes
concept_id	string	stable concept key
kind	enum	term, phrase, icon_term, entity, mechanic
source	object	English lemma/aliases/patterns
target	object	Russian lemma/allowed forms
icon_binding	string/null	sym.progress etc
phrase_templates	array	high-priority multiword mappings
forbidden_targets	array	blocked mistranslations
validation_policy	object	error/warn severity
notes	string	editorial note
version	string	concept set version
7.7 QA result schema (QARecordV1)
Field	Type	Notes
qa_id	string	unique
layer	enum	extraction/structure/term/icon/render/...
severity	enum	info/warning/error/critical
code	string	machine-readable
document_id	string	
page_id	string/null	
entity_ref	string/null	block/icon/asset ref
message	string	human explanation
expected	json	
actual	json	
auto_fix	object	available fixer or null
evidence_refs	array	upstream evidence
waived	bool	
waiver_ref	string/null	
7.8 Render artifact schema (RenderPageV1)
Field	Type	Notes
schema_version	string	render_page.v1
document_version	string	content hash version
page	object	id/title/section path
nav	object	prev/next/parent
blocks	array	render nodes
figures	object map	figure payloads
glossary_mentions	array	concept ids
search	object	normalized text/terms/snippets
source_map	object	source page refs
build_meta	object	build id, generated at
7.9 Run metadata / provenance schema (RunManifestV1)
Field	Type	Notes
run_id	string	unique
pipeline_version	string	
git_commit	string	
config_hash	string	
source_pdf_sha256	string	
started_at / finished_at	timestamps	
stages	array	per-stage invocation refs
provider_versions	object	extractor/model ids
environment	object	docker image, os, python
qa_summary	object	totals by severity
release_ref	string/null	publish target
7.10 Concrete JSON examples
Example A — page with text + icon + figure reference
{
  "schema_version": "page_ir.v1",
  "document_id": "ato_core_v1_1",
  "page_id": "p0042",
  "page_number": 42,
  "language": "en",
  "dimensions_pt": { "width": 595.2, "height": 841.8 },
  "section_hint": {
    "section_id": "combat.attack-test",
    "path": ["Combat", "Attack Test"]
  },
  "blocks": [
    {
      "block_id": "p0042.b001",
      "type": "heading",
      "bbox": [58.2, 74.1, 301.0, 92.6],
      "level": 2,
      "children": [
        { "type": "text", "text": "Attack Test", "marks": ["small_caps"], "lang": "en" }
      ],
      "translatable": true
    },
    {
      "block_id": "p0042.b002",
      "type": "paragraph",
      "bbox": [58.2, 104.0, 534.8, 154.4],
      "children": [
        { "type": "text", "text": "Gain 1 ", "lang": "en" },
        {
          "type": "icon",
          "symbol_id": "sym.progress",
          "instance_id": "syminst.p0042.01",
          "bbox": [108.2, 119.1, 121.8, 132.7],
          "display_hint": { "inline": true, "size_em": 1.0, "baseline_shift_em": -0.1 },
          "source_asset_id": "asset.inline.p0042.07"
        },
        { "type": "text", "text": " Progress, then place the miniature next to ", "lang": "en" },
        {
          "type": "figure_ref",
          "asset_id": "asset.fig.p0042.titan-diagram",
          "label": "Figure 3"
        },
        { "type": "text", "text": ".", "lang": "en" }
      ],
      "annotations": {
        "concept_hits": ["concept.progress", "concept.titan"],
        "source_confidence": 0.96
      },
      "translatable": true
    },
    {
      "block_id": "p0042.b003",
      "type": "figure",
      "bbox": [349.0, 204.0, 540.0, 420.0],
      "asset_id": "asset.fig.p0042.titan-diagram",
      "children": [
        { "type": "text", "text": "Figure 3. Titan movement.", "lang": "en" }
      ],
      "translatable": true
    }
  ],
  "assets": [
    "asset.inline.p0042.07",
    "asset.fig.p0042.titan-diagram"
  ],
  "reading_order": ["p0042.b001", "p0042.b002", "p0042.b003"],
  "confidence": {
    "native_text_coverage": 0.99,
    "reading_order_score": 0.95,
    "symbol_score": 1.0,
    "page_confidence": 0.97
  },
  "qa_state": {
    "blocking": false,
    "errors": 0,
    "warnings": 1
  },
  "provenance": {
    "native_extractor": "pymupdf@1",
    "layout_evidence": ["docling@1"],
    "symbol_detector": "template_match_v1",
    "patch_refs": []
  }
}

Example B — glossary / concept entry
{
  "concept_id": "concept.progress",
  "kind": "icon_term",
  "version": "glossary.2026-03-11.1",
  "source": {
    "lang": "en",
    "lemma": "Progress",
    "aliases": ["progress token"],
    "patterns": ["Progress", "gain Progress", "lose Progress"]
  },
  "target": {
    "lang": "ru",
    "lemma": "Прогресс",
    "allowed_surface_forms": [
      "Прогресс",
      "Прогресса",
      "Прогрессу",
      "Прогрессом",
      "Прогрессе"
    ]
  },
  "icon_binding": "sym.progress",
  "phrase_templates": [
    {
      "source_pattern": "gain {concept.progress}",
      "target_pattern": "получите {concept.progress}"
    }
  ],
  "forbidden_targets": ["Продвижение", "Развитие"],
  "validation_policy": {
    "missing": "error",
    "forbidden": "error",
    "non_preferred_allowed": "warning"
  },
  "notes": "Game mechanic term and inline symbol."
}
Example C — QA report entry
{
  "qa_id": "qa.p0042.icon.inline_missing.01",
  "layer": "icon_symbol",
  "severity": "error",
  "code": "INLINE_SYMBOL_COUNT_MISMATCH",
  "document_id": "ato_core_v1_1",
  "page_id": "p0042",
  "entity_ref": "p0042.b002",
  "message": "Source evidence found one inline symbol matched to sym.progress but the translated block contains zero icon nodes.",
  "expected": { "symbol_id": "sym.progress", "count": 1 },
  "actual": { "count": 0 },
  "auto_fix": {
    "available": true,
    "fixer": "reinsert_inline_symbol_v1"
  },
  "evidence_refs": [
    "native:p0042:image_block_07",
    "template:p0042:match_03"
  ],
  "waived": false,
  "waiver_ref": null
}
Example D — render-ready page payload
{
  "schema_version": "render_page.v1",
  "document_version": "ato_core_v1_1+ru.c1a9d6f",
  "page": {
    "id": "p0042",
    "title": "Проверка атаки",
    "section_path": ["Бой", "Проверка атаки"],
    "source_page_number": 42
  },
  "nav": {
    "prev": "p0041",
    "next": "p0043",
    "parent_section": "combat"
  },
  "blocks": [
    {
      "id": "p0042.b001",
      "kind": "heading",
      "level": 2,
      "children": [
        { "kind": "text", "text": "Проверка атаки" }
      ]
    },
    {
      "id": "p0042.b002",
      "kind": "paragraph",
      "children": [
        { "kind": "text", "text": "Получите 1 " },
        { "kind": "icon", "symbol_id": "sym.progress", "alt": "Прогресс" },
        { "kind": "text", "text": " Прогресс, затем поставьте миниатюру рядом с " },
        { "kind": "figure_ref", "asset_id": "asset.fig.p0042.titan-diagram", "label": "рис. 3" },
        { "kind": "text", "text": "." }
      ]
    }
  ],
  "figures": {
    "asset.fig.p0042.titan-diagram": {
      "src": "/assets/figures/asset.fig.p0042.titan-diagram.webp",
      "alt": "Схема перемещения Титана",
      "caption": "Рис. 3. Перемещение Титана."
    }
  },
  "glossary_mentions": ["concept.progress", "concept.titan"],
  "search": {
    "raw_text": "Получите 1 Прогресс затем поставьте миниатюру рядом с рис 3",
    "normalized_terms": ["получить", "прогресс", "миниатюра", "рисунок", "титан"]
  },
  "source_map": {
    "page_id": "p0042",
    "block_refs": ["p0042.b001", "p0042.b002"]
  },
  "build_meta": {
    "build_id": "build_20260311_01",
    "generated_at": "2026-03-11T12:01:00Z"
  }
}
8. Pipeline design

I recommend these stages.

8.1 Ingest

Purpose
Register the source edition and create immutable source artifacts.

Input contract
document config + source PDF

Output contract
SourceManifestV1, page count, PDF hash, page render refs, basic metadata

Validation rules

PDF opens successfully

page count stable

source_pdf_sha256 recorded

no duplicate document_id

Behavior
Deterministic.

Retry / checkpoint

retry only transient I/O

key: source_pdf_sha256 + config_hash + ingest_impl_version

Failure modes

encrypted/corrupt PDF

missing file

inconsistent page renders

Observability

page count

render timing

source hash

config hash

8.2 Native PDF extract

Purpose
Extract words, spans, blocks, images, fonts, and geometry directly from the PDF.

Input contract
SourceManifestV1

Output contract
NativePageV1 per page

Validation rules

unique word ids

all bboxes inside page bounds

image refs resolvable

char count nonzero for text-bearing pages

Behavior
Deterministic.

Retry / checkpoint

per-page retry on transient process failure only

key includes page fingerprint and extractor version

Failure modes

broken font encoding

missing or partial text layer

image object extraction errors

Observability

words per page

image blocks per page

char coverage

extraction duration

8.3 Layout evidence extraction

Purpose
Produce zones, region classes, reading-order hints, and table/callout/figure candidates.

Input contract
NativePageV1 + page raster

Output contract
LayoutPageV1 + DifficultyScoreV1

Validation rules

reading order references existing zones

zone overlaps below threshold

confidence metrics present

Behavior
Quasi-deterministic if run locally in a pinned container; treat model version as part of the cache key.

Retry / checkpoint

retry once on CPU if GPU path fails

key includes model id/version and page image hash

Failure modes

collapsed columns

bad table segmentation

unstable region classification

Observability

zone count

column count

overlap score

native/layout agreement score

hard-page score

8.4 Furniture detection

Purpose
Detect headers, footers, page numbers, repeating furniture, and strip them from content zones while keeping metadata.

Input contract
All NativePageV1 and LayoutPageV1 for the document

Output contract
FurnitureMapV1 + cleaned content region refs

Validation rules

removed text must match repeated-region criteria

section headings cannot be stripped without explicit patch/waiver

Behavior
Deterministic.

Retry / checkpoint

document-level

key includes full-doc source hash + furniture config version

Failure modes

over-stripping real headings

under-stripping repeated page furniture

Observability

stripped lines count

repeated cluster count

false-strip candidate list

8.5 Symbol / asset detection

Purpose
Recover inline symbols and figure assets as first-class objects.

Input contract
NativePageV1 + page raster + SymbolCatalogV1

Output contract
SymbolMatchSetV1 + AssetBundleV1

Validation rules

matched symbols above threshold

no duplicate overlapping matches

inline symbols must anchor to valid text lines

unmatched small-image candidates retained for review

Behavior
Deterministic.

Retry / checkpoint

per-page

key includes page raster hash + catalog version + matcher version

Failure modes

false positives on decorative art

missed tiny symbols

wrong inline/non-inline classification

Observability

matched inline symbols

unmatched small image candidates

figure count

symbol confidence histogram

8.6 Structure recovery

Purpose
Recover semantic blocks and final reading order.

Input contract
NativePageV1 + LayoutPageV1 + FurnitureMapV1 + SymbolMatchSetV1 + source patches

Output contract
PageIRV1 (language=en)

Validation rules

publish candidates cannot contain unknown blocks

all inline symbol refs valid

list numbering consistent

heading levels valid against style taxonomy

block order total and non-duplicated

Behavior
Deterministic by default. Optional bounded adjudication may be used on flagged pages only, but only to choose among extracted alternatives, never to invent text.

Retry / checkpoint

per-page

repair retry only if optional adjudicator returns invalid schema

Failure modes

multi-column merge

missed heading

wall-of-text paragraph

callout/table confusion

Observability

block counts by type

structure confidence

unknown block count

reading-order violation score

8.7 Translation planning

Purpose
Convert source PageIR blocks into translation batches with glossary and context bindings.

Input contract
PageIRV1 (en) + ConceptRegistryV1 + StyleGuideV1 + TranslationMemory

Output contract
TranslationBatchV1

Validation rules

every translatable block appears exactly once

icon/figure/xref nodes preserved as locked nodes

required concept ids attached

batch size within model profile limits

Behavior
Deterministic.

Retry / checkpoint

document/page scoped

cache exact-match TM hits before model calls

Failure modes

bad batching

missing concept annotations

low-context segments

Observability

TM hit rate

segments per block type

batch count

glossary density

8.8 Translation execution

Purpose
Translate structured blocks into Russian.

Input contract
TranslationBatchV1

Output contract
TranslationBatchResultV1

Validation rules

exact segment id round-trip

schema valid

locked inline nodes preserved

no missing required fields

Cyrillic/target-language sanity checks

Behavior
Non-deterministic, but controlled with structured outputs and temperature=0.

Retry / checkpoint

one same-model repair retry

then secondary-provider retry for failed segments only

cache key includes provider, model, prompt profile, glossary subset, and input hash

Failure modes

invalid schema

placeholder loss

glossary drift

refusal or truncation

Observability

latency

token usage

provider cache hit signals

invalid result rate

per-model failure rate

8.9 Terminology enforcement and linguistic normalization

Purpose
Make the translation publishable and consistent.

Input contract
TranslationBatchResultV1 + ConceptRegistryV1 + TargetPatchSetV1

Output contract
PageIRV1 (language=ru)

Validation rules

locked concepts resolved correctly

forbidden target forms absent

allowed inflections only for enforced concepts

Russian typography normalization applied

no duplicate icons or broken refs

Behavior
Deterministic.

Retry / checkpoint

no LLM unless a failed segment is routed back to targeted repair

key includes concept registry version + style guide version + target patches

Failure modes

ambiguous inflection

phrase template mismatch

unresolved glossary violation

Observability

term replacements count

remaining errors/warnings

per-concept violation counts

8.10 Render model build

Purpose
Create frontend-ready payloads and asset manifests.

Input contract
PageIRV1 (ru) + AssetBundleV1 + section tree

Output contract
RenderPageV1, nav.json, glossary.json, search_docs.jsonl, asset_manifest.json

Validation rules

all refs resolve

all payloads validate against render schemas

nav links and anchors valid

page payload size budgets respected

Behavior
Deterministic.

Retry / checkpoint

deterministic rebuild only

key includes target IR hashes + render profile version

Failure modes

orphan figure refs

broken xrefs

oversized payloads

Observability

payload size by page

asset count

unresolved refs count

8.11 Site build
Purpose
Build the static reader application.

Input contract
render artifacts + frontend source

Output contract
dist/ static site + build manifest

Validation rules

bundle builds successfully

routes and data files present

hashed assets copied correctly

Behavior
Deterministic under locked Node/toolchain versions.

Retry / checkpoint

build rerun on transient node/tooling failure only

Failure modes

type errors

broken imports

route/data mismatches

Observability

build duration

JS/CSS bundle sizes

route count

8.12 QA, visual regression, publish

Purpose
Enforce release gates and produce review packs.

Input contract
render artifacts + site build + baselines + QA rules + waivers

Output contract
QASummaryV1, review pack, release manifest, publish result

Validation rules

no unwaived blocking QA failures

no console/runtime errors

screenshot diffs within threshold

accessibility gate passes on fixture pages

Behavior
Deterministic in pinned CI/runtime image.

Retry / checkpoint

no semantic retry

failed pages become review candidates

Failure modes

visual drift

runtime errors

broken keyboard navigation

missing alt/aria labels

search/nav failures

Observability

issue totals by severity/layer

screenshot diff metrics

review queue size

publish decision

9. Hard-page strategy

This is where most document projects live or die.

9.1 Routing model

Compute a page_confidence score from:

native_text_coverage

extractor_agreement

reading_order_score

structure_score

symbol_score

Recommended scoring:

page_confidence = 0.30 native_text_coverage + 0.20 extractor_agreement + 0.20 reading_order_score + 0.15 structure_score + 0.15 symbol_score

9.2 Routes
Route	Trigger	Tools	Rule
R1 Standard	single-column, high native coverage, high agreement	PyMuPDF + Docling hints	native text is truth; layout only organizes
R2 Complex layout	multi-column, sidebar, callout-heavy, moderate disagreement	PyMuPDF + Docling + Paddle layout	zone-level reading order resolution
R3 OCR-assisted	low native coverage or image-backed regions	PaddleOCR or Tesseract on affected regions	OCR only fills missing text regions
R4 Symbol-dense	many small inline image candidates	native image objects + template matching	icons recovered independently of text
R5 Table/callout specialized	high table/cell geometry or callout signals	Docling/Paddle table regions	preserve typed table/callout blocks
R6 Human review	page_confidence < 0.80 or blocking ambiguity	review pack + typed patch	no publish without patch/waiver
9.3 Concrete routing rules

Use these thresholds initially:

column_count > 1 or zone_overlap_ratio > 0.08 → R2

native_text_coverage < 0.85 → R3

small_image_candidates >= 3 and inline_likelihood > 0.7 → R4

table_cell_candidate_count >= 6 → R5

extractor_agreement < 0.90 → hard-page route

page_confidence < 0.80 or unresolved error after recovery → R6

9.4 Anti-hallucination rules

These are non-negotiable:

No LLM transcribes a page from pixels as the only source of truth.

LLMs may adjudicate among extracted candidates, but not invent missing text.

OCR output must remain tagged as OCR evidence.

Every final block must reference source evidence ids or an explicit human patch.

If the system cannot establish confidence, it produces a review pack, not fake certainty.

9.5 Human review design

When review is required, produce a review pack, not an email or manual checklist.

Review pack contents:

source page raster

overlay of zones, words, icons, figure candidates

extracted candidate orders

current PageIR rendering

blocking QA issues

patch template file

Human action produces:

patches/source/p0042.structure.patch.json

or patches/target/p0042.translation.patch.json

or a versioned QA waiver

This keeps manual intervention deterministic.

10. Translation architecture
10.1 Translation unit choice

Translate at the logical block level, not page level and not single-word level.

Translate as one unit:

headings

paragraphs

list items

callout titles/body blocks

captions

table cells or row groups, depending on table shape

Do not translate as one unit:

full pages

raw markdown blobs

entire multi-block sections

Reason
Paragraph/list-item scope is the sweet spot:

enough context for grammatical Russian

small enough for deterministic validation

stable ids

easy retry of failed segments only

10.2 Structured contract
Translation request contract (TranslationBatchV1)
{
  "batch_id": "tr.p0042.01",
  "source_lang": "en",
  "target_lang": "ru",
  "prompt_profile": "translate_rules_ru.v1",
  "segments": [
    {
      "segment_id": "p0042.b002",
      "block_type": "paragraph",
      "source_inline": [
        { "type": "text", "text": "Gain 1 " },
        { "type": "icon", "symbol_id": "sym.progress" },
        { "type": "text", "text": " Progress." }
      ],
      "context": {
        "page_id": "p0042",
        "section_path": ["Combat", "Attack Test"],
        "prev_heading": "Attack Test"
      },
      "required_concepts": ["concept.progress"],
      "forbidden_targets": ["Продвижение"],
      "locked_nodes": ["sym.progress"],
      "source_checksum": "sha256:..."
    }
  ]
}
Translation result contract (TranslationBatchResultV1)
{
  "batch_id": "tr.p0042.01",
  "segments": [
    {
      "segment_id": "p0042.b002",
      "target_inline": [
        { "type": "text", "text": "Получите 1 " },
        { "type": "icon", "symbol_id": "sym.progress" },
        { "type": "text", "text": " Прогресс." }
      ],
      "concept_realizations": [
        {
          "concept_id": "concept.progress",
          "surface_form": "Прогресс"
        }
      ]
    }
  ]
}
10.3 Translation control stack
A. Translation memory first

If source_checksum exactly matches a previously approved segment, reuse it.

B. Concept-aware planning

Annotate each segment with:

required concepts

preferred phrase templates

forbidden targets

locked inline nodes

C. Structured model output

Require JSON schema output only.

D. Deterministic validation

Reject any segment that:

changes icon count/order

drops figure/xref nodes

violates locked concepts

fails target-language sanity checks

E. Repair loop

Repair only failed segments with exact error codes.

F. Secondary-provider arbitration

Only for stubborn failures.

10.4 Glossary / concept enforcement

Do not model the glossary as a dumb dictionary.

Model it as two layers:

Concept registry
Atomic ideas: Fate, Progress, Titan, Primordial, etc.

Phrase template registry
High-value multiword constructs:

“Fate Test”

“Gain Progress”

“Battleflow card”

“Activation step”

Enforcement order:

phrase template

concept-level validation

deterministic normalization

targeted repair if still invalid

10.5 Russian inflection handling

Be practical here.

Do not try to fully deterministic-generate all Russian phrase inflections from English syntax.

Do:

let the model generate grammatical Russian

validate required concept lemma usage

maintain allowed forms for locked terms

use pymorphy3 to validate or generate atomic inflection cases where safe

store phrase-level templates for critical domain terms

That is the right balance between correctness and maintainability. pymorphy3 is appropriate here because it is a maintained Russian/Ukrainian inflection engine.

10.6 Style guide enforcement

Create a versioned style_guide.toml with rules such as:

tone: rules-precise, non-literary

person: imperative instructional prose

quotes: Russian «ёлочки»

spacing around inline icons

heading capitalization policy

allowed transliteration patterns

number formatting

bold/small-caps conventions for key terms

The model sees the guide. The postprocessor enforces the deterministic parts.

10.7 Prompt caching opportunities

Keep the stable prefix large and fixed:

system instructions

style guide

compact glossary subset format

inline node rules

output schema rules

Both OpenAI and Anthropic document prompt caching support/cost benefits, so the architecture should deliberately stabilize the prefix across requests.

10.8 Model choice by task

Default translation: gpt-5.4

Hard segment repair / arbitration: gpt-5.4-pro

Fallback provider: claude-sonnet-4-6

Escalation on truly nasty segments: claude-opus-4-6

Do not use high-end models for all segments. Use them only on the small failing tail.

11. QA architecture
QA must be layered and release-blocking.

11.1 QA layers
Layer	What to measure	Threshold	Auto-fixable	Blocks publish
Extraction QA	native coverage, extractor agreement, zero-word anomalies	coverage ≥ 0.97 on text pages; hard-page route otherwise	some	yes
Structure QA	unknown blocks, heading/list/table validity, wall-of-text	0 unknown blocks in publish set	some	yes
Terminology QA	locked concepts, forbidden targets, phrase templates	0 term errors	many	yes
Icon/symbol QA	source vs target icon counts, order, unresolved candidates	exact count/order for inline icons	many	yes
Asset/link QA	figure refs, captions, asset paths	0 broken refs	yes	yes
Render QA	schema validation, console errors, broken routes	0 errors	some	yes
Visual regression QA	story/page screenshot drift	within baseline threshold	no	yes on fixture set
Accessibility QA	keyboard nav, labels, color/aria issues via axe	0 critical failures on fixture pages	some	yes
11.2 Concrete rules
Extraction QA

native_text_coverage >= 0.97 on normal text pages

if < 0.97, route to hard-page pipeline, not warning-only

extractor_agreement >= 0.92 on overlapping regions

Structure QA

no unknown blocks in publishable page

no paragraph over 900 chars without list/heading boundaries unless explicitly waived

no missing heading on pages classified as section-openers

list numbering continuity must be exact inside a list group

Terminology QA

zero missing locked concepts

zero forbidden target forms

preferred phrase template mismatch = warning

concept absence where source hit exists = error

Icon QA

source inline icon count must equal target inline icon count

inline icon order must be preserved within block

any unmatched small-image candidate with confidence ≥ 0.93 is an error until resolved or waived

Asset/link QA

every figure ref must resolve

every published figure must have alt text and source ref

zero broken asset URLs in build

Render QA

all render payloads validate

no browser console errors on fixture routes

no missing data fetches

no route 404s for nav/xrefs

Visual regression QA

Storybook component fixtures: strict pixel baseline in pinned container

Reader page fixtures: allow tiny tolerance only for anti-aliasing noise

freeze animations/cursors and use deterministic CSS during capture

Playwright supports screenshot baselines and a stylePath option specifically to improve screenshot determinism. Storybook is designed for isolated UI states, and axe-core integrates automated accessibility checks into regular web testing.

11.3 Auto-fix vs block policy
Auto-fixable

icon reinsertion from high-confidence symbol match

exact terminology replacement from phrase template

typography normalization

broken relative asset path correction

heading level normalization when globally unambiguous

Not auto-fixable

ambiguous reading order

unclear table structure

low-confidence OCR text

semantically ambiguous term translation

unclear figure/caption pairing

These create review tasks, not silent fixes.

11.4 Storage and surfacing

Store QA in:

qa/page/*.json

qa/summary.json

qa/metrics.parquet

qa/review_queue.json

Surface through:

CLI summary

static HTML QA dashboard

review console

release manifest

12. Frontend architecture
12.1 Framework choice

Build a static React + TypeScript + Vite app.

The app should not parse markdown. It should consume typed RenderPageV1 payloads and render components from explicit node types.

12.2 Rendering model

Core renderer components:

BlockRenderer

InlineRenderer

IconInline

FigureBlock

CalloutBlock

TableBlock

GlossaryLink

SourceAnchorBadge

Render rules:

text nodes render plain text with semantic marks

icon nodes render from symbol catalog metadata, not regex token parsing

figure refs render linked captions/assets

tables render semantic HTML tables

callouts render styled containers based on variant

12.3 Search architecture

Build normalized search docs offline from render payloads.

Include:

Russian text

English aliases

glossary terms

section paths

source page numbers

Serialize MiniSearch index or indexable docs into static assets.

Lazy-load search assets on first search open.

MiniSearch is a browser-friendly in-memory search engine, which is appropriate for a single-book reader. Pagefind remains a valid lean alternative if you later move to fully prerendered HTML output.

12.4 Glossary UX

Glossary should not be a dead appendix.

Implement:

dedicated glossary page

inline term hover/click card

backlinks from concept -> occurrences

icon preview in glossary entries

English source term + Russian preferred term + aliases + notes

12.5 Navigation model

Provide three navigation modes:

Section tree

Prev / next page

Source page jump

Primary nav should be section-based. Source page numbers remain visible as traceability metadata.

12.6 Offline / static-hosting friendliness

no runtime backend

all data files static

relative asset URLs

optional service worker later

content versions can coexist in separate static directories

12.7 Performance

route-level code splitting

lazy-load page JSON and heavy figures

sprite sheet for repeated icons

precomputed search index

image variants: thumb / reading / original

fixed payload size budgets

12.8 Accessibility

keyboard-first nav

semantic headings/tables

alt text on figures

aria labels on icons where needed

visible focus styles

color contrast checked in Storybook/Playwright

12.9 Content versioning

Publish under:

/<document_id>/<content_version>/...

Keep a tiny current.json or redirect ref for latest-approved edition.

12.10 Suggested frontend folder structure
apps/web/
  src/
    app/
      router.tsx
      providers/
      hooks/
    routes/
      Home.tsx
      ReaderPage.tsx
      Glossary.tsx
      Search.tsx
      NotFound.tsx
    components/
      reader/
        BlockRenderer.tsx
        InlineRenderer.tsx
        IconInline.tsx
        FigureBlock.tsx
        CalloutBlock.tsx
        TableBlock.tsx
      nav/
        TocTree.tsx
        PrevNextNav.tsx
        SourcePageBadge.tsx
      glossary/
        GlossaryCard.tsx
        GlossaryIndex.tsx
      search/
        SearchDialog.tsx
        SearchResults.tsx
    lib/
      api/
      search/
      glossary/
      render/
      schemas/
    styles/
      tokens.css
      reader.module.css
    stories/
      reader/
      glossary/
      nav/
13. Repository / folder structure
Use a monorepo with clear app/package boundaries.

repo/
  README.md
  pyproject.toml
  pnpm-workspace.yaml
  .github/
    workflows/
  configs/
    base.toml
    local.toml
    ci.toml
    documents/
      ato_core_v1_1.toml
    glossary/
      concepts.toml
      phrase_templates.toml
    symbols/
      ato_core_v1_1.symbols.toml
    qa/
      thresholds.toml
      waivers.toml
  apps/
    pipeline/
      src/atr_pipeline/
        cli/
        runner/
        contracts/
        ingest/
        extract/
          native_pdf/
          layout/
          ocr/
        furniture/
        symbols/
        structure/
        glossary/
        translate/
        assets/
        render/
        qa/
        patches/
        reporting/
      tests/
    web/
      src/
      public/
      tests/
    review/
      src/
  packages/
    schemas/
      jsonschema/
      generated_ts/
    prompts/
      translate/
      repair/
      adjudicate/
    fixtures/
      sample_pages/
        single_column/
        multi_column/
        icon_dense/
        tables_callouts/
        low_confidence/
      sample_documents/
    qa_assets/
      screenshot_baselines/
      source_overlays/
  docs/
    architecture/
    runbooks/
    specs/
    adrs/
  scripts/
    bootstrap.sh
    build_release.sh
    regenerate_schemas.py
    migrate_artifacts.py
  artifacts/
    .gitignore
  patches/
    source/
    target/
    qa/

Notes:

artifacts/ stays out of git.

patches/ stays in git.

packages/schemas is the bridge between backend and frontend.

packages/fixtures is where agent-safe gold data lives.

14. Interface contracts and boundaries
14.1 Important schemas between stages

Use these exact schema families:

SourceManifestV1

NativePageV1

LayoutPageV1

FurnitureMapV1

SymbolMatchSetV1

AssetBundleV1

PageIRV1

ConceptRegistryV1

TranslationBatchV1

TranslationBatchResultV1

RenderPageV1

QASummaryV1

QARecordV1

RunManifestV1

PatchSetV1

14.2 Service interfaces
Stage interface
class Stage(Protocol):
    name: str
    scope: Literal["document", "page", "asset", "batch"]
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def run(self, ctx: StageContext, data: BaseModel) -> BaseModel: ...
Translator interface
class Translator(Protocol):
    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str,
    ) -> TranslationBatchResultV1: ...
Symbol detector interface
class SymbolDetector(Protocol):
    def detect(
        self,
        native_page: NativePageV1,
        page_image_path: str,
        catalog: SymbolCatalogV1,
    ) -> SymbolMatchSetV1: ...
QA rule interface
class QARule(Protocol):
    code: str
    layer: str

    def evaluate(self, artifact: BaseModel) -> list[QARecordV1]: ...
14.3 CLI / job runner contracts

Recommended CLI:

atr ingest --doc ato_core_v1_1
atr run --doc ato_core_v1_1 --from ingest --to page-ir-en
atr run --doc ato_core_v1_1 --from translate --to publish
atr rerun-page --doc ato_core_v1_1 --page p0042 --stage structure
atr build-review-pack --doc ato_core_v1_1
atr diff-runs --run-a run_... --run-b run_...
atr qa --doc ato_core_v1_1
14.4 Config system

Use layered TOML config:

configs/base.toml

configs/local.toml or configs/ci.toml

configs/documents/<doc>.toml

Example config
[document]
id = "ato_core_v1_1"
source_pdf = "inputs/ato_core_v1_1/rules_en.pdf"
source_lang = "en"
target_langs = ["ru"]

[pipeline]
version = "2.0.0"
parallelism = 8
review_threshold = 0.80

[extract.native]
engine = "pymupdf"

[extract.layout]
primary = "docling"
hard_fallback = "paddleocr"
dpi = 300

[symbols]
catalog = "configs/symbols/ato_core_v1_1.symbols.toml"
match_threshold = 0.93

[translation]
provider = "openai"
model_default = "gpt-5.4"
model_hard = "gpt-5.4-pro"
fallback_provider = "anthropic"
fallback_model = "claude-sonnet-4-6"
temperature = 0.0
batch_size = 24
prompt_profile = "translate_rules_ru.v1"

[qa]
block_publish_on = ["error", "critical"]
14.5 Prompt / template organization
Store prompts as versioned files with metadata headers:

packages/prompts/translate/translate_rules_ru.v1.md
packages/prompts/translate/repair_rules_ru.v1.md
packages/prompts/adjudicate/reading_order.v1.md

Frontmatter:

prompt_id: translate_rules_ru
version: v1
input_schema: TranslationBatchV1
output_schema: TranslationBatchResultV1
allowed_models:
  - gpt-5.4
  - gpt-5.4-pro
  - claude-sonnet-4-6
14.6 Artifact naming / versioning conventions
IDs

page: p0001

block: p0001.b003

asset: asset.fig.p0042.titan-diagram

concept: concept.progress

run: run_20260311T120100Z_a1b2c3d4

Artifact paths
artifacts/<doc_id>/<schema_family>/<scope>/<id>/<input_hash>.json

Examples:

artifacts/ato_core_v1_1/page_ir.v1/page/p0042/8f3c12ab45ef.json
artifacts/ato_core_v1_1/render_page.v1/page/p0042/c91d7ee0f0d1.json
Version tags

schema: page_ir.v1

pipeline: 2.0.0

glossary: glossary.2026-03-11.1

prompt: translate_rules_ru.v1

content: ato_core_v1_1+ru.c1a9d6f

15. Implementation roadmap
Phase 0 — Blueprint and fixtures

Build first

repo scaffold

contracts

fixture pages covering every hard case

artifact store + runner skeleton

Milestone

validate schemas and artifact lifecycle on fake/sample data

Do not build yet

translation

full frontend

Phase 1 — English source edition pipeline

Build

ingest

native extract

layout evidence

furniture detection

symbol catalog + symbol matching

structure recovery

render builder for English source edition

Milestone

you can browse a source-faithful English digital reader with icons and figures

This is the critical sequencing decision. Do not add translation until the English source edition is trustworthy.

Phase 2 — Translation subsystem

Build

concept registry

translation planner

structured model adapter

TM cache

terminology enforcement

target PageIR

translation QA

Milestone

Russian edition renders from the same IR with zero markdown dependence

Phase 3 — Reader application

Build

typed React renderer

nav/glossary/search

assets

source page traceability UI

Milestone

full reader usable end-to-end

Phase 4 — QA and review workflow

Build

layered QA engine

review packs

patch application system

visual regression fixtures

accessibility checks

Milestone

publish gate becomes automated

Phase 5 — CI/CD and release process

Build

Dockerized pipeline image

CI jobs

static release packaging

release manifests

regression diff tooling

Milestone

one-command reproducible build and publish

Phase 6 — Optional enhancements

Defer until the system is already working:

service worker/offline caching

side-by-side source view

richer review UI

multi-document library support

external hosting automation

Migration path from current system

If you want incremental adoption instead of a cold switch:

Reuse keywords.json as the seed for ConceptRegistryV1.

Reuse current symbol mapping files as seed data for the new symbol catalog.

Treat current pages.jsonl and markdown outputs as verification fixtures, not upstream truth.

Build the new English source edition first and compare it against the old system page by page.

Only switch the frontend once RenderPageV1 is stable.
16. Agent-oriented work breakdown

Below is a low-ambiguity work package split suitable for coding agents.

WP1 — Repo scaffold and schema package

Goal
Create monorepo structure, schema package, JSON Schema generation, and code quality tooling.

Dependencies
None.

Input / output files

create apps/, packages/, configs/, docs/

define packages/schemas/*

define pyproject.toml, workspace files

Acceptance criteria

schemas validate sample fixtures

TS types generated from JSON Schema

CI runs lint/typecheck/tests

Tests to write

schema round-trip

fixture validation

generated TS compile check

Likely risks

schema churn

backend/frontend type drift

Order

first

WP2 — Artifact store and runner

Goal
Implement immutable artifact store, run registry, cache key logic, and CLI runner.

Dependencies
WP1.

Input / output files

apps/pipeline/src/.../runner/

apps/pipeline/src/.../cli/

SQLite registry

Acceptance criteria

stage can run twice and hit cache

invalid artifact never enters cache

run manifest recorded

Tests

cache key stability

atomic write test

rerun/page-scope replay test

Risks

path/key design mistakes

hidden mutability

Order

second

WP3 — Native PDF extraction

Goal
Extract words, spans, blocks, images, and page geometry from PDF.

Dependencies
WP2.

Input / output

input: source PDF

output: NativePageV1

Acceptance criteria

sample pages produce stable word/image counts

all bboxes inside page bounds

image refs resolvable

Tests

golden fixture tests for known pages

extraction determinism

corrupt-PDF error handling

Risks

PDF oddities

font encoding edge cases

Order

third

WP4 — Layout evidence and hard-page classifier

Goal
Add Docling/Paddle layout evidence and page difficulty scoring.

Dependencies
WP3.

Input / output

NativePageV1 + page raster -> LayoutPageV1 + DifficultyScoreV1

Acceptance criteria

multi-column fixtures classified correctly

hard-page routing fires on known bad pages

Tests

golden zone layout tests

classifier threshold tests

CPU fallback test

Risks

unstable layout outputs

overfitting thresholds

Order

fourth

WP5 — Symbol catalog and icon anchoring

Goal
Build symbol catalog, image clustering/import tool, and deterministic inline anchoring.

Dependencies
WP3.

Input / output

configs/symbols/*

SymbolMatchSetV1, AssetBundleV1

Acceptance criteria

icon-dense fixtures recover exact inline icon counts

no regex token reinjection needed

unmatched candidates surfaced cleanly

Tests

template-match precision/recall on fixture pages

overlap dedupe tests

inline placement order tests

Risks

false positives on decorative art

catalog seeding quality

Order

fifth

WP6 — Structure recovery and English PageIR

Goal
Recover headings, paragraphs, lists, callouts, figures, and final reading order.

Dependencies
WP4, WP5.

Input / output

upstream evidence -> PageIRV1 (en)

Acceptance criteria

no unknown blocks on normal fixtures

heading/list/table fixtures pass

English source reader payload can be built

Tests

golden PageIR snapshots

reading-order tests

furniture stripping tests

Risks

ambiguous layout pages

brittle heuristics

Order

sixth

WP7 — Glossary registry, phrase templates, TM

Goal
Implement concept registry, phrase templates, exact-match translation memory, and source concept matcher.

Dependencies
WP6.

Input / output

configs/glossary/*

ConceptRegistryV1

TM store

source segment annotations

Acceptance criteria

source segments get correct concept hits

exact TM reuse works

forbidden target lists available to translator

Tests

concept matching tests

phrase template priority tests

TM hit/miss tests

Risks

glossary design too shallow

phrase collisions

Order

seventh

WP8 — Translation subsystem

Goal
Implement translation planning, provider adapters, structured outputs, validation, and repair loop.

Dependencies
WP7.

Input / output

TranslationBatchV1 -> TranslationBatchResultV1 -> PageIRV1 (ru)

Acceptance criteria

icons/xrefs survive translation

exact schema validation enforced

failed segments retried/repaired in isolation

Tests

provider adapter mocks

schema violation handling

placeholder preservation tests

TM short-circuit tests

Risks

provider API drift

prompt/schema mismatch

Order

eighth
WP9 — QA engine, waivers, patch system

Goal
Implement QA rules, typed waivers, typed patches, and review queue generation.

Dependencies
WP6, WP8.

Input / output

QARecordV1, QASummaryV1, patch files, waiver files

Acceptance criteria

blocking vs warning behavior enforced

review queue generated from real failures

patches replay deterministically

Tests

waiver expiry tests

patch application tests

release blocking tests

Risks

waiver abuse

patch ordering bugs

Order

ninth

WP10 — Render builder and search/glossary/nav artifacts

Goal
Build frontend-ready payloads from target IR.

Dependencies
WP8, WP9.

Input / output

RenderPageV1

nav.json

glossary.json

search_docs/index

Acceptance criteria

all refs resolve

search docs include glossary aliases

payload schemas validate

Tests

render payload snapshots

xref resolution

search doc generation tests

Risks

payload bloat

inconsistent ids

Order

tenth

WP11 — React reader app

Goal
Implement typed frontend renderer, nav, glossary, search, and page routing.

Dependencies
WP10.

Input / output

apps/web/*

Acceptance criteria

renders fixture edition end-to-end

icons, tables, callouts, figures display correctly

keyboard nav and glossary interactions work

Tests

component tests

route tests

Storybook stories for all block types

Risks

accidental markdown thinking

CSS drift

Order

eleventh

WP12 — Visual regression, accessibility, release pipeline

Goal
Implement Storybook/Playwright/axe checks and static release packaging.

Dependencies
WP11.

Input / output

screenshot baselines

accessibility report

release manifest

dist/

Acceptance criteria

golden fixtures pass

accessibility gate runs in CI

build artifact publishable from one command

Tests

screenshot baseline tests

axe integration tests

release manifest checksum tests

Risks

noisy baselines

environment drift

Order

last
17. ADRs to create
ADR-001 — Canonical state is typed IR, not markdown

Decision: The source of truth is a versioned JSON IR with typed blocks, inline nodes, assets, QA state, and provenance.
Rationale: Markdown cannot faithfully represent inline icons, layout anchors, figure objects, or deterministic patching.
Alternatives rejected: Markdown-centric pipeline; HTML as source of truth.

ADR-002 — Use PyMuPDF as native evidence source

Decision: PyMuPDF is the low-level native PDF extractor.
Rationale: It gives precise word/block/image geometry and stable page evidence.
Alternatives rejected: Docling-only extraction; pdfplumber/pdfminer as primary.

ADR-003 — Use Docling and PaddleOCR as structural evidence, not canonical text

Decision: Docling and Paddle provide layout/order evidence and hard-page fallback.
Rationale: They improve structure recovery without replacing native PDF truth.
Alternatives rejected: OCR-first pipeline; single extractor strategy.

ADR-004 — Treat symbols as first-class catalogued assets

Decision: Inline icons are recovered by catalog matching and template matching, then rendered as icon nodes.
Rationale: Regex reinjection is brittle and untraceable.
Alternatives rejected: markdown token hacks; term-pattern reinsertion only.

ADR-005 — Artifacts are immutable; corrections are typed patches

Decision: Stage outputs are immutable; human corrections are patch artifacts under version control.
Rationale: This gives deterministic replay and eliminates hidden manual edits.
Alternatives rejected: editing JSON/markdown in place; manual hotfix scripts.

ADR-006 — No workflow orchestrator in v1

Decision: Use a custom runner, not Prefect/Dagster/Temporal.
Rationale: The system is personal-scale and artifact-centric; orchestration overhead is premature.
Alternatives rejected: Prefect, Dagster, Temporal.

ADR-007 — Translation operates on structured block-level units

Decision: Translate block-level units with structured output contracts.
Rationale: This balances context quality with deterministic validation and retry granularity.
Alternatives rejected: page-level translation; sentence/word-level translation.

ADR-008 — Glossary is a concept registry plus phrase templates

Decision: Maintain concept ids, phrase templates, allowed target forms, and validation severity.
Rationale: A flat dictionary cannot enforce game terminology correctly in Russian.
Alternatives rejected: keyword replacement only; prompt-only glossary.

ADR-009 — Publish a static React reader, not a runtime CMS

Decision: Build static reader payloads and deploy static assets.
Rationale: Zero-ops runtime, easy versioning, simple distribution.
Alternatives rejected: SSR app; database-backed CMS.

ADR-010 — Search indexes IR-derived content, not generated HTML

Decision: Build search from render payloads and glossary metadata.
Rationale: Keeps the system IR-first and avoids HTML coupling.
Alternatives rejected: Pagefind as primary; hosted search.

ADR-011 — QA is release-blocking and machine-readable

Decision: All QA rules emit typed records and block publish when severity is error or critical.
Rationale: Manual visual inspection becomes the exception.
Alternatives rejected: ad hoc reports; non-blocking QA.

ADR-012 — Build the English source edition before adding translation

Decision: First deliver a correct English digital reader on the new IR.
Rationale: It isolates extraction/render correctness from translation errors.
Alternatives rejected: rebuilding extraction and translation at once.

18. Biggest risks and mitigation
Risk	Why it matters	Mitigation
Symbol matching misses or misbinds icons	core fidelity failure	curated symbol catalog, conservative thresholds, unmatched-candidate review queue
Structure recovery is brittle on stylized pages	headings/lists/callouts break reader quality	dual-evidence extraction, hard-page routing, golden fixtures, typed source patches
Translation drifts terminology	rules meaning changes	concept registry, phrase templates, TM, strict validators, repair loop
LLM provider behavior changes	schema/prompt behavior can drift	provider abstraction, strict validation, raw-response capture, fallback provider
Over-engineering the first release	slow progress	phase plan, English source edition first, review UI deferred
QA baseline noise	reduces trust in automation	pinned Docker/browser/font stack, fixture page set, deterministic screenshot CSS
Schema churn stalls agents	implementation ambiguity	lock schemas early, ADRs, generated TS types, migration scripts
Hidden manual edits reintroduce nondeterminism	replay/debugging collapses	patch-only correction model, artifact immutability
19. Lean variant

If you want a lower-complexity variant that preserves most of the upside:

Lean architecture

Keep the IR-first modular monolith

Use PyMuPDF + Docling only

Use Tesseract as the only OCR fallback

Skip PaddleOCR initially

Skip separate review app; generate static HTML review reports instead

Keep filesystem artifacts + manifest JSON only; defer SQLite registry

Keep React + Vite

Keep MiniSearch

Keep structured translation + glossary registry + TM

Keep Playwright but skip Storybook in v1 if needed

What you lose

less robust hard-page routing

weaker automated layout fallback on multi-column pages

less observability

poorer manual-review ergonomics

less scalable cross-run analytics

What you keep

typed IR

symbol first-class handling

deterministic artifacts

structured translation

searchable/glossary-aware reader

static hosting

replayable builds

If you are short on implementation budget, this is the only lean cut I would accept. I would not cut the IR, the symbol catalog, or structured translation contracts.

20. Final recommendation

Build this exact architecture:

An IR-first Python modular monolith with immutable artifact storage, PyMuPDF as native truth, Docling plus hard-page OCR/layout fallback as structural evidence, first-class symbol catalog/template matching, structured block-level translation with concept enforcement and translation memory, and a static React reader that renders typed nodes instead of markdown.

Why this is the right architecture:

It solves icon loss structurally, not cosmetically.

It solves multi-column/order problems by fusing evidence instead of trusting one extractor.

It makes glossary consistency enforceable instead of aspirational.

It eliminates idempotency bugs through immutable artifacts and patch layers.

It turns QA from manual browsing into deterministic release gates.

It is strong enough for production-shaped personal use without dragging in SaaS infrastructure.

The first 3 implementation steps should be:

Lock the schemas and runner.
Create PageIRV1, RenderPageV1, QARecordV1, the artifact store, cache-key rules, and 10–15 gold fixture pages.

Build the English source edition first.
Implement ingest, native extract, layout evidence, furniture detection, symbol catalog/matching, structure recovery, and render an English digital reader with correct icons and figures.

Add structured translation second.
Implement concept registry, translation memory, structured translation batches, terminology enforcement, and Russian render payloads—without introducing markdown back into the pipeline.
