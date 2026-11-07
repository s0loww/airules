---
name: office-recalculate
description: "Recalculate workbook formulas with a local calculation engine and verify cached values. Триггеры: пересчитать Excel, обновить формулы, кэш формул."
---

# office-recalculate

Use an available local calculation engine and a fresh XLSX/ODS destination. Keep the original workbook. Compare formula strings and representative values before and after calculation. Reopen the output in data-only mode to confirm cached values were refreshed. Check expected totals and error cells rather than only engine exit status. Never describe a save by openpyxl as recalculation. State engine compatibility limits and preserve formulas unless explicitly asked to flatten values.
