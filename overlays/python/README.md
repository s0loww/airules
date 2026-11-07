# Python layer

Canonical Python instructions for the portable DSH `python-airules` preset.
`rules/` contains lazily requested domain rules; `skills/` contains native
filesystem skills. The DSH builder copies these directories into the verified
distribution. Change policy here; `dsh_harness_overlay/src/domain-presets`
contains the native integration and a seed snapshot, not a separate policy fork.
Connections, credentials and local project parameters remain external.
