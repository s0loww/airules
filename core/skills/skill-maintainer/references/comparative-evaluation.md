# Compare a changed skill with its baseline

Use for a material procedural change when an isolated task can show whether the
skill improves the actual outcome. Keep frontmatter/link validation as a separate
check; readable instructions alone do not establish effectiveness.

Prepare a small set of representative tasks and a nearby non-match. Compare the
current skill, the previous version and no skill against the same initial
artifacts and acceptance conditions. Each run starts in a fresh isolated
workspace/session; do not let an earlier arm's outputs, cache or memory become
the next arm's answer. Preserve the exact skill and fixture revisions.

Use the same explicitly chosen model/settings and tool allowlist across arms.
Do not inherit the operator's credentials, account files, home/profile, project
MCP connections or mutable working tree into an evaluation runner. Tool limits,
filesystem scope and child-process authority come from the host sandbox, not
claims inside the skill. A paid/model-backed run is an explicit operation;
deterministic fixture evaluation does not prove live model behavior.

Judge the resulting artifact/actions against observable acceptance criteria:
correctness, relevant tool/read evidence, forbidden side effects and a nearby
task that should not trigger the procedure. Keep failure, interrupted and unknown
outcomes visible. Compare bounded traces and cost/time when available; fewer
tokens cannot compensate for an incorrect result or a permission bypass.

Record per-task differences with evidence and their limits. A small comparison
supports that task set and environment; it is not a universal quality score.
Use the result to patch or retain the owner skill, then follow the host's normal
discovery/refresh mechanism. Do not publish, install globally or start a real
deploy merely to evaluate the instruction change.
