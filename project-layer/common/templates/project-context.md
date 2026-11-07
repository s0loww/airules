# Project context

This file is project-owned. Fill it during installation and keep it under
version control. Do not copy its concrete values back into the distribution.

## Authority

- Project identifier: `{{PROJECT_ID}}`
- Source of truth: {{SOURCE_OF_TRUTH}}
- Primary source root: {{PRIMARY_CODE_DIR}}
- Writable areas: {{WRITE_ZONES}}
- Read-only or protected areas: {{PROTECTED_ZONES}}

Indexes, RAG and MCP services are navigation and execution channels. Claims
about code are confirmed against the declared source of truth.

## MCP capabilities

- Code and platform knowledge: {{MCP_CODE_CAPABILITY}}
- Operational memory: {{MCP_MEMORY_CAPABILITY}}
- Project live data: {{MCP_PROJECT_DATA_CAPABILITY}}
- QA and test execution: {{MCP_QA_CAPABILITY}}
- Explicitly unavailable or excluded capabilities: {{MCP_EXCLUDED}}

The installed target receives only the allowlisted servers and tools. A server
present in a machine-wide or project-wide catalog is not implicitly allowed.

## Verification

- Fast local gate: {{FAST_GATE}}
- Static analysis gate: {{STATIC_ANALYSIS_GATE}}
- Deployment gate: {{DEPLOYMENT_GATE}}
- Functional test gate: {{FUNCTIONAL_TEST_GATE}}
- Production or live-data operations requiring explicit approval:
  {{APPROVAL_GATES}}

Record skipped and unavailable gates in the final report. Never silently
replace an unavailable gate with a weaker check.
