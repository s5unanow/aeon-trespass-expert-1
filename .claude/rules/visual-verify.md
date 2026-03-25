When working on changes that affect page rendering (web components, CSS, pipeline render/export stages, facsimile overlays), verify the result visually before creating a PR:

1. Ensure the dev server is running on `localhost:3001`
2. Use Playwright MCP to navigate to affected pages:
   - `mcp__playwright__playwright_navigate` to `http://localhost:3001/documents/ato_core_v1_1/{edition}/{pageId}`
3. Take a screenshot with `mcp__playwright__playwright_screenshot` (fullPage, savePng to `tmp/`)
4. Read the screenshot to visually confirm the change looks correct
5. If interactive elements exist, use `mcp__playwright__playwright_hover` or `playwright_click` to verify they work
6. Use `mcp__playwright__playwright_evaluate` to inspect DOM state when needed

This applies to files matching:
- `apps/web/src/components/**`
- `apps/web/src/routes/**`
- `apps/web/src/styles/**`
- `scripts/export_to_web.py`
- `scripts/_export_blocks.py`
- `apps/pipeline/src/atr_pipeline/stages/render/**`
