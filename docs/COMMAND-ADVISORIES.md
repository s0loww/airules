# Opt-in command advisories

Command advisories attach a bounded hint to a matching shell event. They are
not a policy gate, a command runner or proof that a deployment failed. The
existing rule reminders and continuity hooks work independently.

## Enable a target

For Codex, set the reviewed build binding `"command_advisories": true`.
Render, inspect the plan and apply through `targets/codex/render.py` as usual.
The default is `false`: no command-advisory registrations are emitted.
Review and trust the new exact hook definitions in the client separately.
The renderer never approves hooks or changes global settings.

For Claude, opt in while following ONBOARD and merge the registrations into
the existing project settings. Preserve unrelated hooks, including custom
deployment and diagnostic handlers. `ci/simulate_install.py
--command-advisories` exercises this layout in a clean disposable target;
it is not an updater for an existing project.

The generic script handles `PreToolUse` and `PostToolUse` for `Bash` and
`PowerShell`. The 1C deployment advisory is an additional `PreToolUse`
handler. Scripts run with Python's `-B` option. Native client permissions
and hook trust remain authoritative.

DSH's embedded rulepack does not execute Codex/Claude lifecycle hooks.
Shipping this release does not add a DSH shell interception API. Keep the
DSH project overlay and use supported native diagnostics explicitly.

## Supply project data

The runtime reads only the project's `.airules/command-advisories.json`.
The installer ships scripts, a schema and examples under the target's hooks
directory; it does not create or overwrite the active project table.
Absent, disabled or unsafe tables produce no hint. Each adapter validates
the configuration for its own feature before emitting a hint.

Copy and review `command-advisories.example.json`, validate it against
`command-advisories.schema.json`, then adapt the literals and hints to the
project. Start with `enabled: false`. A minimal enabled table is:

```json
{
  "schema_version": 1,
  "enabled": true,
  "pre": [
    {
      "id": "reviewed-migration",
      "command_any": ["migrate-project.ps1"],
      "hint": "Confirm the selected test target and review the dry-run report."
    }
  ],
  "post": [
    {
      "id": "access-denied",
      "output_any": ["Permission denied", "Access is denied"],
      "hint": "Check the current identity and the requested path's permissions."
    }
  ]
}
```

`command_any`, `output_any` and `output_all` use literal substring matching,
not regular expressions. Post-event rules need an output condition;
pre-event rules need a command condition. `ignore_case` selects
case-insensitive matching. Hints are fixed project text: command arguments,
output and credentials are not interpolated into them. Keep secrets out of
the table itself.

Input, table size, entry count and emitted context are bounded. Unrelated
events stay silent. Repeated hints and the hook's own output are suppressed;
malformed input cannot block an ordinary tool call. A silent exit is not
evidence that a test, check or deployment succeeded.

## Deployment diagnostics

The 1C overlay supplies `deploy-advisory.py`. Its project `deploy` section
selects command markers and the diagnostic text; it does not contain
infobase credentials or an environment-file path. The syntax diagnostic
distinguishes the whitespace `-Dynamic "-"` form passed through PowerShell
`-File` from `-Dynamic:"-"`.

Process inspection, when explicitly configured, is read-only and bounded.
It must identify a configured target before associating a process with it.
A running web service is not proof that a particular infobase is locked.
No advisory terminates processes, restarts services, deploys a configuration
or widens a native permission grant. See the overlay example and schema for
the exact optional probe settings and applicability limits. Process probes
are disabled by default (`probe_processes: false`). Enabling them additionally
requires an unambiguous `targets` entry with reviewed `command_any` selectors
and an absolute target `path`. `probe_timeout_seconds` is limited to 0.1–2
seconds; no configured command or credential-file reader is accepted.

## Updating existing projects

Do not replace a project's Bash groups with the generated registrations.
Review overlap with existing diagnostic scripts first: either retain the
project handlers or migrate their data deliberately, so the same symptom
does not produce two copies of a hint. Infobase names, local paths,
credentials, accounting exceptions and access policy remain project-owned.

Run the assertion tests and disposable rendered-target smoke checks before
changing a live project's table. An offline event probe establishes matching
and wire format; it does not establish live-client delivery, model behavior
or readiness of the target environment.
