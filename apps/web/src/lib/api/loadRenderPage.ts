import type { RenderPageData } from '../render/types';

export async function loadRenderPage(
  documentId: string,
  pageId: string,
  edition: string = 'ru',
): Promise<RenderPageData> {
  // Try edition-specific path first, fall back to root path
  const editionUrl = `/documents/${documentId}/${edition}/data/render_page.${pageId}.json`;
  const rootUrl = `/documents/${documentId}/data/render_page.${pageId}.json`;

  let res = await fetch(editionUrl);
  if (!res.ok) {
    res = await fetch(rootUrl);
  }
  if (!res.ok) {
    throw new Error(`Failed to load render page: ${res.status} ${rootUrl}`);
  }
  const data: RenderPageData = await res.json();
  if (!data.schema_version || !data.page) {
    throw new Error(`Invalid render page data for ${pageId}`);
  }
  return data;
}
