---
name: v8unpack-cf
description: "Inspect or transform a 1C binary artifact using a confirmed codec, separating ordinary Form.bin from whole CF/CFE/EPF and source-only checks from platform acceptance. Триггеры: v8unpack, Form.bin, распаковать CF, бинарная форма."
---

# Work from a binary artifact

Identify the actual artifact and requested operation before choosing a tool.
One ordinary form `Ext/Form.bin` and a whole CF/CFE/EPF are different routes;
do not assume an ordinary-form codec can rebuild a configuration container.
For managed forms already available as XML, use the metadata workflow instead.

Discover the configured codec/CLI or project runner, its supported version and
operations. Use only its real schema and effects. An available extractor does
not imply a supported writer. A facade is optional; a local artifact route can
work without an ИБ. Missing tools remain an explicit prerequisite, not an
automatic package installation or an invented MCP call.

Read [references/artifact-workflow.md](references/artifact-workflow.md) before
extraction or a round trip. Preserve the original file and use a fresh bounded
workspace/output. Extraction writes artifacts even when it never touches an
ИБ, so use the applicable filesystem/process permissions.

When choosing between platform export and binary extraction, consult logical
rules `getconfigfiles` and `v8unpack-source-structure` through the project index.
Keep standard Designer/EDT exports distinct from an unpacker's layout. A binary
source is not proof of the current applied state of an available ИБ.

Deliver the output identity, supported route/version, changed logical payload,
checks actually performed and opaque or unsupported portions. Rebuilding a
binary does not prove the platform will accept it. Loading or executing it in
an ИБ is a separate authorized operation through the existing project runner
and target guards, not a side effect of inspection or round-trip verification.
