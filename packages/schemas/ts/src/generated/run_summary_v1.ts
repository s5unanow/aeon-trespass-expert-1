/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type RunId = string;
export type DocumentId = string;
export type Status = string;
export type Edition = string;
export type PipelineVersion = string;
export type GitCommit = string;
export type StagesRequested = string[];
export type StagesCompleted = number;
export type StagesFailed = number;
export type PagesTotal = number;
export type PagesProcessed = number;
export type PagesCached = number;
export type PagesFailed = number;
export type PageFilter = string[] | null;
export type DurationS = number;
export type StartedAt = string;
export type FinishedAt = string;
export type ConfigHash = string;
export type SourcePdfSha256 = string;

/**
 * Human/LLM-readable summary written to artifact root after each run.
 */
export interface RunSummaryV1 {
  schema_version?: SchemaVersion;
  run_id: RunId;
  document_id: DocumentId;
  status?: Status;
  edition?: Edition;
  pipeline_version?: PipelineVersion;
  git_commit?: GitCommit;
  stages_requested?: StagesRequested;
  stages_completed?: StagesCompleted;
  stages_failed?: StagesFailed;
  pages_total?: PagesTotal;
  pages_processed?: PagesProcessed;
  pages_cached?: PagesCached;
  pages_failed?: PagesFailed;
  page_filter?: PageFilter;
  duration_s?: DurationS;
  started_at?: StartedAt;
  finished_at?: FinishedAt;
  config_hash?: ConfigHash;
  source_pdf_sha256?: SourcePdfSha256;
}
