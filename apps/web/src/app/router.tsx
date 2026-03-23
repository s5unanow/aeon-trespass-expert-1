import { createBrowserRouter } from 'react-router';
import { ReaderPage } from '../routes/ReaderPage';
import { DocumentIndexPage } from '../routes/DocumentIndexPage';
import { GlossaryPage } from '../routes/GlossaryPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DocumentIndexPage />,
  },
  {
    path: '/documents/:documentId/:edition/glossary',
    element: <GlossaryPage />,
  },
  {
    path: '/documents/:documentId/:edition/:pageId',
    element: <ReaderPage />,
  },
]);
