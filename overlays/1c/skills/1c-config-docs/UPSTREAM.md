# Source of `1c-config-docs`

- Developed in its own repository (maintainer's machine; workspace with runs and the
  equivalence regression next to it)
- Pinned commit: `d4e791ef4f542990ceab5bdc6d1a8e6b4e9cd0b2`
- Synced by: `ci/sync_config_docs.py` (airules repository, maintainer tool) — a byte copy of
  the skill folder, no patches: airules specifics live in the skill's own SKILL.md
  ("Агенты и модели")

## Dependencies in the target project

- Node ≥ 18 — without it the airules installer does not install the skill.
- `npm ci` in `scripts/` — once, on first use; the generator names this command (exit 2)
  when the `docx` package is missing. `scripts/.gitignore` keeps `node_modules/` out of git.
- The `archify` skill with node fields `link` / `description` — shipped in airules core.
- Chrome / Edge for PNG export; pwsh for `verify-docx`; MS Word optional (open-check).

## Resync procedure

1. In the skill repository: `npm test` in `scripts/`; the equivalence battery
   (`1c-config-docs-workspace/tools/run-equivalence.ps1`) when the generator changed.
2. `python ci/sync_config_docs.py --check`, then `python ci/sync_config_docs.py`.
3. `python ci/check_layers.py`, `python ci/simulate_install.py`.
