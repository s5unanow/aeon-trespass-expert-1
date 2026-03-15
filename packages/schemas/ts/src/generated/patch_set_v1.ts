/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type PatchId = string;
export type TargetArtifactRef = string;
export type Op = string;
export type Path = string;
export type Operations = PatchOperation[];
export type Reason = string;
export type Author = string;

/**
 * A set of typed patches for a specific artifact.
 */
export interface PatchSetV1 {
  schema_version?: SchemaVersion;
  patch_id: PatchId;
  target_artifact_ref?: TargetArtifactRef;
  operations?: Operations;
  reason?: Reason;
  author?: Author;
}
/**
 * A single patch operation.
 */
export interface PatchOperation {
  op: Op;
  path: Path;
  value?: Value;
}
export interface Value {
  [k: string]: unknown;
}
