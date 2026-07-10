# Image-set Source Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed image-set source contract and immutable raw-image ingest while preserving the existing PDF path.

**Architecture:** Normalize document input into a tagged PDF/image-set source union, validate image-set manifests completely before writes, and dispatch within the existing ingest stage. Extend the source manifest with separate image-set identity fields and fold all source bytes into the executor cache key.

**Tech Stack:** Python 3.12, Pydantic v2, Pillow, Typer, pytest, immutable `ArtifactStore`, generated JSON Schema and TypeScript.

## Global Constraints

- Work only on `s5unanow/s5u-1553-sl-image-set-source-foundation`.
- Commit messages start with `S5U-1553: `.
- No new third-party dependencies.
- No OCR, crop/orientation/rectification, PageIR, reader, or visual snapshot changes.
- Every refusal occurs before any artifact write.
- Python source and test files stay below 400 lines.
- Generated JSON Schema and TypeScript change only through `make codegen`.

---

### Task 1: Source config union and compatibility

**Files:**
- Create: `apps/pipeline/src/atr_pipeline/config/source.py`
- Modify: `apps/pipeline/src/atr_pipeline/config/models.py`
- Test: `apps/pipeline/tests/unit/config/test_source_config.py`

**Interfaces:**
- Produces: `PdfSourceConfig`, `ImageSetSourceConfig`, `DocumentSourceConfig`, and normalized `DocumentConfig.source`.
- Preserves: `DocumentConfig.source_pdf` input/access and `DocumentBuildConfig.source_pdf_path` for PDF callers.

- [ ] **Step 1: Write failing config tests**

Cover legacy `source_pdf` normalization, explicit PDF/image-set variants,
unknown `source_kind`, and the existing PDF resolved path.

```python
def test_legacy_source_pdf_normalizes_to_pdf_variant() -> None:
    config = DocumentConfig(id="legacy", source_pdf="book.pdf")
    assert config.source.source_kind == "pdf"
    assert config.source_pdf == "book.pdf"

def test_unknown_source_kind_fails_closed() -> None:
    with pytest.raises(ValidationError, match="source_kind"):
        DocumentConfig.model_validate(
            {"id": "bad", "source": {"source_kind": "scanner", "manifest_path": "x"}}
        )
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/pipeline/tests/unit/config/test_source_config.py -q`

Expected: import/model failures because the source variants do not exist.

- [ ] **Step 3: Implement the union and compatibility adapter**

Move `DocumentConfig` out of the near-limit `models.py`. Use
`Annotated[PdfSourceConfig | ImageSetSourceConfig, Field(discriminator="source_kind")]`
and a `model_validator(mode="before")` to normalize legacy input.

- [ ] **Step 4: Verify GREEN and existing PDF config tests**

Run: `uv run pytest apps/pipeline/tests/unit/config/test_source_config.py apps/pipeline/tests/unit/config/test_loader.py -q`

- [ ] **Step 5: Commit**

Commit with `S5U-1553: add source config abstraction` and include the observed
red-before failure excerpt.

### Task 2: Image-set and source-manifest schemas

**Files:**
- Create: `packages/schemas/python/atr_schemas/image_set_manifest_v1.py`
- Modify: `packages/schemas/python/atr_schemas/source_manifest_v1.py`
- Modify: `packages/schemas/python/atr_schemas/__init__.py`
- Modify: `scripts/generate_jsonschema.py`
- Test: `apps/pipeline/tests/contract/test_image_set_source_contract.py`

**Interfaces:**
- Produces: `CaptureMetadataV1`, `ImageSetImageEntryV1`, `ImageSetManifestV1`, and `SourceImageEntryV1`.
- Extends: `SourceManifestV1` with `source_kind`, `source_manifest_sha256`, `source_image_set_sha256`, and `source_images` while retaining `source_pdf_sha256`.

- [ ] **Step 1: Write failing schema roundtrip and invariant tests**

