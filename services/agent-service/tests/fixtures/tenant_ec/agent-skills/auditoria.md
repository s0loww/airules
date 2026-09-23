---
name: auditoria
description: How to run the compliance review (revisa mi mes) — when to sweep vs run one check, how to present findings by severity, and what you must never claim. You report; the user fixes.
triggers: revisa revisar revision auditoria auditar audita cumplimiento control controles verifica verificar chequea chequear cierre declarar declaracion retencion retenciones pendiente pendientes sin contabilizar negativo huecos numeracion secuencia duplicada duplicadas duplicados vencida vencidas exceso brecha cuadra cuadrar descuadre 104 ats sri mes periodo
---
# Auditoría — the compliance review playbook

**compliance_review** runs deterministic checks over the books and returns findings with
severity. Every figure in a finding was computed by the database — quote them exactly, never
recompute. You REPORT problems and explain the manual fix; you never fix, post, create or
delete anything.

## When to call it

- Full sweep (omit `checks`): "revisa junio", "revisa el mes", "¿qué falta antes de declarar?",
  "¿está todo en orden?", month-end / cierre conversations.
- One worry (pass `checks=[...]`): the user names a specific problem —
  - "¿compras sin retención?" → `compras_sin_retencion`
  - "¿documentos sin contabilizar?" → `documentos_sin_contabilizar`
  - "¿stock negativo?" → `stock_negativo`
  - "¿cuánto IVA llevo? / resumen para el 104" → `resumen_iva`
  - "¿huecos en la numeración de facturas?" → `secuencia_facturas`
  - "¿contrapartes duplicadas?" → `contrapartes_duplicadas`
  - "¿pagos en exceso? / facturas vencidas" → `saldos_anomalos`
  - "el banco no cuadra con lo disponible" → `brecha_bancaria`
- Period: resolve "junio" etc. into `period_from`/`period_to` (YYYY-MM-DD) with the current
  date you were given. Balances (stock, deudas, cajas) are evaluated at `period_to` (never in
  the future). **If the user gives NO period and the month has just started (first ~7 days),
  review the PREVIOUS month — the one being closed — and say which period you reviewed**; deep
  in the month, the current month is the natural default.

## How to present the results

1. Lead with the verdict: how many findings, worst severity first ("Encontré 2 problemas de
   severidad alta y 1 aviso").
2. Go severity by severity — **alta** (fix before closing/declaring), **media** (review soon),
   **info** (context, not a problem: resumen_iva, brecha_bancaria). Quote each finding's
   `summary` figures exactly.
3. The app shows the affected documents as clickable links under your reply — do NOT enumerate
   every document; mention the count and point to the links. If a finding has `more`, say how
   many more there are.
4. For each alta/media finding give the ONE-line manual fix, e.g.:
   - compras sin retención → open each Compra and issue its Comprobante de retención
     (Generar → Comprobante de retenciones emitido; SRI expects it within 5 days).
   - documentos sin contabilizar → open the document and post it ("contabilizar"), or mark it
     for deletion if it should not exist.
   - stock negativo → check for missing Ingresos de bienes or wrong bodega on the outgoing
     document; register the missing receipt.
   - huecos de numeración → locate the missing invoices (voided? deleted? kept on paper?) —
     SRI asks for sequence continuity.
   - contrapartes duplicadas → merge the histories: repoint documents to ONE card and mark the
     other for deletion.
   - pagos en exceso → check for duplicated payments or a payment applied to the wrong invoice.
   - facturas vencidas → schedule the payments; the supplier balance is aging.
5. Close with the 1-2 highest-priority actions ("Antes de declarar: emita las 3 retenciones y
   contabilice los 2 documentos pendientes").
6. If `findings` is empty: say the period looks clean on the checks run (name them from
   `clean`) — do NOT invent problems, and do NOT claim MORE than the checks cover.

## Terminology and honesty (absolute)

- "contabilizar / sin contabilizar / se contabilizó" — NEVER "publicar / publicado".
- The resumen_iva difference is an ESTIMATE for orientation; the filing number comes from the
  Formulario 104 report in the app. Say so when you show it.
- If the user asks you to FIX a finding ("emite la retención", "contabilízalos"), you cannot —
  currently no tool creates retenciones or posts documents. Explain the manual path. (You CAN
  offer to draft an Orden de compra — that is the only draftable type today.)
- Never present a check the tool does not have (e.g. bank reconciliation against a statement,
  payroll checks) as run; if asked, say it is not covered yet.
