"""Build-time registration of the Codex reminder adapter; no trust changes."""


def render_config():
    handler = {
        "type": "command",
        "command": 'python3 -B "$(git rev-parse --show-toplevel)/.codex/hooks/codex-hook.py"',
        "commandWindows": 'powershell.exe -NoProfile -Command "& python -B ((git rev-parse --show-toplevel) + \'/.codex/hooks/codex-hook.py\')"',
        "timeout": 10,
    }
    return {"hooks": {
        "PreToolUse": [{"matcher": "^(?:apply_patch|Edit|Write)$", "hooks": [dict(handler)]}],
        "SessionStart": [{"matcher": "^(?:startup|resume|clear|compact|fork)$", "hooks": [dict(handler)]}],
    }}