```python
def test_image_set_manifest_roundtrips() -> None:
    manifest = ImageSetManifestV1.model_validate(VALID_IMAGE_SET)
    assert ImageSetManifestV1.model_validate_json(manifest.model_dump_json()) == manifest

def test_image_source_does_not_overload_pdf_hash() -> None:
    manifest = SourceManifestV1.model_validate(VALID_SOURCE_MANIFEST)
    assert manifest.source_kind == "image_set"
    assert manifest.source_pdf_sha256 == ""
```

Also assert duplicate IDs, duplicate page mappings, non-contiguous order, and
PDF/image-set fingerprint invariant violations fail validation.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/pipeline/tests/contract/test_image_set_source_contract.py -q`

- [ ] **Step 3: Implement focused Pydantic models**

Keep SHA fields constrained to 64 lowercase hex characters when non-empty,
page IDs constrained to `pNNNN`, and supported media types constrained to PNG
and JPEG literals.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/pipeline/tests/contract/test_image_set_source_contract.py apps/pipeline/tests/contract/test_schema_roundtrip.py -q`

- [ ] **Step 5: Commit**

Commit with `S5U-1553: add image-set source schemas` and red-before evidence.

### Task 3: Safe image-set preflight

**Files:**
- Create: `apps/pipeline/src/atr_pipeline/stages/ingest/path_safety.py`
- Create: `apps/pipeline/src/atr_pipeline/stages/ingest/image_set_preflight.py`
- Test: `apps/pipeline/tests/unit/stages/ingest/test_image_set_preflight.py`

**Interfaces:**
- Produces: `preflight_image_set(manifest_path, *, allowed_roots) -> ImageSetIngestPlan`.
- Guarantees: returned entries contain resolved paths, validated bytes, detected media types, exact hashes, and deterministic raw artifact IDs; no store is accepted or written.

- [ ] **Step 1: Write failing happy-path and refusal tests**

Use temporary tiny Pillow PNG/JPEG files. Parameterize traversal, absolute
escape, null byte, unsupported media, duplicate ID, duplicate resolved path,
malformed JSON, missing image, SHA mismatch, and corrupt image cases.

```python
@pytest.mark.parametrize("case", REFUSAL_CASES)
def test_preflight_refuses_invalid_source(case: RefusalCase, tmp_path: Path) -> None:
    manifest_path = case.arrange(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError), match=case.message):
        preflight_image_set(manifest_path, allowed_roots=(tmp_path,))
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/pipeline/tests/unit/stages/ingest/test_image_set_preflight.py -q`

- [ ] **Step 3: Implement path safety and preflight**

Reject nulls and `..` before `Path` resolution, use strict realpath resolution,
enforce `Path.is_relative_to` containment, parse JSON through Pydantic, read all
bytes, verify SHA, verify Pillow format, and calculate the canonical ordered
image-set fingerprint.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/pipeline/tests/unit/stages/ingest/test_image_set_preflight.py -q`

- [ ] **Step 5: Commit**

Commit with `S5U-1553: validate image-set sources before ingest` and red-before
evidence.

### Task 4: Image-set ingest, cache identity, and PDF regression

**Files:**
- Create: `apps/pipeline/src/atr_pipeline/stages/ingest/image_set_ingest.py`
- Modify: `apps/pipeline/src/atr_pipeline/stages/ingest/stage.py`
- Modify: `apps/pipeline/src/atr_pipeline/stages/ingest/manifest_builder.py`
- Modify: `apps/pipeline/src/atr_pipeline/cli/commands/ingest.py`
- Test: `apps/pipeline/tests/unit/stages/ingest/test_image_set_stage.py`
- Test: `apps/pipeline/tests/unit/stages/ingest/test_stage.py`

**Interfaces:**
- Produces: immutable `raw_image` binary artifacts and an image-set `SourceManifestV1`.
- Cache input: `image_set_sha256:<digest>` derived before cache lookup.
- Preserves: PDF `pdf_sha256:<digest>`, raster, embedded-image, and manifest behavior.

- [ ] **Step 1: Write failing stage tests**

Cover raw-image artifact registration, deterministic artifact IDs/manifest
JSON, identical-input cache hits, changed-byte invalidation, missing-input
sentinels, refusal with an empty store, and unchanged PDF cache/fingerprint.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/pipeline/tests/unit/stages/ingest/test_image_set_stage.py apps/pipeline/tests/unit/stages/ingest/test_stage.py -q`

