---
name: office-render
description: "Render local Office or PDF files into preview images and inspect layout. Триггеры: рендер документа, превью страниц, проверить оформление."
---

# office-render

Check local rendering capabilities first. Use a fresh project output directory and bounded page selection, starting with representative pages or slides. Open generated images for visual inspection; a converter exit code is not acceptance. Check clipping, overlap, pagination, missing glyphs, table widths and image resolution. Iterate on the source and render again after changes. Explain any pages not inspected. Do not silently download renderers or use cloud conversion.

Worksheet previews use an exact sheet name and optional A1 range, not printed page numbers. Select a representative range when the sheet is large; keep the renderer's image and tile limits. Document/slide page selection and worksheet geometry are different modes.
