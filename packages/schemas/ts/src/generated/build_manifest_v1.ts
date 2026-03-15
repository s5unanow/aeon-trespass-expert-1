/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type BuildId = string;
export type DocumentId = string;
export type ContentVersion = string;
export type GeneratedAt = string;
export type PipelineVersion = string;
export type Path = string;
export type Sha256 = string;
export type SizeBytes = number;
export type Files = ReleaseFile[];

/**
 * Manifest for a published static release.
 */
export interface BuildManifestV1 {
  schema_version?: SchemaVersion;
  build_id: BuildId;
  document_id: DocumentId;
  content_version?: ContentVersion;
  generated_at?: GeneratedAt;
  pipeline_version?: PipelineVersion;
  files?: Files;
}
/**
 * A file included in the release bundle.
 */
export interface ReleaseFile {
  path: Path;
  sha256?: Sha256;
  size_bytes?: SizeBytes;
}
