---
name: office-pptx
description: "Create or edit PPTX slide decks with visual checks. Триггеры: pptx, PowerPoint, слайды, презентация."
---

# office-pptx

Use python-pptx or another confirmed host presentation library. Define slide size, typography and layout before authoring. Inspect existing slides before edits and preserve requested themes and content. Keep text readable and avoid overlap or overflow. Save a fresh PPTX.

Render slides through the local Office engine. Inspect every affected slide, checking text bounds, images, contrast and consistent spacing. Re-render after visual corrections. Rendering availability is checked at runtime; never claim an unrendered deck passed visual review.
