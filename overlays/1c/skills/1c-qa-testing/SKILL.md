---
name: 1c-qa-testing
description: "Verify a thin-client 1C scenario through the project's available QA interface with observe–act–assert evidence. Триггеры: проверить через QA, сценарий тонкого клиента, UI-проверка 1С."
---

# Verify a bounded QA scenario

Load the project's testing policy and identify the test ИБ, applied configuration,
client/session ownership and required cases. Project QA is an optional independently
configured capability. Discover its live schema and supported target before use;
do not invent a server prefix, UI method or connection.

Start from observation. Resolve controls by current state, perform one meaningful
action, then assert a business result rather than the absence of an error dialog.
Record required, executed, failed and skipped case IDs. A screenshot or opened
window does not prove that a save, проведение or register effect succeeded.

Preserve user/native permissions for every action. Source read-only access does
not grant QA writes to an ИБ. If the required QA/target is unavailable, return a
bounded blocked result or use a supported browser/hidden-desktop route under the
same test contract; do not silently switch to another database.

Keep fresh evidence tied to the actual source/applied target and case. Timeout,
lost session or unknown mutation is not PASS; reconcile before replay. Clean up
only owned sessions/data using the established project procedure. For a persistent
suite use `1c-ui-regression`, not a second ad hoc test engine.
