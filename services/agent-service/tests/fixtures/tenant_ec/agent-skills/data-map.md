---
name: data-map
description: Which numeric/data questions your tools CAN answer, which have NO tool yet (be honest, point to the app's reports), and where each number must come from
triggers: iva iva0 iva12 iva15 impuesto impuestos tasa tasas retencion retenciones base imponible inventario inventarios stock existencias kardex bodega bodegas saldo saldos cuenta cuentas contable libro mayor vendimos vendi venta ventas facturas total totales cobrar deben nos deben debemos debo deuda deudas pendiente pendientes proveedor proveedores cuanto clientes nomina sueldos rol margen costo costos 104 ats sri formulario efectivo bancos caja compra compras pedido pedidos cambia cambiar elimina eliminar borra borrar anula anular contabiliza contabilizar crea crear modifica modificar
---
# Data map — what you can answer, and from where

## You CAN answer today (with your tools)

- Find/list/rank documents (Orden de compra, Compra, Comprobante recibido, Pedido de cliente,
  **Factura de venta, Recibo de caja**) by counterparty, by what was bought
  (item_description), by period, by amount → **find_documents**. Its `sum_total`/`sum_shown`
  are database-computed exact sums — use them for totals over those documents.
- PURCHASE totals and counts — "¿cuánto suman las compras de mayo?", "¿cuánto compramos
  este año?", "¿cuántas facturas de compra tenemos en total?" — are answerable RIGHT NOW:
  call **find_documents** (document_type=Compra, dates only if the user bounded the period)
  and answer with `sum_total` / `total`. "Facturas de compra", "facturas de proveedores" =
  the Compra document. Never refuse these, and never ask permission first — read-only
  searches are free; just run them. (The CANNOT list below is about SALES, not purchases.)
- CUSTOMER ORDERS are searchable too: "pedidos de clientes", "pedidos de venta", "¿cuántos
  pedidos…?", "¿cuánto suman los pedidos…?" → **find_documents** document_type=PedidoDeCliente
  (counts, sums, periods, by client). A *pedido* is NOT a sales invoice — only Facturas de
  venta are out of reach, never refuse pedidos.
- RECEIVED VOUCHERS are searchable too: "comprobantes recibidos", "retenciones recibidas"
  (the withholding vouchers clients hand you) → **find_documents**
  document_type=ComprobanteRecibido (counts, periods, by client). The tax CANNOT below is
  about rates/bases/Formulario 104/ATS — never about counting or listing these documents.
- Which purchases are unpaid / how much we owe one supplier, invoice by invoice →
  **find_unpaid_purchases** (register "Pagos", the canonical settlements source).
  ROUTING RULE: "¿cuánto le debemos a [nombre]?" with a supplier named → ALWAYS
  find_unpaid_purchases(counterparty=nombre), NEVER financial_snapshot — the snapshot is the
  GLOBAL total of every supplier and would misstate one supplier's debt.
- Which SALES are uncollected / how much one CLIENT owes us, invoice by invoice →
  **find_unpaid_sales** (same register, sales side). Same routing rule: a named client →
  find_unpaid_sales(counterparty=nombre); the global receivable → financial_snapshot
  `accounts_receivable`. Always present "nos deben clientes" (AR) and "debemos a
  proveedores" (AP) as SEPARATE figures, never mixed.
- SALES totals of a period ("¿cuánto vendimos en mayo?", "mejor cliente", "¿qué producto se
  vende más?", margen) → **sales_summary** (register Ventas — the canonical source; never sum
  invoices yourself). PURCHASE totals by supplier/item → **purchases_summary** (register
  Compras). Both return the top contributing documents as links — use them for "¿de dónde
  sale esa cifra?".
- Available cash right now (cajas + bancos) → **financial_snapshot** metric `cash`
  (the "Disponible" figure). The BOOK balance → metric `cash_book`; the difference (uncashed
  checks / transfers in transit) → metric `cash_gap` — use it when the user asks why the bank
  "no cuadra".
- Total owed to suppliers for purchases → **financial_snapshot** metric `accounts_payable`;
  total clients owe us → metric `accounts_receivable`; inventory valued at COST → metric
  `inventory_value` (retail/PVP valuation is the Avaluo de bodega report — say so if asked).
- PERIOD COMPLIANCE REVIEW — "revisa junio", "¿qué falta antes de declarar?", "¿tengo compras
  sin retención?", "¿hay documentos sin contabilizar?", "¿stock negativo?", "¿huecos en la
  numeración de facturas?", "¿contrapartes duplicadas?", "¿pagos en exceso / facturas
  vencidas?", "¿por qué el saldo contable de caja/banco no cuadra con lo disponible?" →
  **compliance_review** (all checks for a full sweep, or `checks=[...]` for one worry). See the
  auditoria playbook: you REPORT findings, you never fix them.
- The PERIOD's IVA picture — "¿cuánto IVA llevo en junio?", "dame el resumen para el 104" →
  **compliance_review** `checks=["resumen_iva"]`: bases + IVA by rate for compras and ventas,
  plus the computed difference. Present it as a PREVIEW — the filing itself is the Formulario
  104 report in the app.
- Any derived arithmetic (differences, percentages, VAT amounts from a base you have) →
  **calculate**.

## You CANNOT answer yet (no tool — follow the honesty protocol below)

- Tax/IVA questions AT DOCUMENT LEVEL: "¿qué compras tienen IVA 0/12/15?", per-document rate
  filters, withholding AMOUNTS as a tax figure ("¿cuánto nos retuvieron de IVA?"), the
  filing-grade Formulario 104 and the ATS annex. Point the user to the SRI / IVA reports.
  THREE EXCEPTIONS, never refuse them: (1) counting/listing the DOCUMENTS "retenciones
  recibidas" / "comprobantes recibidos" → find_documents document_type=ComprobanteRecibido
  (see CAN list); (2) computing IVA or a base from an amount the user GIVES you → plain
  arithmetic for **calculate** ("factura de 287.96 con IVA incluido, ¿la base?" →
  287.96 / 1.15); (3) the PERIOD's IVA totals by rate → compliance_review
  checks=["resumen_iva"] (see CAN list).
- PER-ITEM stock quantity: "¿cuánto stock hay de la varilla X?" (register Inventarios by
  item/warehouse; reports in Bodegas). You CAN give the negative-stock alerts
  (compliance_review stock_negativo) and the company-wide value at cost
  (financial_snapshot inventory_value) — but not one item's quantity yet.
- Ledger balances: "saldo de la cuenta 1.1.01" (register Contable; reports in Contabilidad).
- Payroll: "¿cuánto pagamos de sueldos?" (register Rol; Personal section).

## Honesty protocol when no tool fits

0. FIRST verify that really no tool fits. NEVER refuse arithmetic — **calculate** covers ALL
   of it ("¿cuánto es el 5% de 1234.56?" → calculate, not "I can't"), INCLUDING IVA/base
   math on amounts the user provides. NEVER refuse purchase document searches or totals —
   **find_documents** covers them — nor customer-order searches (PedidoDeCliente). The
   protocol below is for DATA you genuinely cannot look up, never for math.
1. Say plainly you cannot look that up yet ("Aún no puedo consultar X desde aquí").
2. Point to where the user can see it in the app (the report/section named above).
3. Offer the closest thing you CAN do, if any.

NEVER answer such a question by running a different search and reporting its empty result as
fact: "I found no Compras with IVA 0" is FALSE information when you never had a tax filter —
the books almost certainly contain them. An invented or proxy answer is worse than "I can't".

## You can READ and PREPARE drafts — but you never POST/SAVE yourself

Your data tools are read-only, with ONE exception: **draft_document** PREPARES a NEW document and
opens it for the user to review and post (currently only "Orden de compra"). Use it for "crea/
prepara una orden de compra a X de N unidades de Y" and as a workflow step. You FILL the draft; the
USER reviews, adjusts and posts (or discards) it — you never post or save anything yourself, and you
only learn the result from the {"status":"reviewed",...} the app returns. See the draft-and-review
playbook.

You still have NO tool for — so do NOT announce or promise — modifying / re-dating / posting /
cancelling / deleting an EXISTING document ("cambia la fecha", "elimina", "contabiliza esta",
"anula el cheque"), creating catalog items ("crea un proveedor"), or drafting any type other than
Orden de compra. When asked for one of these, do NOT ask "¿confirmas?" — you have nothing to
execute; say you cannot do it yet and give the manual path (open the document in its list, edit,
re-post).
