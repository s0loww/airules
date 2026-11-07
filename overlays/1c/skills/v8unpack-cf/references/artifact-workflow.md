# Extraction and round-trip evidence

## Select a supported route

For an ordinary form, confirm that the codec supports the actual form/container
variant and its structured payload. For whole CF/CFE/EPF, confirm the CLI/API's
artifact and writer support for the installed version. Use returned manifests
and documented fields instead of positional edits guessed from another form.
Version-specific observations are not universal guarantees or limitations.

## Preserve identities and opaque data

Record source hash, size, selected codec/version and output workspace. Keep
the source immutable. Extract into a new contained output; preserve the
manifest, unknown records, binary resources and ordering where the codec
requires it. Stop at an unsupported format or incomplete extraction rather
than constructing a plausible partial replacement. Apply the runner's path,
size and process limits to the untrusted input artifact.

Make only the requested payload changes. Retain untouched opaque data exactly.
If a layout/property is exposed only as an undocumented raw array, an element
name from another variant is not evidence of its meaning. Report the gap or
use a supported platform route.

## Establish a round trip

Write to a new artifact, then use an independently read result where supported
to compare the logical payload and intended changes. Check meaningful fields,
resource presence and unchanged opaque data, not merely the number of files.
An unchanged round trip and an intentional edit have different expected diffs.

Container SHA may change for reasons such as encoding or generated records;
that is neither proof of a defect nor proof of equivalence. Keep both hashes
as provenance and base the structural verdict on the supported comparison.
If the reader/writer cannot establish equivalence, mark the round trip
unverified and preserve the original.

Platform acceptance and business behavior require separate platform/project
tests against an authorized target. Do not deliver an unpacker-built current
configuration as a proven loadable substitute for a platform-written one.
