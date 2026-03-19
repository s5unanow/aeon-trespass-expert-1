/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type RunId = string;
export type PipelineVersion = string;
export type GitCommit = string;
export type ConfigHash = string;
export type SourcePdfSha256 = string;
export type Edition = string;
export type StartedAt = string;
export type FinishedAt = string;
export type StageName = string;
export type Scope = string;
export type EntityId = string;
export type CacheKey = string;
export type Status = string;
export type ArtifactRef = string;
export type DurationMs = number;
export type Stages = StageInvocationRef[];
export type QaSummaryRef = string;
export type ReleaseRef = string;

/**
 * Metadata for a single pipeline run.
 */
export interface RunManifestV1 {
  schema_version?: SchemaVersion;
  run_id: RunId;
  pipeline_version?: PipelineVersion;
  git_commit?: GitCommit;
  config_hash?: ConfigHash;
  source_pdf_sha256?: SourcePdfSha256;
  edition?: Edition;
  started_at?: StartedAt;
  finished_at?: FinishedAt;
  stages?: Stages;
  provider_versions?: ProviderVersions;
  environment?: Environment;
  qa_summary_ref?: QaSummaryRef;
  release_ref?: ReleaseRef;
}
/**
 * Reference to a stage invocation within a run.
 */
export interface StageInvocationRef {
  stage_name: StageName;
  scope: Scope;
  entity_id: EntityId;
  cache_key: CacheKey;
  status?: Status;
  artifact_ref?: ArtifactRef;
  duration_ms?: DurationMs;
}
export interface ProviderVersions {
  [k: string]: string;
}
export interface Environment {
  [k: string]: string;
}
