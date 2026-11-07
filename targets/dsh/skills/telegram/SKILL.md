---
name: telegram
description: "Use this distribution's Telegram bridge controls for the selected DSH session. Триггеры: подключить Telegram к DSH, статус Telegram, отключить бота."
---

# Operate the configured Telegram bridge

This is a DSH adapter guide, not a new transport. The current bridge is configured
in Settings → Telegram. The user supplies their own BotFather token and numeric
owner ID there; the token is stored with Windows DPAPI CurrentUser and is not
returned to the model. Do not ask the user to paste tokens into a chat, copy another
installation's credentials or enable autostart as a side effect.

Use the actual local session controls when available:

- `/telegram status` — inspect bridge state;
- `/telegram connect` / `/telegram disconnect` — bind or release the selected session;
- `/telegram on` / `/telegram off` — start or stop the configured bridge;
- `/telegram help` — current command guidance.

Check the current session/workspace binding and the intended owner's private chat
before changing it. The host and DSH must stay running. Existing sessions keep
their preset and native permission policy; a Telegram approval applies to the
specific native call, not a permanent elevation.

Sending messages or attachments remains an external action requiring the user's
instruction. A request to inspect status is not permission to send a test message.
If controls are unavailable, point to the installed bridge settings and report
the missing integration; do not fabricate a Telegram tool or call the network.
