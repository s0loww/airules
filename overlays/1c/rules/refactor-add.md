---
description: "Approach for refactoring 1C code — top-down analysis first, then bottom-up rewrite, with the impact / call-graph / verification tool sequence. Load when planning or executing a 1C refactor."
alwaysApply: false
kind: recipe
---

# Refactoring Approach

Use a hybrid approach. First, run a **top-down analysis** to understand the business logic: explicitly map the entire call chain and trace the data flow. Then refactor **bottom-up**, starting from the lowest-level utility functions. Finally, integrate the updated components back into the high-level procedures.

## Tool sequence

Exhaust the project's MCP search profile before falling back to plain-text grep (see `rules/tooling-playbooks.md → MCP-first Search`). The shared refactoring flow — do not skip steps for signature / export / type changes:

1. **Structural passport of the target.** Pull a full dossier of the object being refactored (structure, forms, dependencies, code modules, roles) via the code-search / metadata tool of the project profile before touching anything.
2. **Downstream impact.** Trace what breaks if the object changes — dependency / impact graph in `downstream` direction. Use a deeper depth for metadata relationships than for pure call chains.
3. **Callers / call graph.** Before changing a signature, export flag, or removing a routine, enumerate every caller (call graph in `callers` direction). Disambiguate by owning object when several routines share a name.
4. **Type usages.** Before renaming, removing, or changing the type structure of an object, find all references to that type.
5. **Code patterns.** Find all code fragments related to the refactored object — exact-text search for name matches, semantic search for purpose-based matches.
6. **Register writers (register / posting refactors only).** Enumerate the documents that post movements to the register, and the movements themselves, **before** changing them — via the project's register-writer / call-graph tooling. Do not modify movements outside `ОбработкаПроведения` / `ОбработкаУдаленияПроведения`.

After refactoring:

- **Re-search for old names / patterns** (high result count, exact + semantic) to confirm nothing still references the old shape.
- **Syntax check + code review** of the refactored code — run the project's "code check" and "code review" tools; loop until clean.

## Companion rules

| Concern | File |
|---|---|
| Full MCP-first search sequence | `rules/tooling-playbooks.md` |
| Query / architecture rules the refactor must preserve | `rules/dev-standards-architecture.md` |
| Register design invariants (dimensions, movements) | `rules/registers-design.md` |
| Locks / transactions when touching posting paths | `rules/locks-and-transactions.md` |
| Safe refactoring verification gates | `rules/verification-matrix.md` |
