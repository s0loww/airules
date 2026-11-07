---
name: 1c-debug-runtime
description: "Investigate a runtime 1C fault with discriminating hypotheses, owned probes and source/target-bound observations. Триггеры: отладить ошибку выполнения 1С, временные пробы, воспроизвести сбой."
---

# Investigate an observed runtime fault

Use when current source evidence does not establish the cause. State expected
and actual behaviour, the selected source/applied target and a small set of
distinguishable hypotheses. First prefer observations that need no mutation.

When the host exposes a project-scoped investigation notebook, inspect its real
schema, open a case, attach selected source/report artifacts, inspect freshness
and close with the observed outcome. A notebook records proposals and hashes;
it does not itself edit BSL, apply probes, run an ИБ, read ЖР or certify a caller's
conclusion. Without that service use the project's existing temporary record.

If instrumentation is necessary, propose a minimal owned marker and values that
separate the hypotheses. Exclude credentials, personal payloads and whole objects.
Read the exact files before editing; preserve other authors' probes. Actual edits,
syntax checks, deployment and reproduction use the project's available tools and
normal permissions. No skill or notebook replaces target guards or authorizes
Apply. Reuse a supported existing runner rather than introducing a parallel one.

Tie each observation to its probe/case, source revision and actual applied target.
A user's pending reproduction, timeout or missing log remains unknown. Use
`1c-event-journal` or `1c-tj-analysis` for the relevant log; an observed value from
another target is not confirmation here. Before retrying a stateful action,
reconcile the prior outcome.

After diagnosis, remove only owned instrumentation through the approved path and
verify cleanup in source and applied state where applicable. Closing the notebook
does not prove cleanup, successful deployment or a fixed business outcome. Preserve
unresolved evidence and explicit follow-up rather than announcing a green result.
