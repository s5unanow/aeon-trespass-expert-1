/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type SourceCriticFindingsCount = number;
export type RepairedParagraphIds = string[];
export type SkippedParagraphIds = string[];
export type ParagraphId = string;
export type BlockType = string;
export type BeforeText = string;
export type AfterText = string;
export type FindingQuotes = string[];
export type Diff = string[];
export type Changes = TranslationStyleRepairChangeV1[];
export type PostRepairTranslationQaCount = number;
export type PostRepairStyleQaCount = number;

/**
 * Per-page report for targeted Russian paragraph repair.
 */
export interface TranslationStyleRepairPageV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  source_critic_findings_count: SourceCriticFindingsCount;
  repaired_paragraph_ids?: RepairedParagraphIds;
  skipped_paragraph_ids?: SkippedParagraphIds;
  changes?: Changes;
  post_repair_translation_qa_count?: PostRepairTranslationQaCount;
  post_repair_style_qa_count?: PostRepairStyleQaCount;
}
/**
 * One paragraph changed by the targeted style repair stage.
 */
export interface TranslationStyleRepairChangeV1 {
  paragraph_id: ParagraphId;
  block_type?: BlockType;
  before_text: BeforeText;
  after_text: AfterText;
  finding_quotes?: FindingQuotes;
  diff?: Diff;
}
