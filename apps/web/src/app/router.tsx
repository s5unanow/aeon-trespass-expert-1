import { lazy, Suspense } from 'react';
import { createBrowserRouter } from 'react-router';
import { ReaderPage } from '../routes/ReaderPage';
import { DocumentIndexPage } from '../routes/DocumentIndexPage';
import { GlossaryPage } from '../routes/GlossaryPage';
import { ReaderLayout } from '../components/layout/ReaderLayout';

// Dashboard is gated behind a lazy import so it does not affect the reader's
// initial bundle — most reader sessions never visit /qa.
const QaDashboard = lazy(() =>
  import('../routes/QaDashboard').then((m) => ({ default: m.QaDashboard })),
);

// The extraction-review surface is lazy too (S5U-1539) — only reviewers visit
// it, so its code + the patch-drafting lib must not grow the reader bundle.
const ReviewPage = lazy(() =>
  import('../routes/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);

function LazyFallback({ label }: { label: string }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label={label}>
      <div className="skeleton-bone skeleton-heading" />
      <div className="skeleton-bone skeleton-block" />
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DocumentIndexPage />,
  },
  {
    path: '/documents/:documentId/:edition',
    element: <ReaderLayout />,
    children: [
      {
        path: 'glossary',
        element: <GlossaryPage />,
      },
      {
        path: 'qa',
        element: (
          <Suspense fallback={<LazyFallback label="Loading QA findings" />}>
            <QaDashboard />
          </Suspense>
        ),
      },
      {
        path: 'review/:pageId',
        element: (
          <Suspense fallback={<LazyFallback label="Loading review page" />}>
            <ReviewPage />
          </Suspense>
        ),
      },
      {
        path: ':pageId',
        element: <ReaderPage />,
      },
    ],
  },
]);
