import { createContext, useContext, type ReactNode } from 'react';

/**
 * Per-page glossary mentions context.
 *
 * `RenderPageData.glossary_mentions` is a list of `concept.<id>` strings the
 * pipeline detected on the page. We surface it via context so the
 * `GlossaryText` matcher inside `InlineRenderer` doesn't have to be prop-
 * drilled through every block kind. Empty array is the safe default for
 * components rendered outside a `PageGlossaryProvider` (e.g., the glossary
 * page itself, where keyword highlighting is intentionally inert).
 */
const PageGlossaryContext = createContext<readonly string[]>([]);

interface PageGlossaryProviderProps {
  mentions: readonly string[];
  children: ReactNode;
}

export function PageGlossaryProvider({ mentions, children }: PageGlossaryProviderProps) {
  return <PageGlossaryContext value={mentions}>{children}</PageGlossaryContext>;
}

export function usePageGlossaryMentions(): readonly string[] {
  return useContext(PageGlossaryContext);
}
