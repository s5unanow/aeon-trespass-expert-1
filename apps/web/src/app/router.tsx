import { createBrowserRouter } from 'react-router';
import { ReaderPage } from '../routes/ReaderPage';
import { DocumentIndexPage } from '../routes/DocumentIndexPage';
import { GlossaryPage } from '../routes/GlossaryPage';
import { ReaderLayout } from '../components/layout/ReaderLayout';

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
        path: ':pageId',
        element: <ReaderPage />,
      },
    ],
  },
]);
