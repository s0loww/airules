---
name: document-search
description: How to search documents well — interpreting "compras de X" (who vs what), the filters that DO NOT exist, honest zero-result answers, disambiguation etiquette
triggers: busca buscar muestrame muestra lista listar ordenes orden compras compra pedidos pedido comprobantes documentos proveedor proveedores articulo articulos servicio servicios ultimo ultima mayor menor mas grande pequena reciente
---
# Searching documents well

## Interpreting "compras de X"

X can be WHO (the counterparty) or WHAT was bought (the goods/service in the lines):
- Clearly a company/person name (S.A., Cía., a person, an RUC) → `counterparty`.
- Clearly goods or a service ("transporte", "cemento", "mantenimiento") → `item_description`.
- Genuinely ambiguous → ask ONE short question, or try `item_description` first and say which
  interpretation you used.

## The only filters that exist

document_type, counterparty / counterparty_code, item_description, date_from/date_to, sort,
limit. There is NO filter by tax rate (IVA), warehouse, payment method, posting state, user or
anything else. If the user asks for an unsupported filter, do NOT shoehorn the term into
another argument (never pass "IVA0" as item_description or counterparty) — say that filter
is not available yet and check the data-map playbook for where the user can see it.

## Zero results are about YOUR filter, not about the books

"total: 0" only proves nothing matched the exact filter you used. Reply by stating the filter
("No encontré Compras del proveedor X en mayo") and offer next steps: widen the period, check
the name, or open the full list (the app renders an "Abrir como lista" link with your
results). NEVER turn an empty search into an absolute claim like "no existen compras con …" —
especially when the term came from an unsupported filter.

## Other rules

- Ambiguous counterparty → the result brings candidates; ask the user which one (the app shows
  them as clickable options) and re-call with `counterparty_code` copied exactly.
- Totals over found documents: use `sum_total` (whole filter) / `sum_shown` (listed items);
  derived figures via the calculate tool. Never mental math.
- When exactly one document matches, the app opens it automatically — just describe it.
- The app renders the found documents as clickable links under your reply — answer the
  question; don't re-enumerate every document in detail.
