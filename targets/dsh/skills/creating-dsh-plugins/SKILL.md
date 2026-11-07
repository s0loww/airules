---
name: creating-dsh-plugins
description: "Create or repair a DSH plugin, tool or Agent composition against the installed host API. Триггеры: плагин DSH, инструмент DSH, расширение харнеса."
---

# Extend the installed DSH version

Start from the requested user behavior and inspect the installed host version,
package exports and native services. Prefer the host's current plugin-development
and composition-reference skills when available. An example from another build
does not establish API compatibility or register a tool.

Choose the narrowest mounting scope. A host plugin owns shared lifecycle/UI;
Agent-specific tools, skill providers and prompt sections belong in the intended
Agent composition. Verify isolation with another preset, not just the target one.

Give a tool a bounded schema and observable result contract. Use the native
session identity, permissions, filesystem/process confinement and cancellation.
Keep credentials and project connections outside distributed defaults. A backend
route needs native connection admission and CSRF for browser mutations.

Inspect existing ownership before writing a plugin or profile fragment. Implement
in the maintained source package, stage a versioned artifact and use the existing
installer/backup/receipt mechanism. Do not patch generated vendor files or rewrite
an entire profile to add one feature. Avoid unsupported browser globals, private
services and implicit permission escalation.

Test real native registration, representative tool behavior, malformed input,
read-only policy and disposal/restart in an isolated profile. Verify UI actions
against the actual backend. A settings form, copied SKILL.md or package on disk
does not prove that the plugin is mounted or functional. Report source, installed
artifact, validation and remaining limitations separately.
