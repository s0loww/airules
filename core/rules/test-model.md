---
description: "Layered test model: which verification channel answers which question, which layers gate a change and which only advise, how agent exploration graduates into a deterministic test, how shared and remote environments are reached, and what counts as run evidence. Load when choosing how to verify a change, planning a test run, or reading a run's verdict. Триггеры: модель тестирования, слои тестов, каналы проверки, гейт или рекомендация, UI-прогон агентом, удалённый контур, стенд, протокол прогона, baseline."
alwaysApply: false
kind: process
---

# Test model

`verification-matrix.md` picks *which* checks a change type needs; this rule
says *through which channel* each check runs and *what its verdict is worth*.
Concrete runners, ports and tools come from the project profile.

## Layers

| Layer | Question it answers | Channel (category) | Gates the change? |
| --- | --- | --- | --- |
| Environment | Is the target built from the sources I think it is? | scripted build/deploy with exit codes, a post-deploy probe | precondition — nothing below counts without it |
| Static | Does the code parse and pass analysis? | syntax check, static analysis against a baseline | yes |
| Logic | Does the routine compute the right value? | unit tests run headless, results as a machine-readable report | yes |
| Data | Did the operation leave the right state behind? | ground-truth queries through a sanctioned data channel | yes |
| UI regression | Does a known user flow still work? | replayable scenario runner | yes, for affected scenarios |
| UI exploration | What does the product do that nobody asserted? | an agent driving a browser or client like a new user | **no — advisory** |
| Simulation | Does a realistic workload expose gaps? | seeded environment, personas, before/after snapshots | **no — advisory** |

- A gating layer is **deterministic**: the same input gives the same verdict.
  Exploration and simulation are not, and their verdict never blocks a
  change on its own.
- **Exploration graduates by pinning.** A finding from an advisory layer
  becomes gating only when it is re-expressed as a deterministic test in a
  gating layer (`intent-testing.md`). Until then it is a question, not a
  failure.
- Pick the **cheapest layer that can observe the behavior**. A value check
  does not need a UI; a form that must open does not need a data query.
- A layer the project has not deployed is reported as *not deployed*, never
  imitated through another layer.

## Environment boundaries

- **Local disposable environments** — built by the project's scripts from
  the sources, one environment per concurrent run, isolated working state,
  a timeout on every tool call, and a recovery ladder that escalates from
  graceful session close to state reset. The data store itself is never
  deleted automatically unless the environment is declared disposable.
- **Shared or remote environments** (a team test contour, a staging
  cluster) — reached **only through their sanctioned channels**: the normal
  client, a published service endpoint, the regular deployment path. Never
  attach a local tool directly to their data store, bypassing the server
  that owns locks, caches and sessions — and never with a tool build that
  differs from the server's.
- **Tool build = target build.** A local tool used against an environment
  runs the exact build that environment runs, selected explicitly, not
  "the newest installed".
- **One run per environment at a time**, under an inter-process lock.
  Services that hold sessions on the environment (published endpoints,
  bridges) are stopped and restarted by the deploy step itself, not by
  hand.

## Evidence

- **Every run leaves a uniquely named artifact** that no later run
  overwrites. A verdict without a preserved artifact does not count.
- **A verdict is a diff, not a count.** Compare against a baseline run on
  the unchanged sources plus a registry of known defects: a new failure is a
  regression, a known one is a reference to the registry, a bare
  "82 of 99 passed" is not a verdict.
- **An interrupted run is not a failure.** Mass errors from the channel
  itself (the endpoint returns server errors for everything, the
  environment rebooted) mark the run *interrupted*: fix the environment,
  re-run from a checkpoint, record the incident separately.
- **Verify through the consumer's channel.** A check through a convenient
  side path (a raw HTTP call where users go through a proxy, an admin
  session where users have restricted rights) proves the side path, not the
  product.

## Companion rules

- `verification-matrix.md` — which checks a change type needs; gate D runs
  the gating layers above.
- `test-discipline.md` — what makes an individual test worth keeping and
  which oracles lie.
- `intent-testing.md` — how exploration findings become ratified intent and
  pinned tests.
