# Image-set Source Foundation Design

**Issue:** S5U-1553

## Goal

Allow photographed book pages to enter the pipeline as a first-class
`image_set` source while preserving the existing PDF configuration, ingest,
fingerprint, raster, and cache behavior.

The change stops at source registration. It does not add crop correction,
orientation correction, OCR, PageIR changes, or reader behavior.

## Source configuration

`DocumentConfig` gains a Pydantic discriminated union whose discriminator is
`source_kind` and whose variants are:

- `pdf`: a source PDF path.
- `image_set`: an image-set manifest path.

The union is the normalized source of truth. A before-validation compatibility
adapter converts today's `document.source_pdf` input into the `pdf` variant.
The compatibility accessor remains available so existing configs and PDF
callers do not need to change. Unknown discriminator values fail during
configuration validation.

The image-set fixture uses an explicit `source_kind = "image_set"`; image-set
ingest is never selected by file-extension inference.

## Image-set manifest contract

The canonical Pydantic `ImageSetManifestV1` contains an ordered `images` list.
Each entry records:

- a stable manifest-provided image ID;
- the source path and declared media type;
- an expected SHA-256 for the raw file bytes;
- an ordered page number/page ID mapping;
- optional typed capture metadata, including capture timestamp, camera make,
  camera model, and EXIF orientation.

Only PNG and JPEG are supported in this foundation. The list order is the page
order. Page numbers must be contiguous from one, page IDs must match the
deterministic `pNNNN` mapping, IDs must be unique, and resolved source paths
must be unique.

The authoritative hash is always recomputed from bytes during ingest and must
match the manifest. Raw-image artifact IDs are deterministic functions of the
page mapping and byte hash, so the same inputs produce the same artifact paths
and manifest JSON.

## Source manifest evolution

`SourceManifestV1` retains `source_pdf_sha256` for compatibility. It also gains
an explicit `source_kind` and image-set-specific fingerprint fields:

- `source_manifest_sha256`: SHA-256 of the canonical input manifest bytes;
- `source_image_set_sha256`: SHA-256 of the ordered page/image identities;
- per-image source entries with image ID, page mapping, media type, SHA-256,
  capture metadata, and immutable raw-artifact reference.

For PDF sources, the new image-set fields are empty and
`source_pdf_sha256` continues to carry the PDF hash. For image sets,
`source_pdf_sha256` remains empty; it is never reused for a different source
kind. Model validation enforces these variant invariants.

## Ingest architecture

`IngestStage` remains the single runner/CLI stage and dispatches internally on
the normalized source union:

1. PDF dispatch executes the existing code path unchanged.
2. Image-set dispatch loads and fully validates every source before writing.
3. Only after preflight succeeds does it register raw bytes through
   `ArtifactStore.put_bytes` and return `SourceManifestV1`.

Image-set preflight is isolated in focused ingest modules so the stage file and
tests remain below the 400-line ceiling. It returns an immutable in-memory plan
containing validated models, resolved paths, bytes, hashes, and target artifact
metadata. No artifact-store method is called during preflight.

The ingest stage version is bumped because image-set dispatch adds observable
artifact writes and changes cache-key composition.

## Path and media safety

Manifest and image paths are checked before filesystem access for null bytes
and traversal components. Paths are then resolved with realpath semantics.
Their resolved targets must remain under the repository/materials allowlist;
absolute paths are accepted only when they resolve under an allowed root.
Symlink escapes therefore fail the same containment check.

Preflight refuses:

- `..` traversal components;
- absolute paths outside allowed roots;
- null bytes;
- unsupported declared or detected media types;
- duplicate image IDs;
- duplicate resolved manifest entries;
- malformed JSON/schema data;
- missing image files;
- SHA-256 mismatches or invalid image bytes;
- non-contiguous or inconsistent ordered page mappings.

All refusals occur before the first artifact write. Tests assert that the
artifact root contains no files after each refusal.

## Cache identity

`IngestStage.extra_cache_inputs` dispatches by source kind:

- PDF: keep the existing `pdf_sha256:<hash>` behavior from S5U-1221.
- Image set: hash the manifest bytes and each ordered raw image byte payload,
  producing an image-set identity before the executor performs cache lookup.

Unchanged inputs therefore hit the existing executor cache. Changing any
image byte changes the ingest cache key and forces a new manifest/artifact
registration. Missing inputs produce stable sentinels so `run()` remains the
authoritative, clear failure point.

## Tests and fixtures

Tests are written red-first and cover:

- legacy `source_pdf` normalization to the PDF union variant;
- unchanged PDF fingerprint and cache-input behavior;
- image-set config and manifest schema round trips;
- unknown `source_kind` rejection;
- deterministic raw-image IDs and byte-identical manifest JSON across runs;
- identical-input cache hit and one-byte cache invalidation;
- CLI ingest success for the committed image-set fixture;
- every path/media/schema/duplicate/missing refusal with an untouched store.

The fixture contains tiny generated PNG files under
`packages/fixtures/sample_documents/`; no photographed or production binary is
committed. Pydantic remains the schema source of truth, and `make codegen`
regenerates JSON Schema and TypeScript outputs.

## Compatibility and scope boundaries

Downstream PDF consumers continue to read `source_pdf_sha256`; registry/run
provenance remains PDF-compatible in this PR. Image-set provenance lives in the
source manifest until a later epic task deliberately extends downstream
extraction/run models.

No new third-party dependency is introduced. Pillow is used only for media
verification and metadata extraction. No OCR, crop, rectification, PageIR,
golden extraction output, web code, or visual snapshot changes are included.
