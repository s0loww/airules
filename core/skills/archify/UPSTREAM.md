# Upstream of `archify`

- Upstream: <https://github.com/tt-a1i/archify> (MIT, see `LICENSE`)
- Vendored from our fork: <https://github.com/s0loww/diag_builder> (private), branch
  `detail-link`; the maintainer's local clone has remote `fork` = that repo, `origin` = upstream
- Pinned fork commit: `85215d389bb31f6eae820b2fe3a0202dcf474c83`
- Synced by: `ci/sync_archify.py` (airules repository, maintainer tool)

## What the fork adds

Two optional node fields in all five diagram types (architecture, workflow, sequence,
dataflow, lifecycle):

- `link` — `{ "href": "<neighbour>.html[#focus=…]", "label": "…" }`: a "Detail" action in
  the node passport that opens a neighbouring diagram. Relative `.html` or `https://` only.
- `description` — one to eight paragraphs (≤ 480 characters each), collapsible in the
  passport.

Diagrams that use these fields validate only with this build; upstream archify rejects
unknown node fields. The details and the fork's own checks are in the fork's `FORK.md`.

## What the sync leaves out

Tests (`test/`), rendered example pages (`examples/*.html`), `package-lock.json`, the
upstream release channel (`skill-release.json`, `scripts/check-update.mjs`,
`scripts/update-contract.mjs`), build-time generators (`scripts/generate-*.mjs`) and the
renderers' developer notes (`renderers/*/README.md`). The run-time needs **no npm
install** — Node >= 18 only.

SKILL.md is patched: the "Update awareness" section is removed (it would suggest updating
from tt-a1i and so dropping the fork's fields), the description is shortened.

## Resync procedure

1. In the fork: rebase `detail-link` on upstream `main` if needed, run
   `node test/golden.mjs` and `node scripts/generate-validators.mjs --check` there.
2. `python ci/sync_archify.py --check`, then `python ci/sync_archify.py`.
3. Smoke, from this skill's folder: `node bin/archify.mjs deliver architecture
   examples/web-app.architecture.json <tmp>.html --quality showcase --json` → 9/9 checks;
   then the same with `link` and `description` added to one component.
4. `python ci/check_layers.py`, `python ci/simulate_install.py`.
