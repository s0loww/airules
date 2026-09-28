# Upstream of `1c-metadata-manage`

- Source: <https://github.com/comol/ai_rules_1c>, `content/skills/1c-metadata-manage/`
- Pinned upstream commit: `20a083e5bd9fa41402ad8428b740c4c01f0cc3d6`
- Synced by: `ci/sync_metadata_manage.py` (airules repository, maintainer tool)

## What the sync takes, and what stays ours

| | Files |
|---|---|
| taken as is (plus the mechanical changes below) | `tools/**` PowerShell scripts, DSL specs and references; `docs/*.md` |
| not taken | Python ports (`*.py` — the PowerShell tools do not call them), upstream `docs/CHANGELOG.md`, `docs/v8unpack-cf.md` (points at an upstream-only skill), upstream `tools/_common/Invoke-1CEdit.ps1` |
| ours, never overwritten | `SKILL.md`, `NOTICE.md`, `UPSTREAM.md`, `docs/edit-preview.md`, `docs/ssl-patterns.md`, `tools/_common/Invoke-1CEdit.ps1`, `tools/1c-form-scaffold/scripts/add-form.ps1` |

Mechanical changes, all re-applied by the sync script:

1. a gate after the param block of every writing script (`GATED` in the script);
2. local fixes as exact-anchor patches (`PATCHES`) — an anchor that no longer
   matches fails the sync;
3. docs: writing-tool calls rewritten to the wrapper, `-Password` examples to
   `-PasswordEnv`, upstream rule references mapped to airules rules, a DryRun
   note under each title.

## Resync procedure

1. `git -C D:\AI_Projects\_ref\ai_rules_1c pull`
2. `python ci/sync_metadata_manage.py --check` — errors mean an unclassified new
   tool or a patch whose anchor moved: classify it / fix or drop the patch;
3. `python ci/sync_metadata_manage.py` — writes, updates the pin above;
4. parse-check all scripts, run the wrapper smoke test, `python ci/check_layers.py`,
   `python ci/simulate_install.py`;
5. review `SKILL.md` against upstream's task table for new domains.
