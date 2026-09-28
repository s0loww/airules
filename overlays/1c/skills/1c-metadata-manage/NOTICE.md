# Third-party notices — `1c-metadata-manage`

The tool scripts of this skill are derived from third-party projects. This
notice is reproduced as their licences require and travels with every copy of
the skill, including installed ones (`.claude/skills/1c-metadata-manage/NOTICE.md`).

Where the files come from and which upstream commit they match: `UPSTREAM.md`.

## Nikolay-Shirokov/cc-1c-skills

- Upstream: <https://github.com/Nikolay-Shirokov/cc-1c-skills>
- Received via: <https://github.com/comol/ai_rules_1c> (Oleg Philippov), which
  vendors these scripts with its own modifications
- Licence: MIT (text below)

Covered: the PowerShell scripts under `tools/` (most carry a
`# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills` header; those
without one come from the same source), the DSL specifications and references
under `tools/*/`, and the domain docs under `docs/`.

Not covered — written by comol/ai_rules_1c on top of the vendored code:
`tools/_common/DevEnv.ps1`, `tools/_common/MetadataAddress.ps1` and the
local-modification blocks inside the scripts. That repository states no licence
of its own; they are carried here as shared work of the airules / ai_rules_1c
authors.

Local modifications made here (airules), all under the same MIT terms:

- `tools/_common/Invoke-1CEdit.ps1` is ours: the airules script contract
  (DryRun by default, `-Apply` to write, `-PasswordEnv`) for every writing tool;
- every writing script carries a short gate inserted after its param block that
  makes it run only through that wrapper;
- sibling-script paths in `cf-edit`, `interface-edit`, `subsystem-compile`,
  `subsystem-edit` and `xdto-edit` point at the real folder; a missing validator
  fails and its exit code propagates;
- the event-handler suffix maps of `form-compile` / `form-edit` use the
  platform's event names (`OnEditEnd`, `Selection` → `Выбор`, `DragEnd`);
- docs: writing-tool calls point at the wrapper, password examples use
  `-PasswordEnv`, references to upstream-only rules point at airules rules.

The complete list of mechanical changes is `ci/sync_metadata_manage.py` in the
airules repository.

### MIT licence text

```
MIT License

Copyright (c) 2025-2026 Nick Shirokov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Desko77/claude-code-skills-1c — `uuid-check`

`tools/1c-uuid-check/scripts/uuid-check.ps1` is a port of
`check_uuid_duplicates.py` from <https://github.com/Desko77/claude-code-skills-1c>
(MIT), adapted to the Designer XML format by comol/ai_rules_1c. The MIT terms
above apply to it under that project's own copyright.
