---
name: 1c-element
description: "Recognize a 1C:Элемент/XBSL project or subtree and choose its actual text, build and verification capabilities instead of classic 8.x tools. Триггеры: 1С Элемент, XBSL, xbsl, Проект.yaml."
---

# Route an Элемент project correctly

Check the relevant subtree for `.xbsl`, paired YAML object definitions and
`Проект.yaml`, then read the project's own instructions and neighboring examples.
Use combined evidence: one file name or a textual mention is not enough to
reclassify an entire mixed repository. Keep classical BSL/XML and Элемент areas
separate when both are present.

Discover the project's actual XBSL editor, checker, build runner and runtime
capabilities. Standard text reading/search/editing and Git can still be useful
without them. A missing XBSL capability is a reported limitation, not proof that
every deployment of this host lacks support. A facade is not required.

Do not treat BSL Language Server, Designer, ibcmd, classic metadata XML or 8.x
templates as validation for XBSL. Preserve the existing YAML structure, object
identities, encoding and language conventions. Follow a neighboring object of
the same kind when making a permitted text change; use authoritative project
documentation for syntax not established by those sources.

For rename or structural changes, establish references across the paired files
and affected subtree first. Report the scope and intended change through the
normal project pipeline. Existing permissions and authorization govern edits,
commits, publication and remote operations; recognizing a file type grants none.

Run the configured Element-native check/build only when available and within
scope. Distinguish text/source review from a successful native build and from
live execution. Installing community tools, creating credentials or publishing
an application is separate work, not automatic setup for this skill.

Deliver changed files, the evidence used to identify the technology, checks
actually run and the precise next validation step when native tools are absent.
Project configuration may contain secrets; inspect only the non-secret fields
needed to resolve the current capability, not broad environment/account dumps.
