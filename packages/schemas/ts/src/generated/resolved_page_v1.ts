/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
export type SourceEvidenceHash = string;
export type RegionId = string;
/**
 * Semantic region classification.
 */
export type RegionKind =
  | 'body'
  | 'sidebar'
  | 'header'
  | 'footer'
  | 'figure_area'
  | 'table_area'
  | 'callout_area'
  | 'margin_note'
  | 'full_width'
  | 'unknown';
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type X01 = number;
export type Y01 = number;
export type X11 = number;
export type Y11 = number;
export type EvidenceIds = string[];
export type Confidence = number;
export type Regions = ResolvedRegion[];
export type BlockId = string;
export type BlockType =
  | 'heading'
  | 'paragraph'
  | 'list'
  | 'list_item'
  | 'table'
  | 'table_row'
  | 'callout'
  | 'figure'
  | 'caption'
  | 'rule_quote'
  | 'divider'
  | 'unknown';
export type RegionId1 = string;
export type EvidenceIds1 = string[];
export type SymbolId = string;
export type InstanceId = string;
/**
 * How a symbol attaches to its context.
 */
export type SymbolAnchorKind = 'inline' | 'prefix' | 'cell_local' | 'block_attached' | 'region_annotation';
export type EvidenceIds2 = string[];
export type Confidence1 = number;
export type SymbolRefs = ResolvedSymbolRef[];
export type Confidence2 = number;
export type Strategy = string;
export type Reason = string;
export type OriginalConfidence = number;
export type Blocks = ResolvedBlock[];
/**
 * Block IDs in reading order
 */
export type MainFlowOrder = string[];
/**
 * Type of anchor/parent relationship between resolved entities.
 */
export type AnchorEdgeKind =
  | 'caption_to_figure'
  | 'block_to_callout'
  | 'symbol_to_block'
  | 'block_to_region'
  | 'aside_to_main';
export type SourceId = string;
export type TargetId = string;
export type Confidence3 = number;
export type AnchorEdges = AnchorEdge[];
export type SymbolRefs1 = ResolvedSymbolRef[];
export type Overall = number;
export type RegionSegmentation = number;
export type ReadingOrder = number;
export type BlockClassification = number;
export type SymbolResolution = number;
export type Extractor = string;
export type Version = string;
export type EvidenceIds3 = string[];

/**
 * Semantic resolution of a page, referencing evidence entities.
 */
export interface ResolvedPageV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  source_evidence_hash?: SourceEvidenceHash;
  regions?: Regions;
  blocks?: Blocks;
  main_flow_order?: MainFlowOrder;
  anchor_edges?: AnchorEdges;
  symbol_refs?: SymbolRefs1;
  confidence?: SemanticConfidence | null;
  provenance?: ProvenanceRef | null;
}
/**
 * A semantic region/zone on the resolved page.
 */
export interface ResolvedRegion {
  region_id: RegionId;
  kind: RegionKind;
  bbox: Rect;
  norm_bbox: NormRect;
  evidence_ids?: EvidenceIds;
  confidence?: Confidence;
}
/**
 * Bounding box in PDF points: [x0, y0, x1, y1].
 */
export interface Rect {
  x0: X0;
  y0: Y0;
  x1: X1;
  y1: Y1;
}
/**
 * Bounding box in normalized [0,1] page coordinate space.
 */
export interface NormRect {
  x0: X01;
  y0: Y01;
  x1: X11;
  y1: Y11;
}
/**
 * A semantic block with evidence traceability.
 */
export interface ResolvedBlock {
  block_id: BlockId;
  block_type: BlockType;
  region_id?: RegionId1;
  evidence_ids?: EvidenceIds1;
  symbol_refs?: SymbolRefs;
  confidence?: Confidence2;
  fallback?: FallbackProvenance | null;
}
/**
 * A symbol occurrence resolved from evidence.
 */
export interface ResolvedSymbolRef {
  symbol_id: SymbolId;
  instance_id?: InstanceId;
  anchor_kind: SymbolAnchorKind;
  evidence_ids?: EvidenceIds2;
  bbox?: Rect | null;
  confidence?: Confidence1;
}
/**
 * When a resolved entity used fallback/alternative extraction.
 */
export interface FallbackProvenance {
  strategy: Strategy;
  reason?: Reason;
  original_confidence?: OriginalConfidence;
}
/**
 * Directed relationship between two resolved entities.
 */
export interface AnchorEdge {
  edge_kind: AnchorEdgeKind;
  source_id: SourceId;
  target_id: TargetId;
  confidence?: Confidence3;
}
/**
 * Per-aspect confidence scores for the resolution process.
 */
export interface SemanticConfidence {
  overall?: Overall;
  region_segmentation?: RegionSegmentation;
  reading_order?: ReadingOrder;
  block_classification?: BlockClassification;
  symbol_resolution?: SymbolResolution;
}
/**
 * Reference to upstream evidence or extraction source.
 */
export interface ProvenanceRef {
  extractor: Extractor;
  version: Version;
  evidence_ids?: EvidenceIds3;
}
