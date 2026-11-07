# Testing contour

The concrete project fills commands, environments and approval boundaries.
The shared order is:

```text
doctor -> analyze -> deploy -> test
```

## Gates

1. **Doctor** — prove that the selected tools and target environment are
   reachable before interpreting application failures.
2. **Analyze** — run syntax and static-analysis checks against the changed
   scope. Existing unrelated diagnostics are recorded separately; new
   diagnostics block the change.
3. **Deploy** — update only the declared test contour. Production deployment
   is never an implicit continuation of a successful test deployment.
4. **Test** — run the smallest relevant functional set first, followed by the
   project-required regression or smoke set.

Mutating scenarios run only on an explicitly declared disposable or test
copy. A live or production contour requires the approval recorded in the
project context.

## Project binding

- Doctor command: `{{DOCTOR_COMMAND}}`
- Analyze command: `{{ANALYZE_COMMAND}}`
- Deploy command: `{{DEPLOY_COMMAND}}`
- Test command: `{{TEST_COMMAND}}`
- Test contour: {{TEST_CONTOUR}}
- Production contour: {{PRODUCTION_CONTOUR}}

## Optional isolated UI-test binding

Fill this section when a project has an isolated UI runner; otherwise record
the channel as unavailable. Stack-specific launch and evidence requirements
come from the stack testing rule (for 1C: `testing-1c.md`).

- Runner and reviewed version/hash: project-defined or unavailable.
- Dry-run command and apply command: project-defined.
- Supported host/session and toolchain versions: project-defined.
- Source snapshot, tested revision and disposable-copy root: project-defined.
- Manager/test identities and target business roles: project-defined.
- Scenario/library locations and required assertions: project-defined.
- Fresh report root, result format and verdict gates: project-defined.
- Timeout, process ownership, cleanup and retained-copy policy: project-defined.
- Separate visual/screenshot channel, when required: project-defined.
