# EP-045 STEP 2 — Changed-Files-Only Delivery Manifest

This archive contains **only** the files created or modified by
EP-045 STEP 2. It is not a full-project archive — every path below is
relative to the project root and should be applied on top of the
existing repository (already containing EP-001 through EP-044,
unmodified except as noted).

## Created

| File | Purpose |
|---|---|
| `web/public/index.html` | EP-045 Web Dashboard — single-page entry point (connection indicator, status area, command form, result area, error area). |
| `web/public/app.js` | Dashboard client-side logic. Plain JavaScript, no framework, no build step. Same-origin `fetch()` calls to `/health`, `/api/v1/status`, `/api/v1/commands` only — no API base URL configuration needed (see rationale below). |
| `web/public/styles.css` | Dashboard styling. Plain CSS, responsive (single column on narrow viewports, two-column grid on wider ones), respects `prefers-reduced-motion`. |
| `tests/EP045/__init__.py` | Package marker for the new test suite. |
| `tests/EP045/test_web_dashboard.py` | `NAME = "EP045"` test suite (38 tests): static-file serving correctness, path-traversal protection, EP-043 route non-regression when `static_dir` is configured, and `Bootstrap` wiring of `api.web_dashboard_dir` (present/absent/empty/missing-directory). |
| `docs/architecture/designs/EP045_DESIGN.md` | The EP-045 STEP 1 design document (included here for completeness; already delivered separately at STEP 1, unchanged content). |

## Modified

| File | Change | Why |
|---|---|---|
| `src/core/api/rest_api_server.py` | Added an **optional** `static_dir` parameter to `RestApiServer.__init__`/`start()`, a new `_try_serve_static()` method on the request handler, and a `static_dir` property. Module docstring updated with a "Static File Serving (EP-045, optional)" section. | **Required for the owner-approved same-origin architecture** — see "Why this change was required" below. Behavior is unchanged (still returns the original 404) whenever `static_dir` is `None`, which remains the default. No route in `_ROUTES`, no existing response shape, and no existing error code changed. |
| `src/bootstrap.py` | Added `Bootstrap._resolve_web_dashboard_dir()` and one new line in `_build_rest_api_server()` to read `api.web_dashboard_dir` from config and pass it to `RestApiServer`. | Wires the new optional capability through configuration, following the exact same tolerant-degrade convention already used for `api.enabled`/`api.host`/`api.port`. |
| `config/config.yaml` | Added `api.web_dashboard_dir: "web/public"` with an explanatory comment block. | Points the new capability at the dashboard's static files. An empty value or a missing directory both degrade safely to "not served" (verified by test). |
| `src/modules/test_module.py` | Added one import line: `import tests.EP045.test_web_dashboard`. | Registers the new suite with `TestRegistry`, following the exact existing per-EP registration convention. |

## Deleted

None.

## Why `src/core/api/rest_api_server.py` needed to change

The owner approved a **same-origin** hosting model and explicitly
asked to avoid CORS unless technically unavoidable (decision #3).
`RestApiServer` is the only process bound to the API's host:port —
`http.server.ThreadingHTTPServer` owns that socket exclusively, and
before this change it returned `404 not_found` for any path outside
its fixed three-route table (`_ROUTES`). Two ways exist to put the
dashboard's HTML/CSS/JS on the *same* origin as that API:

1. Have `RestApiServer` itself serve those files (this change), or
2. Run a second process on the exact same `host:port` — impossible;
   only one listener can bind a given TCP port.

Since option 2 is not physically possible and the owner ruled out
introducing CORS, option 1 was the only remaining path to satisfy
the approved same-origin decision. The change is deliberately
minimal and strictly additive:

- A **new optional constructor/config parameter**, not a new route in
  `_ROUTES` — the three existing API routes and their exact response
  shapes, status codes, and error codes are untouched.
- **Off by default** (`static_dir=None`): any deployment that does not
  set `api.web_dashboard_dir` gets byte-for-byte the same behavior
  `RestApiServer` had before EP-045 (confirmed by
  `_test_static_dir_none_preserves_ep043_404_behavior`).
- **Only `GET`** requests are ever considered for static serving; any
  other method on a non-API path still falls straight through to the
  original 404 (`_test_wrong_method_on_static_path_falls_through_to_get_only`).
- **Path-traversal safe**: every resolved candidate path is checked
  with `Path.relative_to(static_dir)` before being read; a traversal
  attempt is refused and still returns 404, not 500
  (`_test_path_traversal_attempt_returns_404_not_500`).
- **No new dependency**: uses only `pathlib` and `mimetypes`, both
  already-imported-elsewhere standard library modules.
- **No authentication, no CORS headers, no new security surface**
  added — the security posture (decision #4) is unchanged; a static
  HTML/JS/CSS file is no more sensitive than the dashboard bundle
  itself, and the three JSON API routes' own auth posture is
  untouched.

No other file under `src/core/api/` was modified. No file under
`desktop/` was read as a target, imported, or modified — EP-044 is
untouched, confirmed by the unchanged **52/52** result.

## Consequence worth noting (not a silent decision)

Because the dashboard is served same-origin, `app.js` calls
`fetch("/health")`, `fetch("/api/v1/status")`, and
`fetch("/api/v1/commands")` using **relative URLs**. This means V1
needs **no dashboard-side API base URL / host / port configuration
at all** — EP045_DESIGN.md's Open Question 8 (config storage
mechanism) is naturally sidestepped for V1, not resolved by a new,
separate decision. If a future EP moves to a separate-origin
deployment, that config layer would need to be added at that time.

## Verification performed

- `python -m py_compile` on every modified/new Python file: clean.
- Manual functional smoke test of static serving (root, named file,
  Content-Type inference, missing file, traversal attempt): all
  behaved as designed.
- `test EP045` (new suite): **38 passed, 0 failed, 0 skipped**.
- `test EP043` (unmodified): **83 passed, 0 failed, 0 skipped** — no
  regression.
- `test EP044` (unmodified, `desktop/` untouched): **52 passed, 0
  failed, 0 skipped** — no regression.
- Full regression, every registered suite: **5,549 passed, 0 failed,
  0 skipped** (the prior 5,511 baseline + EP-045's 38 new tests).

## What was intentionally NOT done (per owner decisions)

- No CORS policy was added — same-origin serving avoided the need.
- No authentication was added — decision #4.
- No network exposure beyond the existing `api.host` default
  (`127.0.0.1`) — unchanged.
- No chat, memory browser, agent management, workflow editor, voice,
  file management, or notifications — decision #5.
- No build step, no `package.json`, no frontend framework — decision
  #1.
- `desktop/` (EP-044) was not modified.
- EP-046 was not started.
- No full-project archive was created — this is the changed-files-only
  delivery requested.
