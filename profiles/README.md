# Recipient profiles

A profile selects portable defaults and logical capabilities for a recipient.
It does not contain target syntax or facts of a concrete project.

- `public` is the neutral package that can be handed to another user.
- `s0lo` extends `public` with the local operating topology: the 1C facade is
  the primary knowledge channel, while memory, project ONEMCP and QA are
  separate optional capabilities.

Endpoints, credentials, machine paths and concrete server names belong in
ignored `profiles.local/` or in a concrete project's own configuration.
