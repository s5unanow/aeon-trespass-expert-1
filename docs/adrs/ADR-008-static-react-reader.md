# ADR-008: Static React Reader

**Status:** Accepted
**Date:** 2026-03-15

## Context
The end-user reader must display translated rulebook pages with correct formatting, inline symbols, and navigation. We want a deployment model that requires no backend server at runtime -- just static files served from a CDN or local filesystem.

## Decision
The frontend is a static React application that consumes pre-built `RenderPageV1` JSON payloads. Each payload contains all blocks, symbols, and layout hints needed to render one page. The reader performs no markdown parsing, no API calls, and no dynamic content assembly.

## Consequences
- Deployment is a static file upload; no server infrastructure is required at read time.
- The render contract (`RenderPageV1`) is the only interface between pipeline and reader.
- Offline reading is trivially supported by bundling payloads with the app shell.
- Reader features like search or bookmarks operate on the structured payload, not raw text.
