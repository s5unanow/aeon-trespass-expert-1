/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type Version = string;
export type ConceptId = string;
export type Kind = string;
export type Version1 = string;
export type Lang = string;
export type Lemma = string;
export type Aliases = string[];
export type Patterns = string[];
export type Lang1 = string;
export type Lemma1 = string;
export type AllowedSurfaceForms = string[];
export type IconBinding = string | null;
export type SourcePattern = string;
export type TargetPattern = string;
export type PhraseTemplates = PhraseTemplate[];
export type ForbiddenTargets = string[];
export type Missing = string;
export type Forbidden = string;
export type NonPreferredAllowed = string;
export type Notes = string;
export type Concepts = ConceptV1[];

/**
 * Full concept registry for a document.
 */
export interface ConceptRegistryV1 {
  schema_version?: SchemaVersion;
  version?: Version;
  concepts?: Concepts;
}
/**
 * A single glossary/terminology concept.
 */
export interface ConceptV1 {
  concept_id: ConceptId;
  kind?: Kind;
  version?: Version1;
  source: ConceptSource;
  target: ConceptTarget;
  icon_binding?: IconBinding;
  phrase_templates?: PhraseTemplates;
  forbidden_targets?: ForbiddenTargets;
  validation_policy?: ValidationPolicy;
  notes?: Notes;
}
/**
 * English source form of a concept.
 */
export interface ConceptSource {
  lang?: Lang;
  lemma: Lemma;
  aliases?: Aliases;
  patterns?: Patterns;
}
/**
 * Russian target form of a concept.
 */
export interface ConceptTarget {
  lang?: Lang1;
  lemma: Lemma1;
  allowed_surface_forms?: AllowedSurfaceForms;
}
/**
 * High-priority multiword translation mapping.
 */
export interface PhraseTemplate {
  source_pattern: SourcePattern;
  target_pattern: TargetPattern;
}
/**
 * Severity policy for concept enforcement.
 */
export interface ValidationPolicy {
  missing?: Missing;
  forbidden?: Forbidden;
  non_preferred_allowed?: NonPreferredAllowed;
}
