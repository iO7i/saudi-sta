# Vertex-ui Arabic UI sync

Date: 2026-09-12 (Asia/Riyadh)

## Source freshness

- Repository: `https://github.com/vertex-suite-sa/vertex-ui.git`
- Remote default branch: `origin/main`
- Fetched remote SHA: `d1b3d2a5d03daee397dc6a412c959922fe68404f`
- Remote commit: `chore(release): publish audit-clean UI5 artifact (#176)`
- Guide source read from the fetched tree: `docs/HOW_WE_ARABIC.md`
- Guide revision: `2026-08-25`
- The Vertex-ui checkout was dirty before the fetch; no working-tree files in that checkout were changed.

## Applied to Saudi STA Workbench

- Arabic remains the default product language and primary reading direction.
- Visible operational states now have Arabic outcome labels with their exact machine codes retained as operator metadata.
- Generated tournament, recording, review, model, stage, and capability labels use Arabic display maps instead of exposing raw enum names.
- Scenario guidance is outcome-first and encourages natural speech; examples remain optional.
- Review states and evaluation evidence remain explicit rather than being promoted automatically to `GOLD`.
- Western digits are used in the UI scenario catalog; literal Arabic-digit examples were removed from the shared scenario data.
- RTL layout uses logical CSS properties, including inline borders/insets and start-aligned text, and tables scroll safely on narrow screens.
- Focus-visible outlines and a readable Arabic-first font stack were added without introducing an external runtime dependency.
- The English toggle remains available as a mirror of the Arabic surface.

## Verification

- Browser: local Saudi STA Workbench reloaded at `http://127.0.0.1:8000/`; Arabic default and English mirror checked.
- JavaScript syntax: `node --check static/app.js` passed.
- Full Python suite: `34 passed, 1 warning`.
- No model downloader, model `.part` file, model weight, recording, cache, or secret was changed by this UI sync.
