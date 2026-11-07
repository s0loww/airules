# DSH embedded rulepack contracts

`rulepack-manifest.schema.json` defines the secret-free artifact emitted by the
embedded rulepack builder. `capability-registry.schema.json` defines the single
visible `1c-airules` preset. `1c-airules.json` is the checked-in registry value.

The contracts deliberately contain only logical MCP roles. Commands, URLs,
headers, environment-variable bindings and credentials belong to machine or
project configuration and must never be embedded in a rulepack.

Overlay resolution is stable-ID based, in this order:

1. embedded rulepack;
2. recipient profile;
3. project overlay;
4. machine-local override.

Later layers replace an item with the same stable ID. They do not append a
second copy.
