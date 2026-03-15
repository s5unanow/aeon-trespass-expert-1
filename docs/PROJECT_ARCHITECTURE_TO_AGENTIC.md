Assumptions used for this implementation package

No major flaw was found in the prior recommendation. This package stays consistent with the same IR-first modular monolith architecture.

The repo uses:

Python workspace package: atr_pipeline

shared schema package: atr_schemas

frontend workspace package: @atr/web

shared TS schema package: @atr/schemas

The first walking skeleton uses a single checked-in sample page under walking_skeleton. If redistribution of a real rulebook page is risky, use a synthetic page with the same layout characteristics.

All paths below are relative to repo root.

packages/schemas/** is the canonical contract source. packages/schemas/jsonschema/** and packages/schemas/ts/src/generated/** are generated outputs.

1. Repo scaffold

repo/
  README.md
  LICENSE
  Makefile
  pyproject.toml
  uv.lock
  package.json
  pnpm-workspace.yaml
  pnpm-lock.yaml
  .python-version
  .nvmrc
  .gitignore
  .gitattributes
  .editorconfig
  .pre-commit-config.yaml
  .prettierrc.json
  .eslintrc.cjs

  artifacts/
    .gitignore

  var/
    .gitkeep

  .github/
    workflows/
      ci.yml
      python-tests.yml
      web-tests.yml
      visual-regression.yml

  configs/
    base.toml
    ci.toml
    local.example.toml
    documents/
      ato_core_v1_1.toml
      walking_skeleton.toml
    extraction/
      native.toml
      layout.toml
      ocr.toml
    translation/
      style_guide.ru.toml
      model_profiles.toml
    symbols/
      ato_core_v1_1.symbols.toml
      walking_skeleton.symbols.toml
    qa/
      thresholds.toml
      waivers.toml

  docs/
    architecture/
      overview.md
      data-model.md
      stage-runner.md
      render-model.md
      hard-page-routing.md
    runbooks/
      local-dev.md
      build-document.md
      review-hard-pages.md
      release.md
      add-new-symbol.md
    specs/
      walking-skeleton.md
      symbol-catalog.md
      translation-contracts.md
      qa-gates.md
      frontend-rendering.md
    adrs/
      ADR-001-ir-first-canonical-state.md
      ADR-002-markdown-not-source-of-truth.md
      ADR-003-immutable-artifacts-and-patches.md
      ADR-004-pymupdf-as-native-pdf-extractor.md
      ADR-005-docling-as-layout-evidence.md
      ADR-006-symbol-catalog-and-template-matching.md
      ADR-007-structured-translation-contracts.md
      ADR-008-static-react-reader.md
      ADR-009-no-workflow-orchestrator-v1.md
      ADR-010-qa-is-release-blocking.md
      ADR-011-shared-schemas-generated-to-jsonschema-and-ts.md
      ADR-012-build-english-source-edition-first.md

  scripts/
    bootstrap_repo.sh
    bootstrap_fixtures.py
    generate_jsonschema.py
    generate_ts_types.mjs
    validate_fixture_artifacts.py
    import_symbol_catalog.py
    run_walking_skeleton.sh
    build_release.sh
    clean_artifacts.sh

  packages/
    schemas/
      README.md
      python/
        atr_schemas/
          __init__.py
          common.py
          enums.py
          source_manifest_v1.py
          native_page_v1.py
          layout_page_v1.py
          asset_v1.py
          symbol_catalog_v1.py
          symbol_match_set_v1.py
          page_ir_v1.py
          concept_registry_v1.py
          translation_batch_v1.py
          translation_result_v1.py
          render_page_v1.py
          glossary_payload_v1.py
          search_docs_v1.py
          qa_record_v1.py
          qa_summary_v1.py
          run_manifest_v1.py
          patch_set_v1.py
          build_manifest_v1.py
      jsonschema/
        source_manifest_v1.schema.json
        native_page_v1.schema.json
        layout_page_v1.schema.json
        asset_v1.schema.json
        symbol_catalog_v1.schema.json
        symbol_match_set_v1.schema.json
        page_ir_v1.schema.json
        concept_registry_v1.schema.json
        translation_batch_v1.schema.json
        translation_result_v1.schema.json
        render_page_v1.schema.json
        glossary_payload_v1.schema.json
        search_docs_v1.schema.json
        qa_record_v1.schema.json
        qa_summary_v1.schema.json
        run_manifest_v1.schema.json
        patch_set_v1.schema.json
        build_manifest_v1.schema.json
      ts/
        package.json
        tsconfig.json
        src/
          index.ts
          generated/
            source_manifest_v1.ts
            native_page_v1.ts
            layout_page_v1.ts
            asset_v1.ts
            symbol_catalog_v1.ts
            symbol_match_set_v1.ts
            page_ir_v1.ts
            concept_registry_v1.ts
            translation_batch_v1.ts
            translation_result_v1.ts
            render_page_v1.ts
            glossary_payload_v1.ts
            search_docs_v1.ts
            qa_record_v1.ts
            qa_summary_v1.ts
            run_manifest_v1.ts
            patch_set_v1.ts
            build_manifest_v1.ts

    prompts/
      README.md
      system/
        shared_constraints.md
      translate/
        translate_rules_ru.v1.md
        repair_rules_ru.v1.md
      adjudicate/
        reading_order.v1.md
        table_shape.v1.md
      metadata/
        translate_rules_ru.v1.yaml
        repair_rules_ru.v1.yaml
        reading_order.v1.yaml

    fixtures/
      README.md
      sample_documents/
        walking_skeleton/
          source/
            sample_page_01.pdf
            sample_page_01.png
            symbol_progress.png
            source_notes.md
          expected/
            source_manifest.json
            native_page.p0001.json
            layout_page.p0001.json
            symbol_matches.p0001.json
            page_ir.en.p0001.json
            translation_batch.p0001.json
            translation_result.p0001.json
            page_ir.ru.p0001.json
            render_page.p0001.json
            glossary_payload.json
            search_docs.jsonl
            qa_summary.json
          catalogs/
            walking_skeleton.symbols.toml
          patches/
            source/
              .gitkeep
            target/
              .gitkeep
      sample_pages/
        single_column/
          page_0001.pdf
          notes.md
        multi_column/
          page_0114.pdf
          notes.md
        icon_dense/
          page_0042.pdf
          notes.md
        tables_callouts/
          page_0071.pdf
          notes.md
        low_confidence/
          page_0128.pdf
          notes.md

    qa_assets/
      README.md
      playwright_baselines/
        reader-page.spec.ts-snapshots/
          walking-skeleton-linux.png
      storybook_snapshots/
        heading-block-default.png
        paragraph-with-icon.png
      overlays/
        walking_skeleton/
          p0001-zones.png
          p0001-symbols.png
      axe_reports/
        walking_skeleton.reader-page.json

  sample-data/
    walking_skeleton/
      README.md
      expected_release/
        manifest.json
        data/
          render_page.p0001.json
          nav.json
          glossary.json
          search_docs.jsonl

  apps/
    pipeline/
      README.md
      pyproject.toml
      src/
        atr_pipeline/
          __init__.py
          version.py

          cli/
            __init__.py
            main.py
            commands/
              ingest.py
              run.py
              qa.py
              review.py
              release.py

          config/
            __init__.py
            models.py
            loader.py

          runner/
            __init__.py
            stage_protocol.py
            stage_context.py
            plan.py
            executor.py
            cache_keys.py
            result.py

          store/
            __init__.py
            artifact_store.py
            artifact_ref.py
            pathing.py
            atomic_write.py

          registry/
            __init__.py
            db.py
            migrations.py
            runs.py
            events.py

          logging/
            __init__.py
            setup.py

          utils/
            __init__.py
            hashing.py
            json_io.py
            file_io.py
            ids.py
            rects.py
            images.py

          services/
            __init__.py
            pdf/
              __init__.py
              rasterizer.py
            llm/
              __init__.py
              base.py
              mock_translator.py
              openai_adapter.py
              anthropic_adapter.py

          stages/
            __init__.py

            ingest/
              __init__.py
              stage.py
              pdf_fingerprint.py
              manifest_builder.py

            extract_native/
              __init__.py
              stage.py
              pymupdf_extractor.py
              normalizer.py

            extract_layout/
              __init__.py
              stage.py
              docling_adapter.py
              difficulty_score.py
              fallback_stub.py

            symbols/
              __init__.py
              stage.py
              catalog_loader.py
              matcher.py
              anchor_inline.py

            structure/
              __init__.py
              stage.py
              furniture.py
              block_builder.py
              reading_order.py
              heuristics.py

            translation/
              __init__.py
              stage.py
              planner.py
              validator.py
              enforcer.py
              tm.py

            render/
              __init__.py
              stage.py
              page_builder.py
              nav_builder.py
              glossary_builder.py
              search_builder.py

            qa/
              __init__.py
              stage.py
              report_builder.py
              rules/
                __init__.py
                schema_validation_rule.py
                icon_count_rule.py
                source_trace_rule.py

            publish/
              __init__.py
              stage.py
              bundle_builder.py

          review/
            __init__.py
            overlay_builder.py
            pack_builder.py

      tests/
        contract/
          test_schema_roundtrip.py
        unit/
          config/
            test_loader.py
          runner/
            test_cache_keys.py
            test_executor.py
          store/
            test_artifact_store.py
          registry/
            test_db.py
          stages/
            ingest/
              test_stage.py
            extract_native/
              test_pymupdf_extractor.py
            symbols/
              test_matcher.py
            translation/
              test_planner.py
              test_validator.py
            render/
              test_page_builder.py
            qa/
              test_icon_count_rule.py
        integration/
          test_cli_smoke.py
          test_walking_skeleton_pipeline.py

    web/
      README.md
      package.json
      tsconfig.json
      tsconfig.node.json
      vite.config.ts
      vitest.config.ts
      playwright.config.ts

      .storybook/
        main.ts
        preview.ts

      public/
        documents/
          walking_skeleton/
            manifest.json
            data/
              render_page.p0001.json
              nav.json
              glossary.json
              search_docs.jsonl

      src/
        main.tsx
        app/
          App.tsx
          router.tsx
        routes/
          DocumentIndexPage.tsx
          ReaderPage.tsx
          GlossaryPage.tsx
          SearchPage.tsx
        components/
          reader/
            BlockRenderer.tsx
            InlineRenderer.tsx
            HeadingBlock.tsx
            ParagraphBlock.tsx
            IconInline.tsx
            FigureBlock.tsx
          nav/
            TocTree.tsx
            PrevNextNav.tsx
            Breadcrumbs.tsx
            SourcePageBadge.tsx
          glossary/
            GlossaryCard.tsx
            GlossaryDrawer.tsx
            GlossaryIndex.tsx
          search/
            SearchDialog.tsx
            SearchResults.tsx
        lib/
          api/
            loadManifest.ts
            loadRenderPage.ts
            loadGlossary.ts
          render/
            blockTypes.ts
            inlineTypes.ts
          search/
            createMiniSearch.ts
          schemas/
            index.ts
        styles/
          reset.css
          tokens.css
          app.css
          reader.css
        stories/
          reader/
            HeadingBlock.stories.tsx
            ParagraphBlock.stories.tsx
            ReaderPage.stories.tsx
      tests/
        component/
          BlockRenderer.test.tsx
          ReaderPage.test.tsx
        e2e/
          reader-page.spec.ts
        visual/
          block-renderer.spec.ts

Generated vs hand-edited

Generated:

packages/schemas/jsonschema/**

packages/schemas/ts/src/generated/**

Hand-edited:

everything else

2. File-by-file starter plan
2.1 Backbone files
File path	Purpose	What should exist in it	Key interfaces / types / functions	Dependencies	Test files
pyproject.toml	Root Python workspace and tooling	uv workspace config, Python version, lint/test tool configs	workspace members, pytest/ruff/mypy config	none	apps/pipeline/tests/integration/test_cli_smoke.py
package.json	Root JS workspace orchestration	workspace scripts: lint, test, build, codegen:schemas	root scripts only	pnpm-workspace.yaml	CI workflow
configs/base.toml	Global defaults	artifact root, logging, default parallelism, default stage names	config sections used by loader	apps/pipeline/src/atr_pipeline/config/models.py	apps/pipeline/tests/unit/config/test_loader.py
configs/documents/walking_skeleton.toml	First runnable document config	document id, source PDF path, symbol catalog path, target langs, stop stage	DocumentBuildConfig fields	base config, schemas	apps/pipeline/tests/unit/config/test_loader.py
packages/schemas/python/atr_schemas/common.py	Shared primitives	Rect, ArtifactRef, ConfidenceScore, ProvenanceRef, id aliases	Pydantic base models and validators	Pydantic	apps/pipeline/tests/contract/test_schema_roundtrip.py
packages/schemas/python/atr_schemas/enums.py	Common enums	BlockType, InlineType, AssetKind, Severity, LanguageCode	enum classes	common.py	test_schema_roundtrip.py
scripts/generate_jsonschema.py	Contract codegen	load Pydantic models, emit JSON Schema files deterministically	generate_all_schemas()	packages/schemas/python/**	test_schema_roundtrip.py
packages/schemas/ts/src/index.ts	TS schema export barrel	exports generated types and helpers	export * from "./generated/...";	generated TS files	apps/web/tests/component/ReaderPage.test.tsx
2.2 Pipeline runtime files
File path	Purpose	What should exist in it	Key interfaces / types / functions	Dependencies	Test files
apps/pipeline/src/atr_pipeline/runner/stage_protocol.py	Canonical stage contract	Stage protocol, scope enum, stage metadata	Stage.run(ctx, input) -> output	shared schemas, config	tests/unit/runner/test_executor.py
apps/pipeline/src/atr_pipeline/runner/stage_context.py	Per-invocation context	run id, document id, logger, config, artifact store, registry handles	StageContext dataclass	config, store, registry	tests/unit/runner/test_executor.py
apps/pipeline/src/atr_pipeline/runner/cache_keys.py	Idempotent caching	stable content-addressed cache key builder	build_cache_key()	hashing utils, config	tests/unit/runner/test_cache_keys.py
apps/pipeline/src/atr_pipeline/store/artifact_store.py	Immutable artifact storage	path resolution, atomic write, read, exists, list refs	ArtifactStore.put_json(), get_json(), has()	atomic_write.py, pathing.py	tests/unit/store/test_artifact_store.py
apps/pipeline/src/atr_pipeline/registry/db.py	SQLite registry	connection bootstrap, migrations, row factories	open_registry(), run_migrations()	sqlite3	tests/unit/registry/test_db.py
apps/pipeline/src/atr_pipeline/cli/main.py	Main Typer entrypoint	root app and command registration	app = typer.Typer()	command modules	tests/integration/test_cli_smoke.py
apps/pipeline/src/atr_pipeline/config/models.py	Typed config models	DocumentBuildConfig, PipelineConfig, nested extract/qa config	Pydantic models	common.py	tests/unit/config/test_loader.py
apps/pipeline/src/atr_pipeline/config/loader.py	Config merge and validation	load base + env + document config, resolve paths	load_document_config()	models.py, TOML parser	tests/unit/config/test_loader.py
2.3 Walking skeleton backend files
File path	Purpose	What should exist in it	Key interfaces / types / functions	Dependencies	Test files
apps/pipeline/src/atr_pipeline/stages/ingest/stage.py	Create SourceManifestV1 and raster refs	stage class, inputless doc-scoped run, manifest write	IngestStage	config, artifact store, rasterizer	tests/unit/stages/ingest/test_stage.py
apps/pipeline/src/atr_pipeline/services/pdf/rasterizer.py	Page rasterization	render PDF pages to PNG at configured DPI	render_page_pngs()	PyMuPDF	tests/unit/stages/ingest/test_stage.py
packages/schemas/python/atr_schemas/source_manifest_v1.py	Source manifest schema	document metadata, page list, source hashes	SourceManifestV1	common.py	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/extract_native/pymupdf_extractor.py	Native PDF evidence extractor	words, spans, image blocks, page dims	extract_native_page()	PyMuPDF, NativePageV1	tests/unit/stages/extract_native/test_pymupdf_extractor.py
packages/schemas/python/atr_schemas/native_page_v1.py	Native page evidence schema	words, spans, image refs, fonts, extraction metadata	NativePageV1	common.py, AssetV1	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/symbols/matcher.py	Deterministic symbol matching	template matching against sample icon, score filtering	match_symbols()	OpenCV, symbol catalog, raster image	tests/unit/stages/symbols/test_matcher.py
packages/schemas/python/atr_schemas/symbol_catalog_v1.py	Symbol catalog contract	symbol definitions, templates, thresholds, alt labels	SymbolCatalogV1	common.py	test_schema_roundtrip.py
packages/schemas/python/atr_schemas/symbol_match_set_v1.py	Symbol match output schema	matches with page ids, bboxes, score, source asset refs	SymbolMatchSetV1	common.py	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/structure/block_builder.py	Build PageIRV1 for simple pages	heading + paragraph block construction, inline icon insertion	build_page_ir_simple()	NativePageV1, SymbolMatchSetV1, PageIRV1	tests/integration/test_walking_skeleton_pipeline.py
packages/schemas/python/atr_schemas/page_ir_v1.py	Canonical content IR	block unions, inline unions, reading order, provenance	PageIRV1 and block/inline models	common.py, enums.py	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/translation/planner.py	Translation job builder	convert EN blocks to TranslationBatchV1	build_translation_batch()	PageIRV1, concept registry	tests/unit/stages/translation/test_planner.py
apps/pipeline/src/atr_pipeline/services/llm/mock_translator.py	Mock translation provider	deterministic fixture-backed translation adapter	MockTranslator.translate_batch()	TranslationBatchV1, TranslationResultV1	tests/unit/stages/translation/test_validator.py
packages/schemas/python/atr_schemas/translation_batch_v1.py	Translation input contract	segments, context, required concepts, locked nodes	TranslationBatchV1	common.py	test_schema_roundtrip.py
packages/schemas/python/atr_schemas/translation_result_v1.py	Translation output contract	target inline nodes and concept realizations	TranslationResultV1	common.py	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/render/page_builder.py	Build frontend payload	map RU PageIRV1 to RenderPageV1	build_render_page()	PageIRV1, asset refs	tests/unit/stages/render/test_page_builder.py
packages/schemas/python/atr_schemas/render_page_v1.py	Frontend contract	route metadata, blocks, figures, glossary mentions, source map	RenderPageV1	common.py, PageIRV1	test_schema_roundtrip.py
apps/pipeline/src/atr_pipeline/stages/qa/rules/icon_count_rule.py	First blocking QA rule	compare icon counts across source IR, target IR, render payload	evaluate_icon_count()	PageIRV1, RenderPageV1, QARecordV1	tests/unit/stages/qa/test_icon_count_rule.py
packages/schemas/python/atr_schemas/qa_record_v1.py	Machine-readable QA record	code, severity, entity ref, expected/actual, evidence refs	QARecordV1	common.py	test_schema_roundtrip.py
2.4 Frontend walking skeleton files
File path	Purpose	What should exist in it	Key interfaces / types / functions	Dependencies	Test files
apps/web/src/lib/api/loadRenderPage.ts	Load typed page payload	fetch JSON, validate shape, return RenderPageV1	loadRenderPage(documentId, pageId)	@atr/schemas	tests/component/ReaderPage.test.tsx
apps/web/src/components/reader/BlockRenderer.tsx	Central typed renderer	switch by block kind and delegate to block components	BlockRenderer React component	RenderPageV1 types	tests/component/BlockRenderer.test.tsx
apps/web/src/components/reader/IconInline.tsx	Inline icon renderer	icon asset selection, alt/aria behavior	IconInline	render types, CSS	tests/component/BlockRenderer.test.tsx
apps/web/src/routes/ReaderPage.tsx	Page route	load data, render heading/paragraph/icon, prev/next placeholder	ReaderPage	loadRenderPage, BlockRenderer	tests/component/ReaderPage.test.tsx, tests/e2e/reader-page.spec.ts
apps/web/tests/e2e/reader-page.spec.ts	Browser smoke + visual snapshot	open page, assert content, take baseline snapshot	Playwright test	public sample data	Playwright runner
apps/web/.storybook/preview.ts	Deterministic visual environment	disable animations, set stable fonts/styles	Storybook preview config	CSS	tests/visual/block-renderer.spec.ts
2.5 Fixture and prompt files
File path	Purpose	What should exist in it	Key interfaces / types / functions	Dependencies	Test files
packages/fixtures/sample_documents/walking_skeleton/source/source_notes.md	Fixture provenance	where sample came from, what text/icon it contains	plain markdown doc	none	manual reference
packages/fixtures/sample_documents/walking_skeleton/expected/page_ir.en.p0001.json	Golden IR	expected English canonical page IR	valid PageIRV1 JSON	schema package	tests/integration/test_walking_skeleton_pipeline.py
packages/fixtures/sample_documents/walking_skeleton/expected/render_page.p0001.json	Golden frontend payload	expected render page JSON	valid RenderPageV1 JSON	schema package	tests/integration/test_walking_skeleton_pipeline.py, frontend tests
packages/prompts/translate/translate_rules_ru.v1.md	Real translation prompt profile	frontmatter + rules for structured output	prompt metadata header, deterministic instructions	translation schemas	later provider integration tests
packages/prompts/metadata/translate_rules_ru.v1.yaml	Prompt registry metadata	prompt id, allowed models, input/output schemas	YAML metadata	prompt file	provider adapter tests
3. Spec Kit task tree
Below is the task tree sized for coding agents. Each task is bounded, file-scoped, and architecture-safe.

Epic 1 — Repository foundation and shared contracts
Feature 1.1 — Monorepo bootstrap
Task 1.1.1 — Initialize workspace and toolchain

Objective: Create the root repo structure, workspaces, lockfiles, and base scripts.

Why it exists: All later tasks assume stable root tooling and directory conventions.

Dependencies: none

Files to create/update: pyproject.toml, package.json, pnpm-workspace.yaml, Makefile, .pre-commit-config.yaml, .python-version, .nvmrc, root directories from scaffold

Acceptance criteria:

uv sync succeeds

pnpm install succeeds

make lint, make test, make codegen exist as no-op or stub commands

Test requirements: CI smoke workflow runs successfully on an empty implementation skeleton

Definition of done: repo boots on a clean machine without manual setup beyond uv and pnpm

Task 1.1.2 — Add base CI, lint, and formatting

Objective: Wire GitHub Actions and local tooling for Python and TypeScript checks.

Why it exists: Prevents early repo drift and schema/runtime breakage.

Dependencies: Task 1.1.1

Files to create/update: .github/workflows/*.yml, .eslintrc.cjs, .prettierrc.json, pyproject.toml

Acceptance criteria:

Python lint/type/test jobs exist

Web lint/test jobs exist

generated-schema check exists

Test requirements: CI workflow files validate; local lint commands execute

Definition of done: pull requests can fail on formatting/type/schema issues

Feature 1.2 — Shared schemas
Task 1.2.1 — Define common primitives and core v1 models

Objective: Create the first canonical Pydantic schemas used by both pipeline and frontend.

Why it exists: Agents cannot work in parallel without stable contracts.

Dependencies: Task 1.1.1

Files to create/update: packages/schemas/python/atr_schemas/common.py, enums.py, source_manifest_v1.py, native_page_v1.py, page_ir_v1.py, render_page_v1.py, qa_record_v1.py

Acceptance criteria:

models import cleanly

discriminated unions validate for blocks and inline nodes

fixture JSON validates against schemas

Test requirements: schema roundtrip tests for each model

Definition of done: contract package is importable and serializes deterministically

Task 1.2.2 — Generate JSON Schema and TypeScript types

Objective: Add deterministic codegen from Python schemas to JSON Schema and TS.

Why it exists: Frontend must consume the same contracts, not hand-copied shapes.

Dependencies: Task 1.2.1

Files to create/update: scripts/generate_jsonschema.py, scripts/generate_ts_types.mjs, packages/schemas/jsonschema/**, packages/schemas/ts/**

Acceptance criteria:

one command regenerates all schema artifacts

CI fails if generated files are stale

Test requirements: generated TS compiles; JSON schemas validate sample artifacts

Definition of done: schema updates propagate to both Python and TS consistently

Feature 1.3 — Config and architectural guardrails
Task 1.3.1 — Implement typed config loader

Objective: Create layered TOML config loading for base, env, and document configs.

Why it exists: Every stage and CLI command depends on a stable config contract.

Dependencies: Task 1.2.1

Files to create/update: configs/base.toml, configs/ci.toml, configs/documents/walking_skeleton.toml, apps/pipeline/src/atr_pipeline/config/models.py, loader.py

Acceptance criteria:

config resolves paths relative to repo root

document config overrides base config cleanly

invalid config fails with actionable error

Test requirements: unit tests for merge order, path resolution, validation failures

Definition of done: load_document_config("walking_skeleton") returns a fully typed config object

Task 1.3.2 — Seed ADR and spec docs

Objective: Create the initial ADR set and walking skeleton spec.

Why it exists: Agents need explicit architecture boundaries before coding deeper modules.

Dependencies: Task 1.1.1

Files to create/update: docs/adrs/ADR-001...ADR-012, docs/specs/walking-skeleton.md

Acceptance criteria:

first 8 ADRs exist with decisions and rationale

walking skeleton spec names exact fixtures and outputs

Test requirements: none

Definition of done: repo documents answer “what is canonical?” and “what is the first end-to-end slice?”

Epic 2 — Pipeline runtime backbone
Feature 2.1 — Immutable artifact lifecycle
Task 2.1.1 — Implement artifact store

Objective: Build immutable artifact write/read/pathing with atomic commits.

Why it exists: Idempotency and replay depend on this more than any later stage.

Dependencies: Tasks 1.2.1, 1.3.1

Files to create/update: store/artifact_store.py, artifact_ref.py, pathing.py, atomic_write.py

Acceptance criteria:

artifacts are addressed by schema family/scope/id/input hash

partial writes never become visible

duplicate writes with same key return same ref

Test requirements: atomic write test, cache hit test, corrupt temp cleanup test

Definition of done: stages can persist typed artifacts safely

Task 2.1.2 — Implement SQLite run registry

Objective: Track runs, stage invocations, timings, and QA summaries in SQLite.

Why it exists: Debugging and replay require operational metadata outside artifact files.

Dependencies: Task 2.1.1

Files to create/update: registry/db.py, migrations.py, runs.py, events.py

Acceptance criteria:

migrations bootstrap cleanly

run start/finish and stage events are persisted

run lookup by document id works

Test requirements: migration test, insert/read test, transaction rollback test

Definition of done: every pipeline invocation leaves a durable registry record

Feature 2.2 — Stage execution
Task 2.2.1 — Define stage protocol and executor

Objective: Create the stage abstraction, stage context, and executor loop.

Why it exists: Every module after this plugs into the same deterministic execution model.

Dependencies: Tasks 2.1.1, 2.1.2

Files to create/update: runner/stage_protocol.py, stage_context.py, executor.py, cache_keys.py, result.py

Acceptance criteria:

executor resolves input artifacts

executor computes deterministic cache keys

executor skips unchanged work

Test requirements: executor unit tests, cache key stability tests

Definition of done: a trivial stage can run through the full runtime and hit cache on rerun

Task 2.2.2 — Add Typer CLI and command surface

Objective: Expose ingest, run, qa, and release commands.

Why it exists: Agents and humans need a stable operational entrypoint.

Dependencies: Task 2.2.1

Files to create/update: cli/main.py, cli/commands/*.py

Acceptance criteria:

atr run --doc walking_skeleton --to qa works

command help text is accurate

failures return non-zero exit codes

Test requirements: CLI smoke integration test

Definition of done: the pipeline can be driven from the command line without Python module imports
Epic 3 — Core extraction backbone
Feature 3.1 — Ingest
Task 3.1.1 — Implement source manifest stage

Objective: Fingerprint the source PDF, enumerate pages, and write SourceManifestV1.

Why it exists: All downstream work keys off a stable document manifest.

Dependencies: Tasks 1.2.1, 2.2.1

Files to create/update: stages/ingest/stage.py, pdf_fingerprint.py, manifest_builder.py, source_manifest_v1.py

Acceptance criteria:

manifest includes document hash and page metadata

page ids are stable (p0001, etc.)

rerun produces identical output for same input

Test requirements: unit test with sample PDF

Definition of done: ingest stage emits a valid manifest artifact

Task 3.1.2 — Implement page rasterization helper

Objective: Render page PNGs for layout analysis and symbol matching.

Why it exists: later stages need deterministic raster images.

Dependencies: Task 3.1.1

Files to create/update: services/pdf/rasterizer.py, update ingest stage

Acceptance criteria:

page PNGs are written once per page

file paths are stored in manifest or artifact refs

DPI is config-driven

Test requirements: render output existence and size sanity checks

Definition of done: every ingested page has a stable raster ref

Feature 3.2 — Native extraction
Task 3.2.1 — Implement PyMuPDF native extractor

Objective: Extract words, spans, image blocks, fonts, and page dimensions.

Why it exists: native PDF evidence is the primary text truth source.

Dependencies: Tasks 3.1.1, 3.1.2

Files to create/update: stages/extract_native/pymupdf_extractor.py, normalizer.py, native_page_v1.py

Acceptance criteria:

sample page yields stable word and image counts

all bboxes lie within page bounds

extracted evidence serializes into NativePageV1

Test requirements: golden test against walking skeleton expected JSON

Definition of done: one page can be extracted into native evidence deterministically

Feature 3.3 — Layout evidence
Task 3.3.1 — Implement Docling adapter and difficulty score

Objective: Add layout zones and a per-page difficulty classifier.

Why it exists: complex pages need routing and structure hints even if not used in the skeleton.

Dependencies: Tasks 3.1.2, 3.2.1

Files to create/update: stages/extract_layout/docling_adapter.py, difficulty_score.py, layout_page_v1.py

Acceptance criteria:

adapter can return zones for a simple fixture

missing adapter/runtime degrades cleanly to stub result

difficulty score is persisted

Test requirements: unit tests with stubbed layout output

Definition of done: the contract exists and simple pages produce layout artifacts without blocking the skeleton

Epic 4 — Symbols and structure
Feature 4.1 — Symbol catalog
Task 4.1.1 — Implement symbol catalog schema and loader

Objective: Define the symbol catalog format and load the walking skeleton catalog.

Why it exists: icons must be first-class data, not string hacks.

Dependencies: Tasks 1.2.1, 1.3.1

Files to create/update: symbol_catalog_v1.py, stages/symbols/catalog_loader.py, configs/symbols/walking_skeleton.symbols.toml

Acceptance criteria:

catalog loads one symbol entry for sym.progress

template asset path resolves

catalog schema validates

Test requirements: loader test and schema validation test

Definition of done: symbol catalog can be consumed by matcher stage

Task 4.1.2 — Implement deterministic template matcher

Objective: Detect one inline symbol on the sample page and emit SymbolMatchSetV1.

Why it exists: this proves the architecture solves the core icon-loss problem.

Dependencies: Tasks 3.1.2, 4.1.1

Files to create/update: stages/symbols/matcher.py, stages/symbols/stage.py, symbol_match_set_v1.py

Acceptance criteria:

one match for sym.progress is found on sample page

bbox and confidence are persisted

no duplicate matches

Test requirements: matcher golden test on walking skeleton image

Definition of done: icon recovery works without regex reinjection

Feature 4.2 — Structure recovery
Task 4.2.1 — Implement repeated furniture detector

Objective: Create the document-level detector for repeated headers/footers.

Why it exists: furniture contamination is a known systemic failure.

Dependencies: Task 3.2.1

Files to create/update: stages/structure/furniture.py

Acceptance criteria:

module exists with deterministic API

walking skeleton simple page passes through unchanged

future multi-page fixtures can mark repeated regions

Test requirements: unit tests for pass-through behavior and synthetic repeated footer case

Definition of done: structure stage can call furniture detection without special-casing later

Task 4.2.2 — Implement simple-page block builder and reading order

Objective: Build PageIRV1(en) from native text plus symbol matches for single-column pages.

Why it exists: this is the first usable English canonical IR.

Dependencies: Tasks 3.2.1, 4.1.2, 4.2.1

Files to create/update: stages/structure/block_builder.py, reading_order.py, heuristics.py, page_ir_v1.py

Acceptance criteria:

heading block and paragraph block are emitted

inline icon node is inserted in the correct position

reading order is complete and stable

Test requirements: integration test against page_ir.en.p0001.json

Definition of done: English source page IR matches the golden fixture

Epic 5 — Translation subsystem
Feature 5.1 — Glossary and translation memory
Task 5.1.1 — Implement concept registry contract and sample concept

Objective: Create ConceptRegistryV1 and a sample concept.progress.

Why it exists: translation contracts require concept-aware terms from day one.

Dependencies: Task 1.2.1

Files to create/update: concept_registry_v1.py, configs/translation/style_guide.ru.toml, sample glossary data file

Acceptance criteria:

concept.progress exists with preferred RU forms

concept registry validates and loads

Test requirements: concept registry schema test

Definition of done: translation planner can attach required concepts to a segment

Task 5.1.2 — Implement translation planner and mock provider

Objective: Build TranslationBatchV1 from PageIRV1(en) and return deterministic fixture-backed RU output.

Why it exists: proves structured translation without external providers.

Dependencies: Tasks 4.2.2, 5.1.1

Files to create/update: translation_batch_v1.py, translation_result_v1.py, stages/translation/planner.py, services/llm/mock_translator.py, stages/translation/validator.py

Acceptance criteria:

one paragraph segment is produced

mock translator returns one valid RU paragraph with preserved icon node

validator rejects icon count changes

Test requirements: planner unit test, validator unit test, integration against expected RU fixture

Definition of done: the walking skeleton has a valid PageIRV1(ru) without calling an external model

Task 5.1.3 — Add real provider adapter scaffolding

Objective: Create provider interfaces and placeholder adapters for OpenAI and Anthropic.

Why it exists: later translation work should plug into a stable abstraction without changing the planner.

Dependencies: Task 5.1.2

Files to create/update: services/llm/base.py, openai_adapter.py, anthropic_adapter.py, packages/prompts/**

Acceptance criteria:

base adapter interface exists

real adapters can be instantiated but may remain disabled in CI

prompt metadata binds input/output schemas

Test requirements: adapter construction tests with mocked HTTP layer

Definition of done: live providers are a drop-in later, not a redesign

Epic 6 — Render model and frontend
Feature 6.1 — Render artifact build
Task 6.1.1 — Implement render page builder

Objective: Map RU page IR into RenderPageV1.

Why it exists: frontend should only read render artifacts, never raw IR.

Dependencies: Task 5.1.2

Files to create/update: stages/render/page_builder.py, render_page_v1.py

Acceptance criteria:

output contains page metadata, one heading, one paragraph, one icon

schema validates

source map points back to source block ids

Test requirements: unit test against render_page.p0001.json

Definition of done: a valid frontend page payload exists for the sample page

Task 6.1.2 — Implement nav, glossary, and search payload builders

Objective: Build the minimal companion payloads required by the frontend.

Why it exists: even the first page route should load manifest, nav, glossary, and search docs consistently.

Dependencies: Task 6.1.1

Files to create/update: nav_builder.py, glossary_builder.py, search_builder.py, related schema files

Acceptance criteria:

one-page nav payload exists

glossary includes concept.progress

search docs include Russian text

Test requirements: unit tests for payload generation

Definition of done: sample release data folder can be generated fully

Feature 6.2 — Web reader
Task 6.2.1 — Implement typed data loading

Objective: Load render artifacts in the React app with runtime validation.

Why it exists: frontend must fail loudly on contract mismatch.

Dependencies: Tasks 1.2.2, 6.1.1

Files to create/update: apps/web/src/lib/api/loadManifest.ts, loadRenderPage.ts, loadGlossary.ts, lib/schemas/index.ts

Acceptance criteria:

page route fetches JSON from public/documents/walking_skeleton

invalid JSON throws a typed error

Test requirements: component tests with mocked fetch

Definition of done: frontend can load sample data from static assets

Task 6.2.2 — Implement reader route and block renderer

Objective: Render heading, paragraph text, and inline icon from RenderPageV1.

Why it exists: this is the first visible proof that the typed render model works.

Dependencies: Tasks 6.1.1, 6.2.1

Files to create/update: routes/ReaderPage.tsx, components/reader/*.tsx, styles/reader.css

Acceptance criteria:

reader page shows heading and paragraph

icon is visible inline

source page badge renders

Test requirements: component tests and one Playwright smoke test

Definition of done: visiting the reader route renders the sample page correctly

Task 6.2.3 — Add Storybook stories for core blocks

Objective: Create stable isolated fixtures for heading, paragraph, and paragraph-with-icon.

Why it exists: visual regression should not depend only on the full app route.

Dependencies: Task 6.2.2

Files to create/update: .storybook/*, stories/reader/*.stories.tsx

Acceptance criteria:

stories render without app router dependencies

paragraph-with-icon story uses sample render data

Test requirements: visual snapshot for at least one story

Definition of done: component-level visual QA baseline exists

Epic 7 — QA, review, and publish
Feature 7.1 — Core QA
Task 7.1.1 — Implement schema validation and icon count rules

Objective: Add the first blocking QA rules for the walking skeleton.

Why it exists: QA must be built with the pipeline, not bolted on later.

Dependencies: Tasks 5.1.2, 6.1.1

Files to create/update: stages/qa/rules/schema_validation_rule.py, icon_count_rule.py, qa_record_v1.py, qa_summary_v1.py, report_builder.py

Acceptance criteria:

invalid render page fails schema QA

icon count mismatch raises blocking error

summary artifact is written

Test requirements: rule unit tests and integration test with an intentionally broken fixture

Definition of done: atr qa --doc walking_skeleton produces machine-readable blocking results

Task 7.1.2 — Implement review pack scaffolding

Objective: Create basic overlay and report outputs for failed pages.

Why it exists: hard-page review should have a deterministic artifact shape from the start.

Dependencies: Tasks 3.1.2, 3.2.1, 7.1.1

Files to create/update: review/overlay_builder.py, review/pack_builder.py

Acceptance criteria:

sample overlay can mark icon bbox on page PNG

report references page id and failing QA records

Test requirements: unit test for overlay image generation

Definition of done: failed pages can emit a review pack artifact even before a separate UI exists

Feature 7.2 — Visual regression and publish
Task 7.2.1 — Add Playwright visual baseline and axe check

Objective: Capture one stable reader-page screenshot and one accessibility report.

Why it exists: manual visual QA is a known weak point; this starts automated coverage immediately.

Dependencies: Task 6.2.2

Files to create/update: apps/web/playwright.config.ts, apps/web/tests/e2e/reader-page.spec.ts, packages/qa_assets/playwright_baselines/**

Acceptance criteria:

screenshot baseline is committed

route test asserts heading and icon are visible

axe check runs on the same page

Test requirements: Playwright and axe run in CI

Definition of done: a single deterministic visual regression test protects the walking skeleton

Task 7.2.2 — Implement local release bundle

Objective: Build a release directory containing static web assets plus data payloads and a manifest.

Why it exists: the architecture is complete only when a static edition can be emitted reproducibly.

Dependencies: Tasks 6.1.2, 6.2.2, 7.1.1

Files to create/update: stages/publish/bundle_builder.py, build_manifest_v1.py, scripts/build_release.sh

Acceptance criteria:

local release folder contains manifest.json, data payloads, and static app build

manifest records content version and build timestamp

Test requirements: integration test on generated release folder structure

Definition of done: one command creates a self-contained static release bundle

4. Delivery phases
Phase 0: bootstrap / repo / contracts

Goals

lock repo scaffold

lock contract package

lock config loader

lock walking skeleton spec

Outputs

workspace files

ADR seed set

initial schemas

codegen pipeline

walking_skeleton.toml

Prerequisites

none

Risks

schema churn

toolchain mismatch between Python and JS

Exit criteria

fresh clone boots

schemas generate successfully

fixture JSON validates

Phase 1: core IR and extraction backbone

Goals

implement ingest

implement rasterization

implement native extraction

establish first NativePageV1 and SourceManifestV1

Outputs

ingest stage

raster PNGs

native extraction artifact for sample page

pipeline runtime and artifact store

Prerequisites

Phase 0 complete

Risks

PyMuPDF extraction edge cases

artifact pathing bugs

Exit criteria

atr run --doc walking_skeleton --to extract_native works

artifacts are cached and replayable

Phase 2: symbol/icon anchoring

Goals

define symbol catalog

detect one real inline icon

persist SymbolMatchSetV1

Outputs

symbol catalog schema and config

template matcher

expected symbol match fixture

Prerequisites

Phase 1 complete

Risks

matcher false positives

unstable image preprocessing

Exit criteria

one sym.progress match is detected on sample page with stable bbox and score

Phase 3: structure recovery and normalization

Goals

build the first English PageIRV1

insert inline icon node

establish reading order

add furniture detector scaffold

Outputs

block builder

reading order module

page_ir.en.p0001.json

Prerequisites

Phases 1–2 complete

Risks

overfitting heuristics to the sample page

hidden markdown shortcuts sneaking in

Exit criteria

English canonical page IR matches expected golden fixture

Phase 4: translation subsystem

Goals

create concept registry

create translation planner

create mock translator

create validator/enforcer skeleton

Outputs

TranslationBatchV1

TranslationResultV1

page_ir.ru.p0001.json

provider adapter interfaces

Prerequisites

Phase 3 complete

Risks

designing translation contracts too loosely

coupling planner to a specific provider

Exit criteria

one translated paragraph with preserved icon node is produced from structured input

Phase 5: render model and frontend

Goals

build render payload

build minimal nav/glossary/search payloads

render typed page in React

Outputs

RenderPageV1

static sample payloads

ReaderPage route

block renderer and icon renderer

Prerequisites

Phase 4 complete

Risks

frontend drifting into markdown rendering

direct frontend dependence on raw IR instead of render artifacts

Exit criteria

reader route renders heading, paragraph, icon, and source page badge from static JSON

Phase 6: QA and visual regression

Goals

implement first blocking QA rules

add Playwright screenshot baseline

add axe accessibility check

Outputs

QARecordV1

QASummaryV1

baseline screenshot

review pack scaffold

Prerequisites

Phase 5 complete

Risks

flaky visual baselines

QA rules coupled too tightly to fixture-specific output

Exit criteria

sample page passes QA and visual snapshot in CI
Phase 7: publish / operations / hardening

Goals

create local release bundle

add runbook and release process

harden retry/cache behavior

add stubs for real layout and provider adapters

Outputs

local release directory

build manifest

operational docs

stable CI pipeline

Prerequisites

Phase 6 complete

Risks

release bundle structure changing after frontend integration

overbuilding release tooling too early

Exit criteria

one command produces a reproducible static release for walking_skeleton

5. ADR backlog

Create these first, in this order.

Filename	Title	Decision summary	Why it matters now
docs/adrs/ADR-001-ir-first-canonical-state.md	Canonical state is typed IR	JSON IR is the source of truth; markdown is not	Prevents agents from slipping back into text-blob pipelines
docs/adrs/ADR-002-markdown-not-source-of-truth.md	Markdown is export-only	Markdown may exist for debug/export only	Frontend and pipeline boundaries depend on this
docs/adrs/ADR-003-immutable-artifacts-and-patches.md	Artifacts are immutable; fixes are patches	No in-place edits to stage outputs	Needed before artifact store implementation
docs/adrs/ADR-004-pymupdf-as-native-pdf-extractor.md	PyMuPDF is the native truth layer	Native text/image geometry comes from PyMuPDF	Locks extraction backbone
docs/adrs/ADR-005-docling-as-layout-evidence.md	Docling provides structural evidence	Layout/order hints come from a secondary evidence stream	Prevents extractor monoculture
docs/adrs/ADR-006-symbol-catalog-and-template-matching.md	Icons are catalogued assets	Inline symbols are recovered via catalog + matching	Solves the central icon-loss problem explicitly
docs/adrs/ADR-007-structured-translation-contracts.md	Translation uses structured block-level contracts	Translation input/output must be schema-bound	Needed before prompt or adapter work starts
docs/adrs/ADR-008-static-react-reader.md	Publish a static React reader	Web app consumes render payloads only	Locks the frontend integration model
docs/adrs/ADR-009-no-workflow-orchestrator-v1.md	Use custom stage runner	No Prefect/Dagster/Temporal in v1	Prevents premature infra expansion
docs/adrs/ADR-010-qa-is-release-blocking.md	QA blocks publish	Error/critical findings stop release	Needed before QA rules are implemented
docs/adrs/ADR-011-shared-schemas-generated-to-jsonschema-and-ts.md	Contracts are generated to JSON Schema and TS	Python schemas generate web-consumable types	Prevents backend/frontend drift
docs/adrs/ADR-012-build-english-source-edition-first.md	Source edition comes before full translation	Extraction correctness is proven before provider integration	Keeps first implementation slice controlled
6. Contracts and schemas backlog
6.1 Runtime contracts to define first
Contract	File path	Purpose	Required fields / methods	Downstream consumers
DocumentBuildConfig	apps/pipeline/src/atr_pipeline/config/models.py	Typed loaded config	document.id, document.source_pdf, pipeline.version, translation, symbols, qa	CLI, stage context, all stages
Stage protocol	apps/pipeline/src/atr_pipeline/runner/stage_protocol.py	Common execution interface	name, scope, input_model, output_model, run()	executor, all stages
StageContext	apps/pipeline/src/atr_pipeline/runner/stage_context.py	Runtime dependencies	run_id, document_id, config, artifact_store, registry, logger	all stages
ArtifactRef	packages/schemas/python/atr_schemas/common.py and store/artifact_ref.py	Pointer to immutable artifact	schema_family, scope, entity_id, hash, path	store, registry, manifests
6.2 Artifact schemas to define before serious implementation
Schema name	File path	Purpose	Required fields	Downstream consumers
CommonPrimitives	packages/schemas/python/atr_schemas/common.py	Rects, ids, provenance, refs	Rect, ArtifactRef, ProvenanceRef, timestamp helpers	all schemas
SourceManifestV1	.../source_manifest_v1.py	Registered source document and pages	schema_version, document_id, source_pdf_sha256, page_count, pages[]	ingest, rasterizer, CLI, tests
NativePageV1	.../native_page_v1.py	Native text/image evidence per page	page_id, dimensions_pt, words[], spans[], image_blocks[], extractor_meta	symbols, structure, review
LayoutPageV1	.../layout_page_v1.py	Secondary layout evidence	page_id, zones[], reading_order_candidates[], difficulty_score	structure, hard-page routing
AssetV1	.../asset_v1.py	Extracted assets and crops	asset_id, kind, bbox, sha256, source_page_id, variants[]	symbols, render, review
SymbolCatalogV1	.../symbol_catalog_v1.py	Known icon definitions	catalog_id, symbols[], each with symbol_id, label, template_asset, match_threshold	symbols stage, frontend alt labels
SymbolMatchSetV1	.../symbol_match_set_v1.py	Page-level symbol detections	page_id, matches[], symbol_id, bbox, score, source_asset_id	structure, QA
PageIRV1	.../page_ir_v1.py	Canonical page content	document_id, page_id, language, blocks[], assets[], reading_order[], provenance, qa_state	translation, render, QA
ConceptRegistryV1	.../concept_registry_v1.py	Glossary and term rules	version, concepts[], each with concept_id, source, target, validation_policy	translation planner, glossary builder
TranslationBatchV1	.../translation_batch_v1.py	Structured translation request	batch_id, source_lang, target_lang, segments[], required_concepts[], locked_nodes[]	translators, tests
TranslationResultV1	.../translation_result_v1.py	Structured translation response	batch_id, segments[], target_inline[], concept_realizations[]	validator, enforcer, render
RenderPageV1	.../render_page_v1.py	Frontend page payload	schema_version, document_version, page, nav, blocks[], source_map	web app, visual regression
GlossaryPayloadV1	.../glossary_payload_v1.py	Frontend glossary payload	document_id, entries[], concept_id, preferred_term, aliases[], icon_binding	glossary UI
SearchDocsV1	.../search_docs_v1.py	Search input artifacts	document_id, docs[], page_id, text, terms[], section_path[]	search builder, frontend
QARecordV1	.../qa_record_v1.py	Individual QA finding	qa_id, layer, severity, code, entity_ref, expected, actual	QA reports, review pack
QASummaryV1	.../qa_summary_v1.py	Aggregated QA result	document_id, run_id, counts_by_severity, blocking, records[] or refs	CLI, release gate
RunManifestV1	.../run_manifest_v1.py	Run metadata	run_id, pipeline_version, config_hash, stage_results[], qa_summary	registry export, release
PatchSetV1	.../patch_set_v1.py	Human-reviewed deterministic patches	patch_id, target_artifact_ref, operations[], reason, author	later review workflow
BuildManifestV1	.../build_manifest_v1.py	Published release manifest	build_id, document_id, content_version, generated_at, files[]	publish stage, static host
7. Initial implementation order
7.1 Parallelizable workstreams
Workstream A — Contracts and repo foundation

Start immediately.

repo bootstrap

schemas

codegen

config loader

ADRs/specs

Workstream B — Fixtures and gold data

Can start in parallel with A after directory scaffold exists.

sample PDF page

expected JSON artifacts

sample icon template

sample symbol catalog

baseline screenshot placeholder

Workstream C — Pipeline runtime

Starts after core schemas exist.

artifact store

run registry

stage executor

CLI

Workstream D — Frontend stub

Can start after RenderPageV1 is stable, even before real extraction exists.

typed loaders

block renderer

reader route

storybook stories

visual baseline plumbing

Workstream E — Extraction and structure

Starts after runtime + source/native schemas exist.

ingest

rasterization

native extraction

symbol matcher

simple block builder

Workstream F — Translation and QA

Starts after PageIRV1, ConceptRegistryV1, and RenderPageV1 exist.

translation planner

mock translator

validator

icon QA rule

release gate

7.2 Sequence constraints

Do not start provider adapters before translation contracts are frozen.

Do not start real Docling/Paddle integration before LayoutPageV1 is frozen.

Do not let frontend consume raw PageIRV1; it must wait for RenderPageV1.

Do not build review UI before review pack artifact shape exists.

Do not implement search indexing before RenderPageV1 and glossary payload shape settle.

7.3 What should be mocked initially

Mock these in the first implementation slice:

MockTranslator instead of live LLM provider

fallback_stub.py instead of real OCR fallback

single-page nav builder with one page only

one-symbol catalog only

one-rule QA gate: icon count

local file publish only, no remote deploy

7.4 What should be prototyped first

Prototype these before deeper buildout:

NativePageV1 extraction from one page

icon template matching on one sample icon

PageIRV1 with one heading and one paragraph-with-icon

RenderPageV1 loaded by frontend

one Playwright screenshot baseline

7.5 What should be delayed until interfaces stabilize

Delay these until after the walking skeleton passes:

real OpenAI / Anthropic adapters

Docling full integration beyond contract stub

Paddle/Tesseract fallback

multi-page section tree logic

search ranking tuning

glossary drawer UX refinements

review UI application

remote artifact storage

multi-document support

8. First 10 agent tickets
Ticket 1 — Initialize monorepo, workspace tooling, and root scripts

Background
The repo must support a Python pipeline app, a React web app, and shared schema packages without ad hoc setup.

Scope

create root workspace files

create root folders from scaffold

add make targets for lint/test/codegen

add minimal GitHub Actions workflows

Non-goals

implementing business logic

defining final schemas

adding live provider integrations

Files

pyproject.toml

package.json

pnpm-workspace.yaml

Makefile

.pre-commit-config.yaml

.github/workflows/ci.yml

.github/workflows/python-tests.yml

.github/workflows/web-tests.yml

Acceptance criteria

uv sync completes

pnpm install completes

make lint and make test run placeholder tasks successfully

root directory scaffold exists exactly as specified

Tests

CI smoke check

local command smoke check documented in README.md

Risks / notes

keep workspace minimal; do not add optional tools not used by later tickets

no Poetry, no Nx, no turborepo

Ticket 2 — Create shared schema package with common primitives and first core models

Background
All later work depends on typed shared contracts.

Scope

create packages/schemas/python/atr_schemas

add common.py, enums.py

implement SourceManifestV1, NativePageV1, PageIRV1, RenderPageV1, QARecordV1

Non-goals

stage implementation

codegen to TS

frontend use of schemas

Files

packages/schemas/python/atr_schemas/common.py

packages/schemas/python/atr_schemas/enums.py

packages/schemas/python/atr_schemas/source_manifest_v1.py

packages/schemas/python/atr_schemas/native_page_v1.py

packages/schemas/python/atr_schemas/page_ir_v1.py

packages/schemas/python/atr_schemas/render_page_v1.py

packages/schemas/python/atr_schemas/qa_record_v1.py

Acceptance criteria

all models validate and serialize deterministically

block and inline unions use discriminators

one sample JSON per schema validates

Tests

apps/pipeline/tests/contract/test_schema_roundtrip.py

Risks / notes

keep required fields tight; avoid speculative fields unless already committed in architecture

do not place pipeline logic in schema files

Ticket 3 — Add JSON Schema and TypeScript code generation pipeline

Background
Frontend and QA tooling must consume generated contracts, not hand-transcribed types.

Scope

implement Python schema export script

implement TS generation script

create TS package barrel exports

add stale-generated-file check to CI

Non-goals

using generated types in the frontend yet

OpenAPI generation

runtime API server work

Files

scripts/generate_jsonschema.py

scripts/generate_ts_types.mjs

packages/schemas/jsonschema/**

packages/schemas/ts/package.json

packages/schemas/ts/src/index.ts

Acceptance criteria

one command regenerates schemas and TS types

CI fails when generated files are outdated

generated TS package builds

Tests

schema generation smoke test

TS compile test

Risks / notes

keep file names stable; later tickets will import them directly
Ticket 4 — Implement typed config models and layered loader

Background
Document-specific config and shared defaults must be validated before stage execution begins.

Scope

create config models

load base.toml, ci.toml, walking_skeleton.toml

resolve repo-relative paths

expose a single load_document_config(doc_id) API

Non-goals

secret management

environment-specific provider credentials

CLI implementation

Files

configs/base.toml

configs/ci.toml

configs/documents/walking_skeleton.toml

apps/pipeline/src/atr_pipeline/config/models.py

apps/pipeline/src/atr_pipeline/config/loader.py

Acceptance criteria

merged config is deterministic

invalid symbol catalog path fails with clear error

document id lookup is case-sensitive and explicit

Tests

apps/pipeline/tests/unit/config/test_loader.py

Risks / notes

keep config schema separate from artifact schemas

Ticket 5 — Implement immutable artifact store and cache-key pathing

Background
The architecture depends on immutable stage outputs and idempotent replay.

Scope

add artifact ref model

create pathing convention

add atomic JSON write/read helpers

implement has/get/put APIs

Non-goals

SQLite registry

stage executor

artifact garbage collection

Files

apps/pipeline/src/atr_pipeline/store/artifact_ref.py

apps/pipeline/src/atr_pipeline/store/pathing.py

apps/pipeline/src/atr_pipeline/store/atomic_write.py

apps/pipeline/src/atr_pipeline/store/artifact_store.py

apps/pipeline/src/atr_pipeline/runner/cache_keys.py

Acceptance criteria

artifact paths match <doc>/<schema_family>/<scope>/<id>/<hash>.json

writes are atomic

same key returns same ref on rerun

Tests

apps/pipeline/tests/unit/store/test_artifact_store.py

apps/pipeline/tests/unit/runner/test_cache_keys.py

Risks / notes

no mutable “latest” files inside artifact paths

avoid hand-built string concatenation outside pathing.py

Ticket 6 — Implement SQLite run registry and stage executor skeleton

Background
The pipeline needs operational state separate from artifact files.

Scope

create registry schema and migrations

record run lifecycle and stage lifecycle events

define Stage protocol and StageContext

implement executor skeleton with cache skip behavior

Non-goals

concrete stages beyond a dummy test stage

CLI commands beyond executor entry

Files

apps/pipeline/src/atr_pipeline/registry/db.py

apps/pipeline/src/atr_pipeline/registry/migrations.py

apps/pipeline/src/atr_pipeline/registry/runs.py

apps/pipeline/src/atr_pipeline/registry/events.py

apps/pipeline/src/atr_pipeline/runner/stage_protocol.py

apps/pipeline/src/atr_pipeline/runner/stage_context.py

apps/pipeline/src/atr_pipeline/runner/executor.py

Acceptance criteria

a dummy stage run is recorded in SQLite

rerunning the same dummy stage with same inputs skips execution

stage failures are persisted as failed events

Tests

apps/pipeline/tests/unit/registry/test_db.py

apps/pipeline/tests/unit/runner/test_executor.py

Risks / notes

keep registry schema small; artifact files remain the primary data plane

Ticket 7 — Add walking skeleton fixtures and golden expected artifacts

Background
Agents need a stable single-page target to develop against without waiting for the full document pipeline.

Scope

add walking_skeleton sample page

add sample icon image

add source notes

add golden JSON placeholders for manifest, native page, page IR, translation result, render page, QA summary

Non-goals

full real-document fixtures

legal/publishing discussion

multi-page samples

Files

packages/fixtures/sample_documents/walking_skeleton/source/*

packages/fixtures/sample_documents/walking_skeleton/expected/*

packages/fixtures/sample_documents/walking_skeleton/catalogs/walking_skeleton.symbols.toml

docs/specs/walking-skeleton.md

Acceptance criteria

fixture folder is self-explanatory

every expected JSON validates against schema package

sample symbol catalog contains one sym.progress entry

Tests

fixture validation test in test_schema_roundtrip.py

Risks / notes

if real page cannot be checked in, create a synthetic page immediately and document it explicitly

Ticket 8 — Implement ingest stage and page rasterization
Background
The first concrete stage should register the source and produce page rasters for later steps.

Scope

implement IngestStage

fingerprint source PDF

generate SourceManifestV1

rasterize the sample page to PNG

wire stage into executor

Non-goals

text extraction

symbol matching

frontend integration

Files

apps/pipeline/src/atr_pipeline/stages/ingest/stage.py

apps/pipeline/src/atr_pipeline/stages/ingest/pdf_fingerprint.py

apps/pipeline/src/atr_pipeline/stages/ingest/manifest_builder.py

apps/pipeline/src/atr_pipeline/services/pdf/rasterizer.py

apps/pipeline/src/atr_pipeline/cli/commands/ingest.py

Acceptance criteria

atr ingest --doc walking_skeleton writes manifest artifact and raster PNG

rerun hits cache

manifest matches expected fixture fields

Tests

apps/pipeline/tests/unit/stages/ingest/test_stage.py

Risks / notes

keep raster DPI config-driven

write raster refs via artifacts, not ad hoc temp paths

Ticket 9 — Implement native PyMuPDF extraction and one-symbol matcher

Background
This ticket proves the evidence model: text and image evidence from PDF, plus deterministic icon recovery.

Scope

extract words/spans/image blocks into NativePageV1

implement SymbolCatalogV1 loader

implement template matcher for one sample symbol

emit SymbolMatchSetV1

Non-goals

full hard-page routing

multi-column layout handling

translation

Files

apps/pipeline/src/atr_pipeline/stages/extract_native/pymupdf_extractor.py

apps/pipeline/src/atr_pipeline/stages/extract_native/normalizer.py

apps/pipeline/src/atr_pipeline/stages/symbols/catalog_loader.py

apps/pipeline/src/atr_pipeline/stages/symbols/matcher.py

apps/pipeline/src/atr_pipeline/stages/symbols/stage.py

packages/schemas/python/atr_schemas/native_page_v1.py

packages/schemas/python/atr_schemas/symbol_catalog_v1.py

packages/schemas/python/atr_schemas/symbol_match_set_v1.py

Acceptance criteria

sample page yields stable native extraction

one sym.progress detection exists

matcher output validates and matches golden fixture

Tests

apps/pipeline/tests/unit/stages/extract_native/test_pymupdf_extractor.py

apps/pipeline/tests/unit/stages/symbols/test_matcher.py

Risks / notes

do not invent icon placement from text patterns

icon must come from image evidence

Ticket 10 — Build the minimal walking skeleton end-to-end

Background
This ticket proves the architecture with the thinnest full chain: source page -> IR -> translated IR -> render payload -> frontend route -> QA -> visual snapshot.

Scope

implement simple block builder for one page

implement TranslationBatchV1 and MockTranslator

implement RenderPageV1 builder

wire sample payloads into web app

implement one QA rule: icon count parity

add one Playwright screenshot baseline

Non-goals

real LLM integrations

Docling hard-page routing

full glossary/search UX

figure rendering beyond what the sample needs

Files

apps/pipeline/src/atr_pipeline/stages/structure/block_builder.py

apps/pipeline/src/atr_pipeline/stages/translation/planner.py

apps/pipeline/src/atr_pipeline/services/llm/mock_translator.py

apps/pipeline/src/atr_pipeline/stages/translation/validator.py

apps/pipeline/src/atr_pipeline/stages/render/page_builder.py

apps/pipeline/src/atr_pipeline/stages/qa/rules/icon_count_rule.py

apps/web/src/lib/api/loadRenderPage.ts

apps/web/src/components/reader/BlockRenderer.tsx

apps/web/src/components/reader/IconInline.tsx

apps/web/src/routes/ReaderPage.tsx

apps/web/tests/e2e/reader-page.spec.ts

packages/qa_assets/playwright_baselines/reader-page.spec.ts-snapshots/walking-skeleton-linux.png

Acceptance criteria

atr run --doc walking_skeleton --to qa completes successfully

English IR, Russian IR, render page, and QA summary artifacts are produced

reader route renders heading + paragraph + inline icon

Playwright test passes with committed snapshot

Tests

backend integration: apps/pipeline/tests/integration/test_walking_skeleton_pipeline.py

frontend component test: apps/web/tests/component/ReaderPage.test.tsx

frontend Playwright visual test: apps/web/tests/e2e/reader-page.spec.ts

Risks / notes

keep the structure builder intentionally narrow for the sample page

do not skip the render artifact step by feeding raw IR into the frontend

9. Bootstrap prompts for agents
9.1 Architecture-aware repo bootstrap agent
You are working inside an IR-first document compiler repository for a board-game rules reader.

You must preserve these architectural rules:
1. Canonical state is typed JSON IR, not markdown or HTML.
2. Markdown may exist only for docs/debug/export, never as the source of truth.
3. Artifacts are immutable and content-addressed.
4. Human fixes must become typed patches later, not in-place edits.
5. The frontend consumes render payloads, not raw extraction artifacts.
6. Do not introduce microservices, workflow engines, or runtime databases beyond SQLite + filesystem artifacts.
7. Keep all public contracts in packages/schemas and regenerate JSON Schema + TS types whenever those contracts change.
8. Prefer small, boring, deterministic abstractions.
9. Every change must include tests or fixture updates.
10. Do not redesign the architecture unless you hit a genuine contradiction. If so, isolate it and document it before changing code.

Before coding:
- Read docs/specs/walking-skeleton.md
- Read ADR-001 through ADR-008
- Follow the repo scaffold exactly

Output:
- create or update only the files needed for the assigned task
- keep diffs tight
- include any generated files that belong to the task
- include tests and a short note of what was changed
9.2 Backend pipeline agent
You are implementing the Python pipeline for a typed, deterministic document compiler.

Non-negotiable constraints:
- No markdown-centric shortcuts.
- No stage may mutate prior artifacts.
- Use typed Pydantic models from packages/schemas.
- Stage outputs must validate before being written.
- Cache keys must be deterministic and based on stage version, schema version, config hash, and input hashes.
- Avoid hidden global state.
- Use the artifact store and run registry; do not write ad hoc JSON files outside approved paths.
- If external systems are not ready, create a mock adapter behind the stable interface instead of bypassing the architecture.

When implementing stages:
- keep them pure where possible
- keep input/output schemas explicit
- write unit tests first for serializers, validators, and cache behavior
- write an integration test only when the stage boundary is stable

You may add small helper utilities, but do not add a new framework.
If a schema change is necessary, update:
- Python model
- JSON Schema
- TS generated type
- fixture JSON
- tests

Prefer deterministic behavior over cleverness.
9.3 Frontend rendering agent
You are implementing a static React reader for typed render payloads.

Non-negotiable constraints:
- The frontend reads RenderPageV1 and related payloads only.
- Do not parse markdown.
- Do not couple components to pipeline internals or raw extraction artifacts.
- Keep rendering typed: block kind -> block component, inline kind -> inline component.
- Icons are explicit inline nodes, not regex substitutions.
- Accessibility is required from the first route: semantic headings, keyboard focus, meaningful alt/aria text.
- Static hosting is the deployment model; avoid backend assumptions.

Before coding:
- Read docs/specs/frontend-rendering.md
- Read ADR-001, ADR-002, ADR-008, ADR-011
- Import types from @atr/schemas instead of redefining shapes

Deliver:
- small focused components
- tests for block renderer and route
- stable Storybook stories for each new block type
- no CSS-in-JS libraries unless already approved
9.4 QA / visual-regression agent
You own deterministic QA and visual regression.

Non-negotiable constraints:
- QA findings must be machine-readable and typed.
- Error and critical findings are release-blocking.
- Visual tests must be deterministic: fixed viewport, stable fonts, no animations, no random data.
- Accessibility checks must run on the same fixture pages used for visual tests.
- Do not create flaky screenshot coverage across the whole app immediately; start with the walking skeleton route and a few isolated stories.

Before coding:
- Read docs/specs/qa-gates.md
- Read ADR-010
- Read the walking skeleton spec and fixture notes

Implement:
- one blocking rule at a time
- one screenshot baseline at a time
- one accessibility report at a time

If you detect flakiness:
- reduce motion
- freeze time where needed
- move coverage to Storybook stories if full-page snapshots are unstable
- document the reason instead of weakening the architecture
10. Minimal walking skeleton

This is the thinnest end-to-end slice that proves the architecture.

10.1 Exact scope
Input

One sample PDF page:

packages/fixtures/sample_documents/walking_skeleton/source/sample_page_01.pdf

One icon template:

packages/fixtures/sample_documents/walking_skeleton/source/symbol_progress.png

One document config:

configs/documents/walking_skeleton.toml

Output

SourceManifestV1

NativePageV1

SymbolMatchSetV1 with exactly one sym.progress

PageIRV1(en) with:

one heading block

one paragraph block

one inline icon node

TranslationBatchV1

TranslationResultV1

PageIRV1(ru) with preserved icon node

RenderPageV1

QASummaryV1 with one passing icon-count rule

one frontend route showing the page

one Playwright baseline screenshot

10.2 Sample content to hard-code into the fixture expectation

Use this exact logical content for the first slice.

English source intent

Heading: Attack Test

Paragraph: Gain 1 [sym.progress] Progress.

Russian target intent

Heading: Проверка атаки

Paragraph: Получите 1 [sym.progress] Прогресс.

The icon must appear as a typed inline node in both EN and RU IR, and in the rendered page payload.

10.3 Minimal stages that must exist

Ingest

fingerprints the sample PDF

emits page metadata

rasterizes page p0001

Extract native

extracts words and image blocks from the PDF via PyMuPDF

writes NativePageV1

Match symbols

loads walking_skeleton.symbols.toml

detects sym.progress

writes SymbolMatchSetV1

Build English Page IR

creates one heading block and one paragraph block

inserts icon node inline in the paragraph

writes page_ir.en.p0001.json

Plan and execute mock translation

creates one translation batch

mock translator returns fixed RU inline nodes

validator checks icon preservation

writes page_ir.ru.p0001.json

Build render payload

maps RU IR to RenderPageV1

creates one-page nav payload

creates one-entry glossary payload for concept.progress

creates one search doc

Run QA

schema validation passes

icon count rule passes

Render frontend

ReaderPage loads render_page.p0001.json

BlockRenderer renders heading and paragraph

IconInline renders the inline icon

Run visual regression

Playwright opens the page

checks heading and paragraph text

captures screenshot baseline

10.4 Exact files that must be implemented for the walking skeleton
Pipeline

configs/documents/walking_skeleton.toml

packages/fixtures/sample_documents/walking_skeleton/source/sample_page_01.pdf

packages/fixtures/sample_documents/walking_skeleton/source/symbol_progress.png

packages/fixtures/sample_documents/walking_skeleton/catalogs/walking_skeleton.symbols.toml

apps/pipeline/src/atr_pipeline/stages/ingest/stage.py

apps/pipeline/src/atr_pipeline/stages/extract_native/pymupdf_extractor.py

apps/pipeline/src/atr_pipeline/stages/symbols/matcher.py

apps/pipeline/src/atr_pipeline/stages/structure/block_builder.py

apps/pipeline/src/atr_pipeline/stages/translation/planner.py

apps/pipeline/src/atr_pipeline/services/llm/mock_translator.py

apps/pipeline/src/atr_pipeline/stages/translation/validator.py

apps/pipeline/src/atr_pipeline/stages/render/page_builder.py

apps/pipeline/src/atr_pipeline/stages/qa/rules/icon_count_rule.py

apps/pipeline/tests/integration/test_walking_skeleton_pipeline.py

Frontend

apps/web/src/lib/api/loadRenderPage.ts

apps/web/src/components/reader/BlockRenderer.tsx

apps/web/src/components/reader/IconInline.tsx

apps/web/src/routes/ReaderPage.tsx

apps/web/tests/component/ReaderPage.test.tsx

apps/web/tests/e2e/reader-page.spec.ts

Contracts

packages/schemas/python/atr_schemas/source_manifest_v1.py

packages/schemas/python/atr_schemas/native_page_v1.py

packages/schemas/python/atr_schemas/symbol_catalog_v1.py

packages/schemas/python/atr_schemas/symbol_match_set_v1.py

packages/schemas/python/atr_schemas/page_ir_v1.py

packages/schemas/python/atr_schemas/translation_batch_v1.py

packages/schemas/python/atr_schemas/translation_result_v1.py

packages/schemas/python/atr_schemas/render_page_v1.py

packages/schemas/python/atr_schemas/qa_record_v1.py

packages/schemas/python/atr_schemas/qa_summary_v1.py

Gold data

packages/fixtures/sample_documents/walking_skeleton/expected/source_manifest.json

packages/fixtures/sample_documents/walking_skeleton/expected/native_page.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/symbol_matches.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/page_ir.en.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/translation_batch.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/translation_result.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/page_ir.ru.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/render_page.p0001.json

packages/fixtures/sample_documents/walking_skeleton/expected/qa_summary.json

QA assets

packages/qa_assets/playwright_baselines/reader-page.spec.ts-snapshots/walking-skeleton-linux.png

10.5 Required automated checks for the walking skeleton
Backend integration test

apps/pipeline/tests/integration/test_walking_skeleton_pipeline.py

runs the pipeline from ingest through qa

validates each artifact against schema

compares emitted artifacts to expected golden JSON for the sample page

Frontend component test

apps/web/tests/component/ReaderPage.test.tsx

loads the sample render page

asserts heading text

asserts paragraph text

asserts inline icon element exists

Frontend visual test

apps/web/tests/e2e/reader-page.spec.ts

opens /documents/walking_skeleton/p0001

asserts visible heading Проверка атаки

asserts visible paragraph Получите 1

asserts one icon exists

captures screenshot and compares against baseline

QA rule test

apps/pipeline/tests/unit/stages/qa/test_icon_count_rule.py

passing case: source IR icon count == target IR icon count == render icon count == 1

failing case: target icon omitted

asserts severity is error in failing case

10.6 Minimal command flow that must work
uv run atr ingest --doc walking_skeleton
uv run atr run --doc walking_skeleton --from ingest --to qa
pnpm --filter @atr/web dev
pnpm --filter @atr/web test
pnpm --filter @atr/web test:e2e
10.7 Done criteria for the walking skeleton

 sample page is checked in

 source manifest artifact is produced

 native extraction artifact is produced

 one icon is matched from image evidence

 English PageIRV1 contains one typed inline icon node

 Russian PageIRV1 preserves the same icon node

 RenderPageV1 is generated and validated

 frontend route renders heading, paragraph, and icon from render payload

 one QA rule passes

 one backend integration test passes

 one frontend visual regression snapshot passes