- [ ] **Step 3: Implement dispatch and immutable writes**

Preflight before calling `put_bytes`; after success, register every entry under
`raw_image/page/<deterministic-id>/`, collect relative refs, and build the
source manifest. Bump `IngestStage.version` from `1.2` to `1.3`.

- [ ] **Step 4: Verify GREEN and the complete ingest unit suite**

Run: `uv run pytest apps/pipeline/tests/unit/stages/ingest apps/pipeline/tests/unit/config -q`

- [ ] **Step 5: Commit**

Commit with `S5U-1553: ingest immutable image-set sources` and red-before
evidence.

### Task 5: Committed fixture, CLI proof, and code generation

**Files:**
- Create: `configs/documents/image_set_sample.toml`
- Create: `packages/fixtures/sample_documents/image_set_sample/source/page_0001.png`
- Create: `packages/fixtures/sample_documents/image_set_sample/source/page_0002.png`
- Create: `packages/fixtures/sample_documents/image_set_sample/source/image_set_manifest.json`
- Create: `packages/fixtures/sample_documents/image_set_sample/expected/_annotation_meta.toml`
- Modify: `packages/fixtures/manifest.toml`
- Test: `apps/pipeline/tests/integration/test_image_set_cli.py`
- Generate: `packages/schemas/jsonschema/*.schema.json`
- Generate: `packages/schemas/ts/src/generated/*.ts`

**Interfaces:**
- Provides: a tiny two-page source used by real config loading and `atr ingest`.

- [ ] **Step 1: Generate two tiny deterministic PNG fixtures**

Use Pillow to create fixed 2x2 RGB images, then compute exact SHA-256 values and
write the input manifest/config through reviewed patches.

- [ ] **Step 2: Write and RED-run the CLI integration test**

Patch the fixture config's artifact root and registry location to `tmp_path`,
invoke `atr ingest --doc image_set_sample`, and assert exit zero plus one
immutable raw artifact per page.

Run: `uv run pytest apps/pipeline/tests/integration/test_image_set_cli.py -q`

- [ ] **Step 3: Make the CLI test GREEN and validate fixture inventory**

Run: `uv run python scripts/validate_fixture_manifest.py`

- [ ] **Step 4: Regenerate contracts**

Run: `make codegen`

Run: `make codegen && git diff --exit-code packages/schemas`

- [ ] **Step 5: Commit**

Commit with `S5U-1553: add image-set ingest fixture and generated contracts`
and red-before evidence.

### Task 6: Verification, review, and delivery

**Files:**
- Create: `tmp/review-s5u-1553.md` through independent Path A review.
- No production file is changed unless a gate/reviewer finds a defect.

- [ ] **Step 1: Run focused verification**

Run: `uv run pytest apps/pipeline/tests -k "ingest or source" -q`

Run: `uv run atr ingest --doc image_set_sample`

- [ ] **Step 2: Run the canonical gate**

Run: `make check`

Iterate with a reproducing failing test for every implementation defect until
all checks pass.

- [ ] **Step 3: Audit the branch diff**

Run: `git diff --check` and `git diff main...HEAD`. Remove placeholders,
shortcuts, untracked artifacts, and scope drift.

- [ ] **Step 4: Run independent fresh-eyes review**

Dispatch Path A using `.claude/prompts/review.md` with only issue ID, branch,
and working directory. Resolve every blocking finding and re-review after the
final fix commit.

- [ ] **Step 5: Push and create the draft PR**

Run: `git push -u origin HEAD`.

Run: `gh pr create --draft` with a title beginning `S5U-1553:`, summary,
verification evidence, one-row-per-bullet Coverage table, red-before evidence,
and `Closes S5U-1553`.
