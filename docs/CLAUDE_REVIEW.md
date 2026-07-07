# mdview — Production Readiness, Architecture & Product Audit

**Reviewed:** `md-viewer` v0.1.0 (single-module Python package, `src/md_viewer/cli.py` + `template.html`)
**Codebase size:** ~1,170 lines Python, ~600 lines HTML/CSS/JS, zero tests

---

## Executive Summary

This is a well-executed *prototype* with real UX polish (GitHub-style tree, dark mode, breadcrumbs, live reload, a working admin panel) wrapped around an architecture that cannot support the product vision. The gap isn't cosmetic — it's structural. Three things stand out immediately:

1. **The "local-first, no internet, no remote APIs" promise is already broken.** PlantUML diagrams are rendered by POSTing your diagram source to `plantuml.com`'s public server, and Mermaid/PlantUML's JS libraries are pulled from a CDN at runtime. This is the single most important finding in this review — it directly contradicts requirement #1 in your own spec.
2. **The server is single-threaded and blocking**, using bare `socketserver.TCPServer`. Every request — including the 2-second live-reload poll — queues behind whatever request is currently running. This alone invalidates the stated performance targets at any real scale.
3. **The whole app is one 1,170-line file driven by module-level global state that mutates on import** (CLI parsing, directory validation, and a full `rglob('*.md')` filesystem walk all happen at import time, before `main()` even runs). This makes the code untestable as written — there isn't a single test in the repo — and is why several requirements you specified (extension-based filtering, full-text search, raw/rendered toggle) simply don't exist yet despite adjacent features suggesting they might.

None of this means start over. The rendering pipeline, the nav-tree UX, and the admin settings panel are genuinely good ideas, reasonably well executed for a v0.1. But this is pre-alpha, not release candidate. See the Final Recommendation.

---

## Scores

| Dimension | Score /10 | Rationale (short) |
|---|---|---|
| Overall Product | 4 | Good taste in UX, but core promises (local-first, performance) are unmet |
| Production Readiness | 2 | No tests, no threading, no auth on mutating endpoints, broken dependency manifest |
| Architecture | 3 | Monolithic single file, global mutable state, two competing templating systems |
| Performance | 3 | Untested claims; O(n) string-replace nav caching won't survive 10k+ files, let alone 100k |
| Maintainability | 3 | No tests, no types, no logging, dead-simple logic buried in 200+ line functions |
| UX | 7 | Genuinely nice — GitHub Explorer feel, dark mode, breadcrumb, persisted tree state |
| Developer Experience | 4 | `pip install -r requirements.txt` alone is broken (missing Jinja2); no CONTRIBUTING, no CI |

---

## Strengths

- **Nav tree UX is close to right.** Persisted expand/collapse state via `localStorage`, auto-expand-to-active-file, GitHub-style depth shading — this is the correct reference point (VS Code Explorer) and it's tastefully done.
- **Theming is solid.** CSS custom properties with a real dark-mode branch via `prefers-color-scheme`, consistent icon system per file extension.
- **Path traversal is handled correctly** for the primary file-serving path: `(DOCS_DIR / path).resolve()` followed by `relative_to(DOCS_DIR.resolve())` correctly rejects `../` escapes and symlinks that resolve outside the root.
- **Symlink cycle protection exists** in the nav-tree builder (`visited` set keyed by `os.path.realpath`), which shows real awareness of a subtle bug class most first drafts miss.
- **The exclude-directory model (name vs. absolute path) is a reasonable design** — distinguishing `node_modules` (name-based, matches anywhere) from `project/generated/swagger` (path-based, matches once) is exactly the right mental model for this feature, even though the implementation needs work (see below).
- **Admin panel with hot-reloadable config** is the right instinct for requirement #4 ("changes should hot reload without restart") — it's just incomplete (directories only, no extensions).

---

## Weaknesses

- Everything lives in one file with global state set at import time. Untestable, unreviewable in isolation, and fragile — importing `cli.py` for any reason (including from a test file) triggers filesystem I/O and can call `sys.exit()`.
- Two independent HTML rendering paths: the Jinja2 `template.html` for normal pages, and a hand-rolled Python f-string template for `/_admin`. They duplicate the entire CSS variable palette. They will drift.
- No caching of rendered document output despite an explicit `<20ms cached document` target — every request re-reads the file, re-runs a hand-rolled regex preprocessor, and re-runs the full Markdown pipeline from scratch.
- "Search" only filters filenames already present in the DOM. There is no content search at all, despite full-text search being an explicit target (`<50ms search response`).
- No extension-based filtering (`show only .md`, `hide .log`) despite this being requirement #4, item 3–4 in your spec, verbatim.
- `requirements.txt` is missing `Jinja2`, which `cli.py` imports unconditionally at module load. `pip install -r requirements.txt && mdview` currently crashes on a clean environment.

