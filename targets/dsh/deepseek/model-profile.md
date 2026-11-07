# Model profile — DeepSeek in DSH

This profile contains only behavior that is safe to carry into DSH. Facts
measured in another harness, including effective context limits and effort
scales, are not treated as DSH facts.

## Rendered block

```text
## Model profile: DeepSeek in DSH

- Inspect referenced files and current tool state before making claims about
  the codebase. Do not speculate about unopened code.
- Keep changes minimal and on task: no speculative features, broad refactors
  or test-only hacks.
- Report skipped, blocked, failing and unverified work plainly.
- Follow the Rule Index lazily: load only rules relevant to the current task.
- Give conclusions and evidence; do not emit raw internal reasoning.
```

## DSH measurements still required

- delegation behavior and useful parallelism;
- self-verification behavior without extra prompting;
- adherence to a long contract after compaction;
- instruction-versus-example weighting;
- routing quality for English rule bodies and Russian requests;
- effective context and effort controls exposed by DSH.

Promote a measured correction into the rendered block only after a repeated
eval shows that it changes behavior in the intended direction.
