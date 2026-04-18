import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles/tokens.css';
import './styles/reset.css';
import './styles/layout.css';
import './styles/reader.css';
import './styles/glossary.css';
import './styles/qa.css';
import './styles/transitions.css';
import './styles/feedback.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
