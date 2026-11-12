"""Build-time registration of the Codex reminder adapter; no trust changes."""


def render_config(command_advisories=False, deploy_advisory=True):
    handler = {
        "type": "command",
        "command": 'python3 -B "$(git rev-parse --show-toplevel)/.codex/hooks/codex-hook.py"',
        "commandWindows": 'powershell.exe -NoProfile -Command "& python -B ((git rev-parse --show-toplevel) + \'/.codex/hooks/codex-hook.py\')"',
        "timeout": 10,
    }
    config = {"hooks": {
        "PreToolUse": [{"matcher": "^(?:apply_patch|Edit|Write)$", "hooks": [dict(handler)]}],
        "PreCompact": [{"matcher": "^(?:manual|auto)$", "hooks": [dict(handler)]}],
        "PostToolUse": [{"matcher": "^(?:Read|read|builtin:read|read_file)$", "hooks": [dict(handler)]}],
        "SessionStart": [{"matcher": "^(?:startup|resume|clear|compact|fork)$", "hooks": [dict(handler)]}],
    }}
    if command_advisories:
        def advisory(filename):
            return {
                "type": "command",
                "command": 'python3 -B "$(git rev-parse --show-toplevel)/.codex/hooks/' + filename + '"',
                "commandWindows": 'powershell.exe -NoProfile -Command "& python -B ((git rev-parse --show-toplevel) + \'/.codex/hooks/' + filename + '\')"',
                "timeout": 10,
            }
        for event in ("PreToolUse", "PostToolUse"):
            config["hooks"][event].append({"matcher": "^(?:Bash|PowerShell)$",
                "hooks": [advisory("command-advisory.py")]})
        if deploy_advisory:
            config["hooks"]["PreToolUse"].append({"matcher": "^(?:Bash|PowerShell)$",
                "hooks": [advisory("deploy-advisory.py")]})
    return config
