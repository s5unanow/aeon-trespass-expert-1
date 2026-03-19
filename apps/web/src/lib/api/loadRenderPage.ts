import type { RenderPageData } from '../render/types';

export async function loadRenderPage(
  documentId: string,
  pageId: string,
  edition: string = 'ru',
): Promise<RenderPageData> {
  const url = `/documents/${documentId}/${edition}/data/render_page.${pageId}.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load render page: ${res.status} ${url}`);
  }
  const data: RenderPageData = await res.json();
  if (!data.schema_version || !data.page) {
    throw new Error(`Invalid render page data for ${pageId}`);
  }
  return data;
}
