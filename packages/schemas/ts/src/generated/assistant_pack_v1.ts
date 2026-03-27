/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type Edition = string;
export type ChunksCount = number;
export type IndexPath = string;
export type ChunksPath = string;
export type BuildId = string;
export type GeneratedAt = string;
export type PipelineVersion = string;

/**
 * Manifest describing the assistant artifact bundle for a document edition.
 *
 * Produced by the pipeline export step, consumed by the assistant
 * query service to locate chunks and the FTS5 index.
 */
export interface AssistantPackV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  edition: Edition;
  chunks_count?: ChunksCount;
  index_path?: IndexPath;
  chunks_path?: ChunksPath;
  build_id?: BuildId;
  generated_at?: GeneratedAt;
  pipeline_version?: PipelineVersion;
}
