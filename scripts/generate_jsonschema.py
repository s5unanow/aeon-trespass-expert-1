#!/usr/bin/env python3
"""Generate JSON Schema files from Pydantic v2 models.

Output goes to packages/schemas/jsonschema/*.schema.json
These are generated files — do not edit by hand.
"""

import json
from pathlib import Path

from atr_schemas.asset_v1 import AssetV1
from atr_schemas.build_manifest_v1 import BuildManifestV1
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.glossary_payload_v1 import GlossaryPayloadV1
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.nav_payload_v1 import NavPayloadV1
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.render_page_v1 import RenderPageV1
from atr_schemas.review_pack_v1 import ReviewPackV1
from atr_schemas.run_manifest_v1 import RunManifestV1
from atr_schemas.search_docs_v1 import SearchDocsV1
from atr_schemas.source_manifest_v1 import SourceManifestV1
from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1
from atr_schemas.waiver_v1 import WaiverSetV1

MODELS = {
    "asset_v1": AssetV1,
    "build_manifest_v1": BuildManifestV1,
    "concept_registry_v1": ConceptRegistryV1,
    "glossary_payload_v1": GlossaryPayloadV1,
    "layout_page_v1": LayoutPageV1,
    "native_page_v1": NativePageV1,
    "nav_payload_v1": NavPayloadV1,
    "page_ir_v1": PageIRV1,
    "patch_set_v1": PatchSetV1,
    "qa_record_v1": QARecordV1,
    "qa_summary_v1": QASummaryV1,
    "render_page_v1": RenderPageV1,
    "review_pack_v1": ReviewPackV1,
    "run_manifest_v1": RunManifestV1,
    "search_docs_v1": SearchDocsV1,
    "source_manifest_v1": SourceManifestV1,
    "symbol_catalog_v1": SymbolCatalogV1,
    "symbol_match_set_v1": SymbolMatchSetV1,
    "translation_batch_v1": TranslationBatchV1,
    "translation_result_v1": TranslationResultV1,
    "waiver_set_v1": WaiverSetV1,
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "packages" / "schemas" / "jsonschema"


def generate() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        out_path = OUTPUT_DIR / f"{name}.schema.json"
        content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        out_path.write_text(content, encoding="utf-8")
        print(f"  wrote {out_path.relative_to(OUTPUT_DIR.parent.parent.parent)}")


if __name__ == "__main__":
    generate()
