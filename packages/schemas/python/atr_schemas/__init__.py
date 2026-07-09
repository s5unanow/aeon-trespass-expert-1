"""Shared Pydantic v2 schemas for the ATR document compiler pipeline."""

from atr_schemas.asset_class_v1 import AssetClassV1, AssetIdentity
from atr_schemas.asset_occurrence_v1 import AssetOccurrenceV1
from atr_schemas.asset_registry_v1 import AssetRegistryV1
from atr_schemas.asset_v1 import AssetV1, AssetVariant
from atr_schemas.assistant_citation_v1 import AssistantCitationV1
from atr_schemas.assistant_pack_v1 import AssistantPackV1
from atr_schemas.build_manifest_v1 import BuildManifestV1, ReleaseFile
from atr_schemas.common import (
    ArtifactRef,
    ConfidenceMetrics,
    EvidenceId,
    NormRect,
    PageDimensions,
    ProvenanceRef,
    QAState,
    Rect,
    RegionId,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1, ConceptV1
from atr_schemas.enums import (
    AnchorEdgeKind,
    AssetKind,
    AssetSourceKind,
    BlockType,
    InlineType,
    LanguageCode,
    OccurrenceContext,
    PatchScope,
    PatchTargetKind,
    QALayer,
    RegionKind,
    Severity,
    StageScope,
    SymbolAnchorKind,
)
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceEntity,
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceRegionCandidate,
    EvidenceTableCandidate,
    EvidenceTextSpan,
    EvidenceVectorCluster,
    EvidenceVectorPath,
)
from atr_schemas.glossary_payload_v1 import GlossaryEntryV1, GlossaryPageRef, GlossaryPayloadV1
from atr_schemas.image_set_manifest_v1 import ImageSetImageV1, ImageSetManifestV1
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1, LayoutZone
from atr_schemas.native_page_v1 import (
    ImageBlockEvidence,
    NativePageV1,
    SpanEvidence,
    WordEvidence,
)
from atr_schemas.nav_payload_v1 import NavEntryV1, NavPayloadV1
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.page_images_v1 import PageImageEntry, PageImagesV1
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    FigureRefInline,
    HeadingBlock,
    IconInline,
    InlineNode,
    LineBreakInline,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TermMarkInline,
    TextInline,
    UnknownBlock,
    XrefInline,
)
from atr_schemas.patch_set_v1 import PatchOperation, PatchProvenance, PatchSetV1
from atr_schemas.public_qa_record_set_v1 import PublicQARecordSetV1, PublicQARecordV1
from atr_schemas.public_qa_summary_v1 import PublicQASummaryV1
from atr_schemas.qa_metrics_v1 import FindingCodeCount, QAMetricsV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.raster_meta_v1 import RasterLevel, RasterMetaV1
from atr_schemas.render_page_v1 import (
    RenderBlock,
    RenderCalloutBlock,
    RenderDividerBlock,
    RenderFigureBlock,
    RenderFigureRefInline,
    RenderHeadingBlock,
    RenderIconInline,
    RenderInlineNode,
    RenderPageV1,
    RenderParagraphBlock,
    RenderTableBlock,
    RenderTableCellBlock,
    RenderTableRowBlock,
    RenderTextInline,
)
from atr_schemas.resolved_page_v1 import (
    AnchorEdge,
    FallbackProvenance,
    ResolvedBlock,
    ResolvedPageV1,
    ResolvedRegion,
    ResolvedSymbolRef,
    SemanticConfidence,
)
from atr_schemas.review_pack_v1 import ReviewFinding, ReviewPackV1
from atr_schemas.rule_chunk_v1 import GlossaryConcept, RuleChunkV1
from atr_schemas.run_manifest_v1 import RunManifestV1
from atr_schemas.run_summary_v1 import RunSummaryV1
from atr_schemas.search_docs_v1 import SearchDocEntry, SearchDocsV1
from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1
from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1, SymbolEntry
from atr_schemas.symbol_match_set_v1 import SymbolMatch, SymbolMatchSetV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1
from atr_schemas.translation_style_critic_v1 import (
    TranslationStyleCriticFindingV1,
    TranslationStyleCriticPageV1,
)
from atr_schemas.translation_style_repair_v1 import (
    TranslationStyleRepairChangeV1,
    TranslationStyleRepairPageV1,
)
from atr_schemas.waiver_v1 import WaiverSetV1, WaiverV1

