# Third-party notices — `1c-metadata-manage`

The tool scripts of this skill are derived from a third-party project. This
notice is reproduced as its licence requires and travels with every copy of the
skill, including installed ones (`.claude/skills/1c-metadata-manage/NOTICE.md`).

## Nikolay-Shirokov/cc-1c-skills

- Upstream: <https://github.com/Nikolay-Shirokov/cc-1c-skills>
- Received via: <https://github.com/comol/ai_rules_1c> (Oleg Philippov), July 2026
  snapshot
- Licence: MIT

Covered: the PowerShell scripts under `tools/` (most carry a
`# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills` header; those
without one come from the same source). Local modifications, all under the same
MIT terms:

- every mutating script follows the airules script contract: DryRun by default,
  changes only with `-Apply`, credentials through `-PasswordEnv` instead of a
  password argument;
- `1c-role-compile/scripts/role-compile.ps1` is restored locally from the DSL
  reference;
- editors that auto-validate (`meta-edit`, `cf-edit`, `interface-edit`,
  `subsystem-edit`, `subsystem-compile`) resolve the validator under its real
  directory name, fail when it is missing, and propagate its exit code;
- `meta-edit` refuses `add-form` / `add-template` (registration without files);
- the event-handler suffix map of `form-compile` / `form-edit` uses the
  platform's event names (`OnEditEnd`, `DragEnd`, `Selection` → `Выбор`).

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
