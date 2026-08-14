---
description: "Dirty fixture: a rule whose frontmatter never declares its genre."
alwaysApply: false
---

# Dirty fixture: rule without a genre

The frontmatter above carries a description but no `kind`, so the delivery
layer cannot tell whether this rule belongs on the path-matching hook or on
the lazy index. It silently falls out of both.
