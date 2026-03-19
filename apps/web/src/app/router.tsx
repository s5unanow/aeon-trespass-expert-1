import { createBrowserRouter } from 'react-router';
import { ReaderPage } from '../routes/ReaderPage';
import { DocumentIndexPage } from '../routes/DocumentIndexPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DocumentIndexPage />,
  },
  {
    path: '/documents/:documentId/:edition/:pageId',
    element: <ReaderPage />,
  },
]);
