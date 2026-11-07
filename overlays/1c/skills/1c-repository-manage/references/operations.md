# Object-scoped repository operations

Confirm the supported operation in the current capability/runner schema. These
are semantic categories, not universal tool names or command-line arguments.

| Operation | Required facts | Result to establish |
|---|---|---|
| Status/history/diff | Binding, configuration/extension and requested version/range | Repository identity, observed revisions and bounded evidence |
| Dump | Exact repository version and fresh output artifact | What was exported; this does not update an ИБ |
| Lock | Exact metadata objects, ownership and requested revision behavior | Success/conflict/unknown for each object and resulting lock owner |
| Update | Exact objects/revision and treatment of local changes | What changed in the local configuration and which sources need refresh |
| Commit | Exact objects, authorized publication and meaningful comment | Published revision and per-object result, including locks retained |
| Unlock | Exact objects, actual owner and local-change state | Which locks were released; distinguish release from discard |

An empty object list, wildcard or root plus descendants may target the whole
configuration. Resolve an explicit finite list before execution. If the API
requires an object rather than a реквизит or табличная часть, name the owner
and show that normalization. Treat `Конфигурация` as a specific root object
only where the runner documents that meaning; it is not permission to include
all descendants.

A lock conflict belongs to the other owner. Report it and re-scope or obtain
the appropriate decision; do not remove it automatically. Multiple objects may
have different outcomes, so retain partial ownership and supported cleanup in
the handoff. A fresh report and observed lock state, not exit code alone,
establish completion.

Force/discard requires the project's explicit allow setting and authorization
for that concrete exceptional effect. Do not set the allow flag yourself to
make an operation pass. Existing verified authorization remains effective;
another prompt is needed only when the intended effect or scope is missing.
Forced unlock can discard uncommitted changes and is not ordinary cleanup.

Bind/unbind, repository creation and user administration are separate tasks.
Do not use them to bypass an ordinary lock or update failure. If such work is
explicitly requested, identify its actual administrative capability and effects
instead of claiming this skill's ordinary runner provides them.
