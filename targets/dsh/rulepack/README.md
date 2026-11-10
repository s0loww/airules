# Embedded DSH rulepack

This target compiles the portable airules policy into a deterministic package
that a DSH harness can mount without copying the complete ruleset into every
project.

```powershell
python targets\dsh\rulepack\build.py `
  --source . `
  --output var\rulepack\airules-0.13.0

python targets\dsh\rulepack\verify.py `
  --output var\rulepack\airules-0.13.0
```

The output contains the root contract, lazy rules, role definitions, native
skills and the neutral testing contour.  `manifest.json` records every file
hash and exposes MCP roles only as logical names.  It never contains an MCP
URL, command, header, credential or machine-local binding.

The role definitions are packaged as `prompt-adapter`: the pinned DSH API has
no independent named-role registry, so the verified persona is loaded through
`airules_role` and passed to an ordinary DSH subagent prompt. Project facts and MCP bindings remain in
the project overlay or in machine-local DSH settings.

Build output must not exist before the command starts.  The builder stages the
entire package in a sibling temporary directory and publishes it with one
directory rename only after all portability checks pass.

For a distributable release, add `--require-clean`. Development artifacts may
record `source.dirty: true`; a release artifact must be built from a clean Git
tree and the builder refuses otherwise.

The embedded contract loads a rule by stable ID through the runtime tool
`airules_rule` with optional parameters `{ "id": "<rule-id>" }`. Calling the
tool without `id` returns the available rule inventory. It never relies on a
project-local `rules/` directory.
