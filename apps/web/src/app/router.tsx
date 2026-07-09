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

// S5U-1538: extraction review drafting route is lazy so the main reader bundle
// (article/facsimile rendering, navigation, glossary) is completely unaffected.
const ReviewPage = lazy(() =>
  import('../routes/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);

function QaFallback() {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading QA findings">
      <div className="skeleton-bone skeleton-heading" />
      <div className="skeleton-bone skeleton-block" />
    </div>
  );
}

function ReviewFallback() {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading extraction review">
      <div className="skeleton-bone skeleton-heading" />
      <div className="skeleton-bone skeleton-block" />
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
        // S5U-1538: lazy review route for typed PatchSetV1 drafting.
        // URL: /documents/:documentId/:edition/review/:pageId
        path: 'review/:pageId',
        element: (
          <Suspense fallback={<ReviewFallback />}>
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
