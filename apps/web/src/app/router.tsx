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

// Extraction review is reviewer-only and patch-drafting heavy, so it stays out
// of the reader's initial bundle just like /qa.
const ExtractionReviewPage = lazy(() =>
  import('../routes/ExtractionReviewPage').then((m) => ({ default: m.ExtractionReviewPage })),
);

function QaFallback() {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading QA findings">
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
          <Suspense fallback={<QaFallback />}>
            <QaDashboard />
          </Suspense>
        ),
      },
      {
        path: 'review/:pageId',
        element: (
          <Suspense fallback={<QaFallback />}>
            <ExtractionReviewPage />
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
