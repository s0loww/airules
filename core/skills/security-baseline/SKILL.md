---
name: security-baseline
description: "Review changed trust boundaries or security-sensitive behavior using concrete source-to-sink evidence. Триггеры: ревью безопасности, секреты и доступ, инъекции, граница доверия."
---

# Review a security boundary

Use for a requested security review or a concrete security-sensitive change.
Review the affected boundary and reachable paths; do not turn an unrelated edit
into a mandatory full-system audit. Project review policy owns the verdict
format and escalation process.

Identify protected data/actions, the actor controlling each input, authentication
and authorization checks, and the sink that reads, executes, persists or exposes
it. Trace alternate routes and asynchronous work, not just the visible UI check.
Separate a demonstrated path from an untested hypothesis.

## Follow the relevant paths

- **Credentials and observability:** trace secrets through storage, subprocess
  environments, exceptions, diagnostics and artifacts. Verify masking happens
  before persistence; a masked UI does not protect raw logs. Use placeholders in
  findings rather than reproducing discovered secrets.
- **Authority and sessions:** check resource ownership and authorization at the
  mutation boundary. For browser-backed actions, inspect native admission,
  origin/CSRF behavior and session lifetime as applicable. Hiding a control does
  not constrain another endpoint.
- **Untrusted input:** follow paths into queries, process arguments, filesystem
  operations, rendering and model/tool actions. Prefer the project's safe APIs
  and context-appropriate encoding; distinguish data from executable instructions.
  Include link traversal and executable uploads when files cross the boundary.
- **External operations:** inspect deadlines, cancellation and ownership of work
  after a timeout. Retry only when the operation's replay contract permits it;
  partial output or an unknown mutation result is not proof of a safe retry.
- **Dependencies and deployment:** use the actual dependency closure and exposure
  to assess impact. Support version/support-status claims with current primary
  evidence. An old version number or hypothetical future use alone is not a
  demonstrated vulnerability.

Choose checks matching the path: an unauthorized resource request, a malformed
input at the sink, an output encoding case, or cancellation after work starts.
Use isolated fixtures where possible and keep live probing within authorization.

## Report actionable findings

For each finding provide the entry point, violated invariant, reproducible
condition, source location and practical impact. Use the project's severity
scheme with evidence-based confidence; identify residual uncertainty. Group
duplicate manifestations under their shared cause and propose a bounded fix.
Distinguish pre-existing findings from regressions in the reviewed change.

An exposed credential warrants a remediation plan, not automatic key rotation,
history rewriting or deletion of evidence. Follow the owner's authorized response
process. This skill does not grant testing access or require a new scanner or
remote service merely to produce a review.
