---
name: 1c-form-shot
description: "Capture an identified 1C form through an already supported browser, EDT, QA or desktop surface. Триггеры: снимок формы 1С, показать форму, скриншот формы."
---

# Capture the intended form

Resolve the object/form and the client/target the user wants to see. Use the
project's UI-testing policy to choose an available supported surface: browser,
EDT renderer, QA or desktop. Hidden desktop is eligible only for targets and
executors whose support has been established. A renderer image is not a live
client screenshot; label the distinction.

Observe the actual surface before opening or navigating to the form. Use the
surface's native capture, keep the intended form and useful surrounding context,
and preserve the resulting artifact path. Avoid unrelated windows, credentials
and private records. Opening a form or executing its handlers may have effects;
apply the same authorization and target rules as the chosen executor.

If no supported capture is available, report the missing capability and the
smallest manual capture needed. Do not install an alternate screenshot/OCR stack
as a side effect. A screenshot establishes appearance, not business correctness
or correspondence to the latest source revision.
