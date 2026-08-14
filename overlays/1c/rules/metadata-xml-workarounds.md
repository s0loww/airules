---
description: Common XML generation pitfalls for 1C metadata and managed forms (`TabularSection` `LineNumber`, `PagesGroupExtInfo` typo, `Page.enabled`, UID uniqueness, ScheduledJob method binding, post-edit validation). Load when authoring or fixing metadata XML or `Form.xml` by hand.
alwaysApply: false
kind: invariant
---

# Common XML Generation Pitfalls (Metadata and Forms)

Concrete recurring mistakes when generating or editing 1C metadata XML / MDO and managed-form XML by hand or with scripts. Apply when authoring metadata XML directly (rather than via the `1c-metadata-manage` skill).

> Strong preference: use the `1c-metadata-manage` skill or the `1c-metadata-manager` subagent to mutate metadata XML. The cases below are for reviewing or fixing existing files.

---

## 1. TabularSections — no `LineNumber` standard attribute

Tabular sections (`табличные части`) **must not** contain a `<standardAttributes>` block with `LineNumber`. The platform adds it automatically; an explicit copy will cause a load error or duplication.

```xml
<!-- WRONG — remove this block from <tabularSections> -->
<standardAttributes>
  <dataHistory>Use</dataHistory>
  <name>LineNumber</name>
  <fillValue xsi:type="core:UndefinedValue"/>
  <fullTextSearch>Use</fullTextSearch>
  <minValue xsi:type="core:UndefinedValue"/>
  <maxValue xsi:type="core:UndefinedValue"/>
</standardAttributes>
```

The same rule applies to MDO (EDT format) `*.mdo` files — do not add a `LineNumber` standardAttribute to tabular sections; the EDT toolchain provides it implicitly.

---

## 2. `Pages` group — correct extInfo type name

The extInfo type is `PagesGroupExtInfo` (with letter "**s**"), not `PageGroupExtInfo`:

```xml
<!-- CORRECT -->
<type>Pages</type>
<extInfo xsi:type="form:PagesGroupExtInfo">
  <pagesRepresentation>Auto</pagesRepresentation>
  <currentRowUse>Auto</currentRowUse>
</extInfo>
```

A misspelled `PageGroupExtInfo` will silently break the form — the page group will not load in Designer / EDT.

---

## 3. `Page` element — must include `<enabled>true</enabled>`

For each `Page` element inside a `Pages` group, the `<enabled>` flag is required. Without it, Designer treats the page as disabled (or the form fails validation).

```xml
<type>Page</type>
<enabled>true</enabled>
```

---

## 4. UID / UUID — must be globally unique

All UIDs and UUIDs of new metadata objects, attributes, tabular sections must be **globally unique** across the configuration.

- Generate each UUID separately via `[guid]::NewGuid()` (PowerShell) or `uuid.uuid4()` (Python).
- Never reuse a UUID by copy-paste.
- Never use placeholder / sequential UUIDs (`a1b2c3d4...`, `b2c3d4e5...`).
- After bulk metadata generation, run a duplicate-UUID check across the source tree.

When adding metadata objects — also update `Configuration.xml` (`<childObjects>` ordering matters).

---

## 5. ScheduledJob `MethodName` — fully-qualified with `CommonModule.` prefix

A `ScheduledJob`'s `<MethodName>` must be the **fully-qualified** handler reference including the metadata-class prefix, not just `Module.Method`:

```xml
<!-- WRONG — load fails: "Ссылка на неизвестный метод" / "Имя метода должно быть задано" -->
<MethodName>МойОбщийМодуль.МойОбработчик</MethodName>

<!-- CORRECT -->
<MethodName>CommonModule.МойОбщийМодуль.МойОбработчик</MethodName>
```

The handler must be an exported procedure of a non-global **server** common module (`<Server>true</Server>`). Match the serialization of the existing base-config jobs (the same `CommonModule.<Module>.<Method>` shape). Without the prefix, load-from-files fails the job's method-binding validation even though the procedure exists.

---

## 6. Role `Rights.xml` — no rights on enums

Enums are readable by everyone without restriction, so an explicit rights block
for `Enum.<Name>` in a role is redundant. Types that never appear in
`Rights.xml` at all: `Enum`, `FunctionalOption`, `DefinedType`, `CommonModule`,
`CommonPicture`, `CommonTemplate` (the `1c-metadata-manage` skill, `role-manage`
doc, lists them with the full rights vocabulary).

```xml
<!-- WRONG — belongs in no role, neither in an extension nor in the base config -->
<object>
    <name>Enum.СтатусыОбработки</name>
    <right><name>Read</name><value>true</value></right>
    <right><name>View</name><value>true</value></right>
</object>
```

> **Suspect first when an extension load hangs.** External practice reports
> `DESIGNER /LoadConfigFromFiles -Extension` on platform 8.3.27 hanging for
> 60+ seconds with an empty `/Out` and no error when a role's `Rights.xml`
> contains a rights block on a **new** enum; EDT is reported to generate such a
> block on export. **Not reproduced on our contour** — treat it as the first
> hypothesis for a silent load hang, not as an established fact. Reviewing
> `Rights.xml` for `Enum.*` blocks is worth doing regardless: the block is
> redundant either way.
>
Rights in a role file are the static half of access control. The runtime half —
access-group profiles, assigning them to users, checking a right or a role from
code — is `access-rights-bsp.md`, and it has its own silent-failure mode
(a profile that saves with its roles quietly dropped).

> The same source reports the same hang shape when a **new metadata object and
> a role granting rights on it** arrive in one export, with a two-pass load
> (object first, rights second) as the workaround. Equally unverified here —
> worth trying when a load hangs, not worth splitting every export in two.

---

## 7. Validation hook

Whenever editing metadata XML by hand, after the change run:

- Validation from the `1c-metadata-manage` skill or project metadata validation scripts (`1c-meta-validate`, form validation, compile/load smoke where available).
- A dedicated XML schema validator only if the current session actually exposes one — validate against the appropriate XSD (fetch the schema for the target metadata type first if unsure).
- A duplicate-UUID scan across the source tree after bulk generation.

This catches structural issues (missing required elements, wrong type names, broken references) before they reach the platform.
