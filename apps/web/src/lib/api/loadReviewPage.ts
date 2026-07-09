import type { RenderPageData } from '../render/types';
import { normalizeRenderPage } from '../render/normalize';

export interface ReviewPageLoad {
  /** Normalized page for rendering the block list + facsimile overlay. */
  page: RenderPageData;
  /**
   * The raw `blocks` array exactly as it appears in the artifact JSON. Reorder
   * patches replace `/blocks` with a permutation of these raw entries so the
   * round-trip is a faithful reorder (no re-materialized default fields).
   */
  rawBlocks: unknown[];
}

/**
 * Fetch a render page once and return both the raw blocks (for building
 * faithful reorder patch values) and the normalized page (for rendering).
 * Same edition-first / root-fallback URL strategy as `loadRenderPage`.
 */
export async function loadReviewPage(
  documentId: string,
  pageId: string,
  edition: string,
  signal?: AbortSignal,
): Promise<ReviewPageLoad> {
  const editionUrl = `/documents/${documentId}/${edition}/data/render_page.${pageId}.json`;
  const rootUrl = `/documents/${documentId}/data/render_page.${pageId}.json`;

  let res = await fetch(editionUrl, { signal });
  if (!res.ok) {
    if (res.status !== 404) {
      throw new Error(`Edition fetch failed: ${res.status} ${editionUrl}`);
    }
    res = await fetch(rootUrl, { signal });
  }
  if (!res.ok) {
    throw new Error(`Failed to load render page: ${res.status} ${rootUrl}`);
  }
  const raw: unknown = await res.json();
  const page = normalizeRenderPage(raw);
  const rawBlocks =
    raw !== null && typeof raw === 'object' && Array.isArray((raw as { blocks?: unknown }).blocks)
      ? ((raw as { blocks: unknown[] }).blocks as unknown[])
      : [];
  return { page, rawBlocks };
}