__all__ = [
    "AnchorEdge",
    "AnchorEdgeKind",
    "ArtifactRef",
    "AssetClassV1",
    "AssetIdentity",
    "AssetKind",
    "AssetOccurrenceV1",
    "AssetRegistryV1",
    "AssetSourceKind",
    "AssetV1",
    "AssetVariant",
    "AssistantCitationV1",
    "AssistantPackV1",
    "Block",
    "BlockType",
    "BuildManifestV1",
    "CalloutBlock",
    "CaptionBlock",
    "ConceptRegistryV1",
    "ConceptV1",
    "ConfidenceMetrics",
    "DifficultyScoreV1",
    "DividerBlock",
    "EvidenceChar",
    "EvidenceEntity",
    "EvidenceId",
    "EvidenceImageOccurrence",
    "EvidenceLine",
    "EvidenceRegionCandidate",
    "EvidenceTableCandidate",
    "EvidenceTextSpan",
    "EvidenceTransformMeta",
    "EvidenceVectorCluster",
    "EvidenceVectorPath",
    "FallbackProvenance",
    "FigureBlock",
    "FigureRefInline",
    "FindingCodeCount",
    "GlossaryConcept",
    "GlossaryEntryV1",
    "GlossaryPageRef",
    "GlossaryPayloadV1",
    "HeadingBlock",
    "IconInline",
    "ImageBlockEvidence",
    "ImageSetImageV1",
    "ImageSetManifestV1",
    "InlineNode",
    "InlineType",
    "LanguageCode",
    "LayoutPageV1",
    "LayoutZone",
    "LineBreakInline",
    "ListBlock",
    "ListItemBlock",
    "NativePageV1",
    "NavEntryV1",
    "NavPayloadV1",
    "NormRect",
    "OccurrenceContext",
    "PageDimensions",
    "PageEntry",
    "PageEvidenceV1",
    "PageIRV1",
    "PageImageEntry",
    "PageImagesV1",
    "ParagraphBlock",
    "PatchOperation",
    "PatchProvenance",
    "PatchScope",
    "PatchSetV1",
    "PatchTargetKind",
    "ProvenanceRef",
    "PublicQARecordSetV1",
    "PublicQARecordV1",
    "PublicQASummaryV1",
    "QALayer",
    "QAMetricsV1",
    "QARecordV1",
    "QAState",
    "QASummaryV1",
    "RasterLevel",
    "RasterMetaV1",
    "Rect",
    "RegionId",
    "RegionKind",
    "ReleaseFile",
    "RenderBlock",
    "RenderCalloutBlock",
    "RenderDividerBlock",
    "RenderFigureBlock",
    "RenderFigureRefInline",
    "RenderHeadingBlock",
    "RenderIconInline",
    "RenderInlineNode",
    "RenderPageV1",
    "RenderParagraphBlock",
    "RenderTableBlock",
    "RenderTableCellBlock",
    "RenderTableRowBlock",
    "RenderTextInline",
    "ResolvedBlock",
    "ResolvedPageV1",
    "ResolvedRegion",
    "ResolvedSymbolRef",
    "ReviewFinding",
    "ReviewPackV1",
    "RuleChunkV1",
    "RunManifestV1",
    "RunSummaryV1",
    "SearchDocEntry",
    "SearchDocsV1",
    "SemanticConfidence",
    "Severity",
    "SourceManifestV1",
    "SpanEvidence",
    "StageScope",
    "SymbolAnchorKind",
    "SymbolCatalogV1",
    "SymbolEntry",
    "SymbolMatch",
    "SymbolMatchSetV1",
    "TableBlock",
    "TableCellBlock",
    "TableRowBlock",
    "TermMarkInline",
    "TextInline",
    "TranslatedSegment",
    "TranslationBatchV1",
    "TranslationResultV1",
    "TranslationSegment",
    "TranslationStyleCriticFindingV1",
    "TranslationStyleCriticPageV1",
    "TranslationStyleRepairChangeV1",
    "TranslationStyleRepairPageV1",
    "UnknownBlock",
    "WaiverSetV1",
    "WaiverV1",
    "WordEvidence",
    "XrefInline",
]
