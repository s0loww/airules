---
description: "Optional compression of command output before it enters the model context via an rtk-style CLI proxy: what to wrap, what never to wrap, and how to recover full output. Load when a compression proxy is available (rtk --version succeeds) or the user asks about saving tokens on command output. Триггеры: rtk, сжатие вывода, экономия токенов на командах, длинный вывод."
alwaysApply: false
---

# Tool-output economy (pluggable, requires an installed proxy)

Command output (git, tests, listings, logs) is a major share of an agentic
session's input tokens, and most of it is noise for the model. A CLI proxy
such as [rtk](https://github.com/rtk-ai/rtk) rewrites supported commands into
compressed, information-dense equivalents before their output reaches the
context window. Measured on real repositories: `git diff` −80%, `git log`
−60%, listings and grep −50…95%; unsupported commands pass through unchanged.

## When this rule applies

- The proxy is **installed and detectable**: `rtk --version` succeeds.
  If it is not installed, this rule is inert — the agent must **not**
  install it, add hooks, or change user configuration on its own; adopting
  the proxy is the user's decision.
- Applies to shell commands only. Native harness tools (file read, built-in
  search) do not pass through the proxy.

## What to wrap (prefix the command with `rtk`)

High-volume, read-only commands whose full output is navigation, not an
artifact:

- `rtk git log / diff / status / show` — history and change review;
- `rtk ls / tree / find` — structure scouting (requires coreutils on PATH:
  available in a bash session, usually absent in plain PowerShell — there
  fall back to raw commands);
- `rtk grep / rg` — content search across many files;
- `rtk err <command>` — wrap any long-running check or validator when only
  errors/warnings and the verdict matter;
- `rtk test <runner>` — test runs where only failures matter;
- container/cloud listings (`rtk docker/kubectl/aws …`) when supported.

Compression philosophy matches lazy loading: the proxy returns the minimal
useful view (e.g. `rtk ls` shows one level); drill down with a narrower call
instead of requesting everything at once.

## What never to wrap

- **Mutations**: any command that changes state — applies, deploys, data
  migrations (including `-Apply` runs of contract scripts). Their full log
  is the verification artifact.
- **Verification-gate evidence**: when `verification-matrix.md` requires a
  check's output as evidence (syntax check, static analysis, schema
  validation), consume the full output — or wrap with `rtk err` **only** if
  the pass/fail verdict and every error/warning line survive; when in doubt,
  run raw. Measured caveat: `rtk err` reliably keeps the verdict and stderr
  but can drop stdout detail lines (e.g. a checker that prints violations to
  stdout and only the summary to stderr loses the violations). Verify once
  per checker before relying on it; already-terse checkers gain nothing —
  run them raw.
- For noisy project-specific tools, prefer a **project filter**
  (`.rtk/filters.toml`, committed with the repo) over generic `rtk err`: it
  states explicitly which lines survive. Project filters require one-time
  user approval per machine (`rtk trust` — a safety gate against malicious
  filters in cloned repos); the agent must not run `rtk trust` itself —
  surfacing the need to the user is the correct move.
- Commands whose output is machine-parsed downstream (reports consumed by
  scripts).

## Trust and recovery

- Compressed output is **navigation, not the source of truth** — the same
  status indexes and RAG have in the root contract. Decisions that depend on
  exact content are verified against the raw file/log.
- If a compressed result looks incomplete or ambiguous — do not guess:
  re-run the command raw, or read the proxy's full-output copy (rtk tee
  recovery stores it on failures; `rtk config` shows the tee mode and path).
- Exit codes pass through the proxy; a failing command stays failing.

## Channel and environment notes

- Deeper integration (automatic rewriting of every shell call via the
  harness hook) exists for some channels — an install-time decision noted in
  the distribution's channel adapters. Installing such hooks is a user decision;
  this rule only covers explicit `rtk`-prefixed calls, which work in any
  channel with no configuration.
- Telemetry of the reference proxy is opt-in; for fully offline work set
  `RTK_TELEMETRY_DISABLED=1`.

## Relation to economy mode

Combines well with `orchestrator-economy.md`: scouting subagents that wrap
their bulk reads save tokens on the cheap tiers, and the orchestrator's
spot-checks stay raw (they are verification, not navigation).