---

## Critical Issues

These block a public release regardless of anything else.

### C1. Local-first promise is violated by design (Security + Product)
`renderPlantUML()` in `template.html` encodes the *entire diagram source* and sends it to `https://www.plantuml.com/plantuml/svg/<encoded>` via an `<img src>`. Any PlantUML block in any document — including private/proprietary docs — is transmitted to a third-party server with no opt-out, no warning, and no local rendering fallback. Combined with Mermaid and the PlantUML encoder being pulled from `cdn.jsdelivr.net` with no Subresource Integrity hash, "no internet, no cloud, no remote APIs" (your requirement #1) is false as shipped. This needs to be fixed before anything else — it's not a performance nit, it's a broken product promise and a real data-exfiltration vector for anyone browsing internal documentation.

### C2. Single-threaded, blocking server architecture
`socketserver.TCPServer` processes one request at a time. There is no `ThreadingMixIn`, no async runtime. Concrete consequence: while one client is loading a large Markdown file (which does regex preprocessing + full Markdown conversion + nav-tree string surgery, all synchronously), *every other request blocks* — including the live-reload poll from the same tab, and any request from a second browser tab. This is incompatible with "should feel instantaneous" and with supporting 100,000+ files.

### C3. Raw HTML passthrough with no sanitization
The Markdown pipeline (`codehilite, toc, tables, fenced_code`) does not disable raw HTML, and no sanitizer (e.g., `bleach`, `nh3`) is applied to the output. `python-markdown` renders embedded raw HTML/`<script>` verbatim by default. Given the product's actual use case — pointing `mdview` at *any* local project, including ones you cloned from GitHub and didn't author — this is a real stored-XSS vector: a malicious `CONTRIBUTING.md` in a cloned repo executes arbitrary JS in the app the moment you browse to it. This matters more here than in a typical Markdown tool because "browse any local project's docs" is the explicit design goal.

### C4. No CSRF protection on state-mutating endpoints
`/_admin/save` accepts POST and mutates server-side config (exclude rules) with no token, no Origin check. The server binds to `127.0.0.1` only, which limits *remote* exposure, but this is exactly the shape of "localhost CSRF" / DNS-rebinding attack that's bitten many local dev-server tools: any web page open in the same browser can silently POST to `http://localhost:8000/_admin/save` and rewrite your exclusion rules. Low severity today (worst case is a rewritten config), but the pattern is dangerous once editing/saving local files (your stated future roadmap) lands on this same unauthenticated endpoint.

### C5. Broken dependency manifest
`requirements.txt` omits `Jinja2`, which is a hard, unconditional import in `cli.py`. Anyone following the README-implied `pip install -r requirements.txt` path gets an `ImportError` at first run. `pyproject.toml` and `requirements.txt` should be a single source of truth — right now they silently diverge.

### C6. Zero test coverage
There are no tests anywhere in the archive. Combined with global mutable state set at import time, this isn't just "needs more tests" — the current structure actively resists being tested. Any refactor from here forward is high-risk without a safety net.

---

## High Priority Improvements

1. **Render PlantUML locally** (e.g., via a bundled PlantUML jar + local Java, or a pure-Python renderer) or clearly gate remote rendering behind an explicit opt-in flag with a warning banner. Same treatment for the Mermaid/PlantUML-encoder CDN scripts — vendor them locally so the app truly works offline.
2. **Move to `ThreadingHTTPServer`** (or migrate to FastAPI + Uvicorn as your own spec recommends once complexity justifies it) so one slow request can't stall the whole app.
3. **Sanitize rendered HTML** before sending to the client — allowlist-based (`nh3`/`bleach`), even in a local-first tool, given the "browse any project" use case.
4. **Cache rendered documents** keyed by `(path, mtime)`. This alone gets you most of the way to the `<20ms` cached-open target without re-architecting anything.
5. **Kill the eager, string-replace-based nav rendering.** Build the tree as data (nested dicts/dataclasses), cache *that*, and compute active/expanded state via small JSON sent to the client — not via `.replace()` on a multi-megabyte HTML blob on every request.
6. **Fix `requirements.txt`** to match `pyproject.toml` exactly, or delete `requirements.txt` entirely and standardize on `pyproject.toml` (recommended — one manifest, no drift).
7. **Add a real content-search endpoint** (even a naive `grep`-style scan with a size cap is a legitimate v1; a proper index is a v2 concern) — filename-only filtering doesn't meet your own stated bar.
8. **Add extension-based show/hide filtering** to the admin panel — it's explicitly named in your spec and currently doesn't exist at all.
9. **Split `cli.py` into modules**: `server.py`, `nav.py` (tree building), `render.py` (markdown pipeline), `config.py` (exclude rules + admin persistence), `cli.py` (arg parsing + entrypoint only). Move all CLI parsing and directory validation *inside* `main()`, not at module import time.

## Medium Priority Improvements

- Replace the hand-rolled indented-code-block regex preprocessor with a proper Markdown extension, or verify `fenced_code` already handles this correctly (it likely does for most real-world cases — the custom regex logic looks like it's compensating for a misunderstanding of a stdlib extension rather than a real gap).
- Unify the admin page onto the same Jinja2 template system as the rest of the app instead of a separate hardcoded f-string with duplicated CSS variables.
- Reconsider the port-conflict-resolution feature (~200 lines: detecting the PID on a busy port and offering to `kill -9` it). This is significant scope and risk (killing an arbitrary, possibly unrelated process) for a documentation viewer. A simpler "port busy, trying next available port automatically" with no interactive kill prompt is safer and removes ~150 lines.
- Add basic structured logging behind a `--verbose`/`-v` flag; `log_message` currently does nothing at all, which will make every future bug report a guessing game.
- Add type hints — the codebase has none, which will slow down any contributor trying to safely extract modules per the item above.

## Low Priority Improvements

- The `get_file_description()` regex that strips a fixed emoji set (`⭐🏗️🔧📋❓🔍📊📖`) from titles is oddly specific and will silently miss any emoji not in that literal set — either generalize (strip all emoji via a Unicode range) or drop the feature.
- `format_display_name()`'s abbreviation-detection heuristic (all-caps, ≤5 chars ⇒ treat as abbreviation like "HLD"/"API") is clever but undocumented and will misfire on real filenames (e.g., `TODO_list.md` → "TODO" preserved, "List" capitalized — probably fine, but there's no test proving the intended behavior, so it's already technical debt).
- Icons dictionary (`FILE_ICONS`) duplicates the same SVG path definition for `.json`, `.yaml`, `.yml` verbatim (copy-pasted, not shared) — extract shared icon paths into constants.

---

## Architecture Review

**Current shape:** a single Python module that (a) parses `sys.argv` and validates the target directory at import time, (b) defines an `http.server.SimpleHTTPRequestHandler` subclass that does routing, Markdown rendering, nav-tree generation, breadcrumb generation, and admin-page HTML generation all as methods on one class, and (c) a `main()` that handles port conflicts and starts the blocking server loop.

This violates separation of concerns in a way that will make the two biggest roadmap items — a proper plugin/renderer architecture and a FastAPI/React split — much harder than they need to be, because there's no seam anywhere in the current code to plug into. The renderer isn't a renderer, it's 150 lines inlined into `do_GET`. The nav tree builder isn't a component, it's a closure inside a request handler method. There's no `Config` object — configuration is five different module-level globals mutated from two different places (startup, and the admin POST handler) with `global` statements reaching across function boundaries.

**Recommendation:** before any UI or feature work, extract:
- `Config` (immutable snapshot + a `reload()` method) — replaces the five scattered globals
- `DocTree` (data structure + builder, no HTML in it) — replaces `_build_nav_tree`
- `Renderer` (protocol/ABC with a `MarkdownRenderer` implementation) — this *is* your future plugin architecture, introduced now instead of later
- `Server` (thin HTTP layer that composes the above)

This is a 1–2 day refactor that costs little and unlocks everything else on your roadmap (plugins, tests, FastAPI migration, multi-root workspaces).

---

## Performance Review

Your stated targets (300ms cold start, 20ms cached open, 100ms uncached open, 50ms search, 16ms tree toggle, 100k+ files) are the right targets for the product. The current implementation does not meet them and — more importantly — several parts of the design make them structurally unreachable without a rewrite of that part:

- **Cold start does a full recursive filesystem walk (`DOCS_DIR.rglob('*.md')`) just to print a warning.** On a 100k-file repo, this walk alone can take multiple seconds. This should be removed or deferred (check lazily, or check only the top 2–3 levels).
- **Nav tree generation is O(files) string concatenation, done once, then reused via full-string `.replace()` calls on every request** to toggle `active`/`has-active` classes. For 100k files, that cached HTML string is plausibly 10–50MB of markup; every page load performs several linear scans and rewrites of that string server-side, then ships the entire thing to the browser, which then has to parse and lay out 100k+ DOM nodes with zero virtualization. This is the single biggest scalability blocker in the codebase — worse than the threading issue, because it doesn't degrade gracefully, it just stops being usable somewhere in the 5k–20k file range.
- **No document cache.** Every `GET` of a Markdown file re-reads from disk and re-runs the full conversion pipeline, even for the file you just viewed 2 seconds ago via live-reload polling.
- **Blocking, single-threaded server** (see C2) means these already-heavy per-request costs also serialize across all connected clients/tabs.

None of this requires FastAPI or a rewrite to fix in the short term. In order of ROI: (1) cache rendered docs by mtime, (2) switch to threaded serving, (3) replace string-replace nav caching with structured data + client-side active-state computation, (4) add DOM virtualization or on-demand lazy subtree loading for the sidebar once tree size crosses a threshold (a few hundred nodes).

---

## Security Review

| Area | Status | Notes |
|---|---|---|
| Path traversal | ✅ Handled | `resolve()` + `relative_to()` check is correct for the primary content path |
| Symlink cycles (nav tree) | ✅ Handled | `visited` set prevents infinite recursion |
| Raw HTML / XSS | ❌ Not handled | No sanitizer; `python-markdown` passes raw HTML through by default (C3) |
| Remote data exfiltration | ❌ Present | PlantUML source sent to a public third-party server (C1) |
| CSRF on admin endpoints | ❌ Not handled | No token/Origin check on `/_admin/save` (C4) |
| Bind address | ✅ Good | Bound to `127.0.0.1` only, limiting remote network exposure |
| Arbitrary process kill | ⚠️ Risky UX | `kill -9`'ing whatever process holds the requested port, based only on PID from `lsof`, with no ownership/sanity check |
| Large file handling | ❌ Not addressed | No file-size cap before reading a Markdown file fully into memory and rendering it |
| Malicious Markdown (huge files, deeply nested structures) | ❌ Not addressed | No timeout or size guard around the Markdown conversion call |
| Supply chain (CDN scripts) | ❌ Not handled | Mermaid/PlantUML-encoder loaded from CDN with no SRI hash |

---

## UX Review

The visual and interaction design is the strongest part of this codebase and is genuinely close to the VS Code Explorer / GitHub reading-experience blend you're targeting: persistent sidebar, breadcrumb, dark mode, hover states, active-item highlighting with auto-scroll, filename search with highlighting. This is not the part that needs rework.

What's missing relative to your own vision doc:
- No raw/rendered toggle (spec requirement #6) — there's currently only one view mode.
- No keyboard navigation or command palette (both explicitly named as roadmap items — fine to defer, but worth noting neither has any scaffolding yet, e.g. no keydown listeners at all in `template.html`).
- Search only matches what's already rendered into the sidebar DOM, not file contents — this will frustrate the exact user this tool is for (an engineer who remembers a phrase, not a filename).
- The "Explorer" sidebar has no way to distinguish "no doc files exist here" from "everything is filtered out" — both currently look like an empty tree with no explanatory state.

---

## Scalability Review

| File count | Expected behavior today | Primary bottleneck |
|---|---|---|
| ~100 | Fine | — |
| ~1,000 | Noticeably slower nav updates; still usable | String-replace on cached nav HTML |
| ~10,000 | Sluggish page loads (multi-hundred-ms+), sidebar scroll gets janky | Nav HTML size + unvirtualized DOM |
| ~50,000 | Likely multi-second page loads; single-threaded server makes concurrent tabs painful | Nav generation + blocking I/O |
| 100,000+ | Likely to hang or become effectively unusable; browser may struggle to render the DOM at all | All of the above, compounded |

None of this is a knock on the idea — it's a completely normal state for a first working version. But it means the "supports 100,000+ files" claim in your spec is aspirational relative to the current implementation, not a description of it. Reaching it requires (in priority order): a lazy/paginated tree API instead of one giant inline blob, frontend virtualization, and moving off a single-threaded blocking server.

---

## Maintainability Review

Low, for reasons already covered: one file, global mutable state set at import time, no tests, no types, no logging, two divergent templating systems. The good news is none of this is deep — it's a "hasn't been done yet" problem, not a "wrong foundation" problem. The rendering logic itself (Markdown conversion, nav building) is straightforward enough that extracting it into testable, injectable components is a mechanical refactor, not a redesign.

---

## Technical Debt

- Global state / import-time side effects (biggest item — blocks testing entirely)
- Two templating systems (Jinja2 + hand-rolled f-string) with duplicated CSS
- `requirements.txt` / `pyproject.toml` drift
- Hand-rolled indentation-fixing regex of uncertain necessity
- Port-kill subprocess logic (high complexity-to-value ratio)
- No sanitization layer on rendered HTML
- No cache layer despite performance targets assuming one exists

---

## Future Roadmap (from your Long-Term Vision list)

**Prioritize:**
- Full-text search (currently the single biggest functional gap vs. your own spec)
- Raw/rendered toggle (foundational for the editing feature that depends on it)
- Extension-based filtering (named explicitly in your spec, not yet built)
- Lazy tree loading / virtualization (blocks the 100k-file goal entirely without it)
- Local PlantUML/Mermaid rendering (fixes the local-first violation)

**Defer, with scaffolding now:**
- Plugin architecture — don't build the plugin *system* yet, but do extract the `Renderer` interface now (see Architecture Review) so plugins are a natural extension later rather than a rewrite.
- Command palette, keyboard shortcuts — genuinely nice, genuinely not urgent.

**Reject or reconsider:**
- Document graph / link graph / cross-document references — high complexity, unclear connection to "make reading local docs effortless." This is closer to a knowledge-management feature (Obsidian's territory) than a documentation-browser feature. Worth explicitly deciding this is out of scope rather than letting it linger on the roadmap.
- The interactive port-kill flow — recommend simplifying to auto-select next available port with no prompt, removing ~150 lines and a real risk (killing the wrong process) for a feature that doesn't touch your product's core value.

---

## Top 25 Highest-ROI Improvements

1. Stop sending PlantUML source to a public third-party server (C1)
2. Switch to `ThreadingHTTPServer` (C2)
3. Add HTML sanitization to the Markdown render output (C3)
4. Fix `requirements.txt` to include Jinja2 / consolidate to one manifest (C5)
5. Move CLI parsing + directory validation into `main()`, out of module import time
6. Cache rendered document HTML keyed by `(path, mtime)`
7. Replace string-replace-based nav active-state injection with structured data
8. Add a file-size cap / timeout around Markdown conversion (DoS guard on huge files)
9. Vendor Mermaid + PlantUML-encoder locally instead of loading from CDN
10. Add extension-based show/hide filtering to the admin panel
11. Add real content search (even a naive linear scan with a result cap is a legitimate v1)
12. Add CSRF protection (Origin check, minimum) on `/_admin/save`
13. Extract a `Renderer` interface/protocol — becomes the seed of the plugin architecture
14. Extract `DocTree` as a data structure, separate from its HTML rendering
15. Extract `Config` as a single object, remove the five scattered globals
16. Add a basic test suite around path resolution, exclude-rule matching, and nav-tree building (highest-leverage tests given current risk profile)
17. Remove or defer the eager `rglob('*.md')` scan at startup
18. Simplify port-conflict handling to auto-pick next port, drop the interactive kill flow
19. Add `--verbose` logging instead of a fully suppressed `log_message`
20. Add a raw/rendered toggle in the UI (foundation for future editing)
21. Unify admin page onto the same Jinja2 template system as the main viewer
22. Add DOM virtualization or lazy subtree fetching to the sidebar for large trees
23. Add type hints as modules get extracted (do this *during* the refactor, not after)
24. Deduplicate repeated SVG path definitions in `FILE_ICONS`
25. Add an "empty vs. fully filtered" distinguishing state to the sidebar UX

---

## Final Recommendation

**Would I ship this publicly today? No.**

What would stop me, specifically:
- The local-first promise is currently false (PlantUML → public internet). That's not a rough edge, it's the headline claim of the product being untrue on first use for anyone who writes a diagram.
- No sanitization on rendered HTML, combined with "point this at any local project" as the explicit use case, is a real XSS exposure for a tool people will reasonably use on repos they didn't write.
- `pip install -r requirements.txt` is broken today for a new user.
- Zero tests means every fix from here on is a gamble against silent regressions.

None of these are far away — this is a few focused days of work, not a rewrite. The UX foundation is worth keeping and building on. I'd fix items 1–8 above, add a minimal test suite, and *then* revisit this audit before any public release. The architecture question (FastAPI/React vs. current stack) can wait until after that — right now the current stack isn't the bottleneck, the missing seams inside it are.