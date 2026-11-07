# Common project layer

This is portable project-level content. It is installed after `core/` and the
selected stack overlay, but before a recipient profile and a concrete project
overlay.

Unlike `project-template/`, this directory contains shared operating policy:

- a neutral project-context contract;
- a reusable testing-contour contract;
- defaults for lazy rule loading and explicit MCP selection.

It must not contain machine paths, endpoints, credentials, database names or
facts from a concrete project. Those values are supplied by a profile-local or
project-local configuration at composition time.

Precedence is:

```text
core -> stack overlay -> common project layer -> recipient profile
     -> concrete project overlay -> target renderer
```

The target renderer may change file layout and syntax. It must not change the
meaning of this layer.
