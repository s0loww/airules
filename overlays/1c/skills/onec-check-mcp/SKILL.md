---
name: onec-check-mcp
description: "Diagnose missing or failing project MCP capabilities while separating discovery, transport and scope readiness. Триггеры: MCP не отвечает, инструмент 1С не найден, диагностика MCP."
---

# Diagnose the configured capability

Separate three facts: definition visible to this agent; configured transport
reachable; requested operation valid for the selected project/target. They require
different evidence. Use the host's actual manager/discovery interface to inspect
visible definitions without making calls.

For a user-requested connection check, inspect the configured connection's actual
status and supported health operation. A transport error differs from an unknown
method or an empty project index. An HTTP response to the wrong method is not a
successful capability check. Report exact bounded errors without secrets.

Do not assume local Docker, fixed ports, a facade or matching server names on every
machine. Inspect only the selected configured service; network probes, container
commands, connection changes and restarts retain their own authorization and native
permissions. Do not change a remote endpoint to localhost to make a probe pass.

Return the observed layer of failure, scope evidence and next resolving action.
Keep read-only diagnosis separate from saving settings, installing/upgrading MCP
or restarting shared services. Initial project parameters and connections belong
to their existing project/host settings owner, not another environment wizard
or donor-distribution installer.
