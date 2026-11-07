---
name: api-conventions
description: "Design or review a REST endpoint's resource contract, validation, compatibility and failure semantics. Триггеры: REST API, контракт эндпоинта, HTTP ошибки, проектирование API."
---

# Fit the API to its consumers

Read the existing API contract and relevant handlers/clients first. Keep established
resource naming, versioning and error envelopes unless changing that contract is
part of the task. These guidelines apply to REST; do not force HTTP conventions
onto an RPC protocol or invent a new response wrapper for an existing service.

## Decide the observable contract

- Describe the resource, caller, authorization boundary, accepted input and result.
  Validate ownership on the server, not only in the interface. Bound input sizes,
  collection limits and file types according to the actual operation.
- Choose methods by semantics: safe reads stay safe, and state changes are explicit.
  Distinguish a created resource, an accepted asynchronous job and a completed
  operation. A timeout is not evidence that a write did not occur.
- For retried mutations define an idempotency/reconciliation contract. State what
  a key identifies, its lifetime, concurrent-request behavior and how callers find
  an uncertain result. A new key is not a repair for an unresolved earlier attempt.
- Specify pagination/order/filter consistency where clients depend on it. For
  concurrent edits use a version or conditional request and a clear conflict result.
- Map failures by their actual meaning and the project's conventions: invalid
  input, authentication, forbidden access, missing resources, conflicts, limits,
  temporary dependency failures and internal defects are distinct cases. Preserve
  useful stable error identifiers without returning secrets or raw exception state.

Keep transport parsing and response translation at the boundary; put domain
decisions with their existing owner. A small handler need not acquire a new layer
hierarchy solely to satisfy a diagram. Trace externally supplied values to their
sinks when authorization or validation is in doubt.

Check the contract against callers, schemas and representative failure paths.
For a change, state compatibility/migration consequences and the tests that cover
them. Do not claim a chosen status code or envelope is universally mandatory.
