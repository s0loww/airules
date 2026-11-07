---
name: office-xlsx
description: "Create, edit and validate XLSX spreadsheets and formula results. Триггеры: xlsx, Excel, формулы, электронная таблица."
---

# office-xlsx

Use openpyxl or another confirmed host spreadsheet library. Inspect workbook sheets, dimensions, formulas and styles first. Keep formulas as formulas; never replace them with guessed values. Use number formats, frozen headers and sensible widths according to the request.

Save a fresh workbook, recalculate through the local Office engine, then reopen both formula and data-only views. Check expected numeric values, formula preservation and error cells. openpyxl does not calculate formulas; missing or stale cached values are not evidence of success. Render relevant sheets or bounded ranges and inspect for clipping. Report unsupported formulas or changes by the calculation engine.
