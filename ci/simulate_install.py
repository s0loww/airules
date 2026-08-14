#!/usr/bin/env python3
"""Симуляция установки дистрибутива в чистую цель по процедуре ONBOARD.

Что закрывает. `check_layers.py` проверяет исходники дистрибутива, гейт
впрыска — поведение хука. Ни один не отвечает на вопрос, ради которого
дистрибутив существует: **собирается ли из него рабочая установка**. Процедура
ONBOARD исполняется агентом, и её расхождение с содержимым репозитория
обнаруживается только в целевом проекте — то есть у пользователя.

Так и вышло при первом прогоне: после снятия многоканальности правило
`subagents-model-routing` продолжало обещать резолв усилия через
`channels.<channel>.effort`, хотя карта стала плоской. Все гейты были зелёные:
файл на месте, ссылки целы, синтаксис верный.

    python ci/simulate_install.py            # собрать во временном каталоге
    python ci/simulate_install.py --keep DIR # собрать в DIR и не удалять

Что симулятор НЕ делает: он не подменяет агента. Всё, что требует суждения
(ответы интервью, классификация MCP, выбор оверлея), подставлено фиксированными
значениями — проверяется механическая исполнимость процедуры, а не качество
решений. Отсюда и граница: зелёный прогон означает «раскладка собирается и
проходит собственный лист §10», а не «установка хорошая».

Чистая стандартная библиотека, Python 3.8+.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.dirname(HERE)
STACK = "1c"

# Ответы интервью (§2). Фиксированные: симулятор проверяет процедуру, а не
# качество ответов.
ANSWERS = {
    "PROJECT_ID": "demo-target",
    "PROJECT_NAME": "Demo Target",
    "STACK": STACK,
    "SOURCE_OF_TRUTH": "src/",
    "PRIMARY_CODE_DIR": "src/",
    "MCP_ORDER": "memora, project-index",
    "DISABLED_MCP": "legacy-index",
    "PREFIX": "Демо_",
    "LANGUAGE_POLICY": "русский в ответах, английский в коде",
    "BACKUP_DIR": ".rules-backups/",
}

KIND_ORDER = ("invariant", "case", "recipe", "process", "router")


def read(path):
    return io.open(path, encoding="utf-8-sig").read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def dist(*parts):
    return os.path.join(DIST, *parts)


# --------------------------------------------------------------- сборка цели
def build(target, problems):
    """Исполнить ONBOARD §4–§8 механически. Возвращает сводку по составу."""
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    # Минимальная цель: код, по которому сработают маски хука.
    write(os.path.join(target, "src", "Documents", "Тест", "Ext", "ObjectModule.bsl"),
          "Процедура ОбработкаПроведения(Отказ, Режим)\nКонецПроцедуры\n")
    write(os.path.join(target, "src", "Configuration.xml"),
          '<?xml version="1.0"?>\n<MetaDataObject/>\n')

    # §4.1 rules/ — core + оверлей
    meta = {}
    for base in (dist("core", "rules"), dist("overlays", STACK, "rules")):
        for name in sorted(os.listdir(base)):
            if not name.endswith(".md"):
                continue
            text = read(os.path.join(base, name))
            write(os.path.join(target, "rules", name), text)
            kind = re.search(r"^kind:\s*(\S+)", text, re.M)
            desc = re.search(r"^description:\s*(.+)$", text, re.M)
            meta[name[:-3]] = (kind.group(1).strip("\"'") if kind else None,
                               desc.group(1).strip().strip('"') if desc else "")

    # §4.1 openspec/
    shutil.copytree(dist("project-template", "openspec"), os.path.join(target, "openspec"))

    # §5 библиотеки оверлея — путь нормативный
    tools_src = dist("overlays", STACK, "tools")
    if os.path.isdir(tools_src):
        for name in os.listdir(tools_src):
            src = os.path.join(tools_src, name)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(target, "tools", name), dirs_exist_ok=True)

    # §6 карта моделей
    tiers, efforts = parse_model_map(read(dist("core", "install", "model-map.yaml")))
    roles = parse_roles(read(dist("core", "agents", "ROLES.md")))
    for role in roles:
        tier = role["override"] if role["override"] in tiers else role["tier"]
        role["model"] = tiers.get(tier)
        role["effort_value"] = efforts.get(role["effort"])
        if not role["model"]:
            problems.append(("BLOCK", "model-map", "тир '{0}' роли {1} не резолвится".format(
                tier, role["role"])))
        if not role["effort_value"]:
            problems.append(("BLOCK", "model-map", "усилие '{0}' роли {1} не резолвится".format(
                role["effort"], role["role"])))

    # §4.1 AGENTS.md
    values = dict(ANSWERS,
                  RULE_INDEX=render_index(meta, problems),
                  AGENTS_TABLE=render_agents_table(roles, tiers),
                  DOMAIN_ROUTES=domain_routes(),
                  DOMAIN_TRIGGER="1С, метаданные",
                  DOMAIN_ROLE="metadata-manager")
    out = read(dist("core", "templates", "AGENTS.md"))
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    write(os.path.join(target, "AGENTS.md"), out)
    write(os.path.join(target, "CLAUDE.md"), "See @AGENTS.md\n")

    # §6 .claude/agents
    render_agents(target, roles, problems)

    # §6 skills / commands
    for sub in ("skills", "commands"):
        dst = os.path.join(target, ".claude", sub)
        os.makedirs(dst, exist_ok=True)
        for base in (dist("core", sub), dist("overlays", STACK, sub)):
            if not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                src = os.path.join(base, name)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(dst, name), dirs_exist_ok=True)
                else:
                    shutil.copy(src, dst)

    # §7 .mcp.json
    write(os.path.join(target, ".mcp.json"), json.dumps(
        {"mcpServers": {"memora": {"type": "http", "url": "http://memora.invalid/mcp"}}},
        ensure_ascii=False, indent=2) + "\n")

    # §5.1 хук
    install_hook(target, problems)

    # §8 манифест
    files = {}
    for root, dirs, names in os.walk(target):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, target).replace(os.sep, "/")
            if rel.startswith("src/"):
                continue
            import hashlib
            files[rel] = hashlib.sha256(io.open(path, "rb").read()).hexdigest()
    write(os.path.join(target, ".airules-manifest.json"), json.dumps({
        "version": read(dist("VERSION")).strip(),
        "installed_at": "1970-01-01T00:00:00Z",
        "files": files,
        "placeholders": ANSWERS,
    }, ensure_ascii=False, indent=2) + "\n")

    return {"rules": len(meta), "roles": len(roles), "files": len(files)}


def parse_model_map(text):
    tiers, efforts, section = {}, {}, None
    for line in text.splitlines():
        if re.match(r"^claude:", line):
            section = "claude"
            continue
        if section == "claude":
            m = re.match(r"^  (high|medium|low|fast|orchestrator):\s*(\S+)", line)
            if m:
                tiers[m.group(1)] = m.group(2)
            if re.match(r"^  effort:", line):
                section = "effort"
            continue
        if section == "effort":
            m = re.match(r"^    (\w+):\s*(\S+)", line)
            if m:
                efforts[m.group(1)] = m.group(2)
            elif line.strip() and not line.startswith("    "):
                section = None
    return tiers, efforts


def parse_roles(text):
    roles = []
    row = re.compile(r"^\| ([a-z][a-z-]+) \| (\w+)(\*?) \| (\w+) \| (\w+) \| (\S+) \| (.+?) \|$")
    for line in text.splitlines():
        m = row.match(line)
        if not m or m.group(1) == "role":
            continue
        roles.append(dict(role=m.group(1), tier=m.group(2), conditional=bool(m.group(3)),
                          effort=m.group(4), tools=m.group(5),
                          override=None if m.group(6) == "—" else m.group(6),
                          purpose=m.group(7)))
    return roles


def render_index(meta, problems):
    groups = {k: [] for k in KIND_ORDER}
    for name, (kind, desc) in sorted(meta.items()):
        if kind in groups:
            groups[kind].append((name, desc))
        else:
            problems.append(("HIGH", "rules/" + name,
                             "kind='{0}' вне словаря — строка индекса без группы".format(kind)))
    lines = []
    for kind in KIND_ORDER:
        if groups[kind]:
            lines.append("\n**{0}**\n".format(kind))
            lines += ["- `rules/{0}.md` — {1}".format(n, d.split(". ")[0][:150])
                      for n, d in groups[kind]]
    return "\n".join(lines)


def render_agents_table(roles, tiers):
    rows = ["| agent | model | effort | tools | purpose |", "| --- | --- | --- | --- | --- |"]
    for r in roles:
        rows.append("| {role} | {model} | {effort_value} | {tools} | {purpose} |".format(**r))
        if r["conditional"]:
            rows.append("| {0}-deep | {1} | xhigh | {2} | {3} (deep) |".format(
                r["role"], tiers.get("high"), r["tools"], r["purpose"]))
    return "\n".join(rows)


def domain_routes():
    lines = read(dist("overlays", STACK, "README.md")).splitlines()
    return "\n".join(l for l in lines if l.startswith("| ") and "`" in l)


def render_agents(target, roles, problems):
    layout = read(dist("core", "install", "layout.md"))
    disc = re.search(r"```\n(## Дисциплина исполнения.*?)```", layout, re.S)
    if not disc:
        problems.append(("BLOCK", "layout.md",
                         "блок «Дисциплина исполнения» не извлекается из процедуры 4"))
    profiles = dict(re.findall(r"## Profile: (.+?)\n\n```\n(.*?)```",
                               read(dist("core", "install", "model-profiles.md")), re.S))
    if "Claude common" not in profiles:
        problems.append(("BLOCK", "model-profiles.md", "нет блока «Claude common»"))
    for r in roles:
        body_path = dist("overlays", STACK, "agents", r["role"] + ".md")
        if not os.path.isfile(body_path):
            body_path = dist("core", "agents", "roles", r["role"] + ".md")
        if not os.path.isfile(body_path):
            problems.append(("BLOCK", "roles", "нет тела роли " + r["role"]))
            continue
        head = ("---\nname: {role}\ndescription: {purpose}\nmodel: {model}\n"
                "effort: {effort_value}\ntools: {tools}\n---\n\n").format(**r)
        body = read(body_path).split("---", 2)[-1].lstrip("\n")
        text = head + body + "\n\n" + (disc.group(1) if disc else "")
        text += "\n\n```\n" + profiles.get("Claude common", "") + "```\n"
        write(os.path.join(target, ".claude", "agents", r["role"] + ".md"), text)


def install_hook(target, problems):
    hooks = os.path.join(target, ".claude", "hooks")
    os.makedirs(hooks, exist_ok=True)
    shutil.copy(dist("core", "hooks", "rule-inject.py"), hooks)
    map_src = dist("overlays", STACK, "hooks", "rules-map.json")
    if os.path.isfile(map_src):
        shutil.copy(map_src, hooks)
    write(os.path.join(target, ".claude", "settings.json"), json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Edit|Write", "hooks": [{
            "type": "command", "command": "python",
            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/rule-inject.py"]}]}],
        "SessionStart": [{"matcher": "compact", "hooks": [{
            "type": "command", "command": "python",
            "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/rule-inject.py",
                     "--session-start"]}]}],
    }}, ensure_ascii=False, indent=2) + "\n")

    hook = os.path.join(hooks, "rule-inject.py")
    checks = ((["--check-map"], "--check-map"),
              (["--dry-run", "src/Documents/Тест/Ext/ObjectModule.bsl"], "--dry-run"))
    for args, label in checks:
        proc = subprocess.run([sys.executable, hook] + args, cwd=target,
                              capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            problems.append(("BLOCK", "hook",
                             "{0} в целевой раскладке не отработал".format(label)))


# ------------------------------------------------------- проверочный лист §10
def verify(target):
    """ONBOARD §10, исполненный по собранной цели. -> [(ok, имя, деталь)]"""
    out = []

    def check(name, ok, detail=""):
        out.append((bool(ok), name, detail))

    def files(base, exts=(".md", ".json", ".yaml", ".toml")):
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d != ".git"]
            for n in names:
                if os.path.splitext(n)[1] in exts:
                    yield os.path.join(root, n)

    leftovers = {}
    for path in files(target):
        rel = os.path.relpath(path, target).replace(os.sep, "/")
        # Скиллы и библиотеки несут свои плейсхолдеры: у скиллов — шаблонная
        # нотация, у библиотек — рантайм-параметры из env-файла, заполнять
        # которые на установке запрещено (§0: среди них креды).
        if "/skills/" in rel or rel.startswith(("openspec/", "tools/")):
            continue
        hits = sorted(set(re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", read(path))))
        if hits:
            leftovers[rel] = hits
    check("ноль незаполненных {{…}}", not leftovers,
          "; ".join("{0}: {1}".format(k, ",".join(v)) for k, v in list(leftovers.items())[:3]))

    agents_md = read(os.path.join(target, "AGENTS.md"))
    refs = set(re.findall(r"`rules/([A-Za-z0-9_-]+)\.md`", agents_md))
    missing = sorted(r for r in refs
                     if not os.path.isfile(os.path.join(target, "rules", r + ".md")))
    check("каждое правило из Rule Index существует", not missing, ", ".join(missing))

    claude = read(os.path.join(target, "CLAUDE.md")).strip()
    check("CLAUDE.md — ровно 'See @AGENTS.md'", claude == "See @AGENTS.md", repr(claude[:50]))
    check(".claude/rules/ не создан", not os.path.isdir(os.path.join(target, ".claude", "rules")))

    mcp = json.loads(read(os.path.join(target, ".mcp.json")))
    bad = [n for n, s in mcp.get("mcpServers", {}).items()
           if "url" in s and s.get("type") != "http"]
    check("remote MCP несут type: http", not bad, ", ".join(bad))

    adir = os.path.join(target, ".claude", "agents")
    defs = sorted(os.listdir(adir)) if os.path.isdir(adir) else []
    check("агенты отрендерены", defs, "каталог пуст")
    texts = {f: read(os.path.join(adir, f)) for f in defs}
    check("у каждого агента блок дисциплины",
          all("Дисциплина исполнения" in t for t in texts.values()),
          ", ".join(f for f, t in texts.items() if "Дисциплина исполнения" not in t)[:80])
    check("у каждого агента профиль модели",
          all("Model profile" in t for t in texts.values()),
          ", ".join(f for f, t in texts.items() if "Model profile" not in t)[:80])
    check("model и effort заполнены",
          all(re.search(r"^model:\s*\S+", t, re.M) and re.search(r"^effort:\s*\S+", t, re.M)
              for t in texts.values()))
    check("верхняя ступень (max) никому не проставлена",
          not [f for f, t in texts.items() if re.search(r"^effort:\s*max\s*$", t, re.M)])
    check("у ro-ролей нет пишущих инструментов",
          not [f for f, t in texts.items()
               if re.search(r"^tools:\s*ro\s*$", t, re.M)
               and re.search(r"\b(Write|Edit|Bash)\b", t.split("---")[1])])

    check("манифест записан и валиден",
          os.path.isfile(os.path.join(target, ".airules-manifest.json"))
          and bool(json.loads(read(os.path.join(target, ".airules-manifest.json"))).get("files")))

    dist_paths = {}
    for path in files(os.path.join(target, "rules")):
        hits = sorted(set(re.findall(r"(?:core|overlays)/[A-Za-z0-9_.\-]+/", read(path))))
        if hits:
            dist_paths[os.path.basename(path)] = hits[:2]
    check("в правилах нет дистрибутивных путей", not dist_paths,
          "; ".join("{0}: {1}".format(k, ",".join(v)) for k, v in list(dist_paths.items())[:3]))

    broken = {}
    for path in files(os.path.join(target, "rules")):
        for name in sorted(set(re.findall(r"`rules/([A-Za-z0-9_-]+)\.md", read(path)))):
            if not os.path.isfile(os.path.join(target, "rules", name + ".md")):
                broken.setdefault(os.path.basename(path), []).append(name)
    check("перекрёстные ссылки правил разрешаются", not broken,
          "; ".join("{0} -> {1}".format(k, ",".join(v)) for k, v in list(broken.items())[:3]))

    tool_refs = {}
    for path in files(os.path.join(target, "rules")):
        for ref in sorted(set(re.findall(r"`(tools/[A-Za-z0-9_./-]+)`", read(path)))):
            if not os.path.exists(os.path.join(target, ref.replace("/", os.sep))):
                tool_refs.setdefault(os.path.basename(path), []).append(ref)
    check("ссылки правил на библиотеки разрешаются", not tool_refs,
          "; ".join("{0} -> {1}".format(k, ",".join(v)) for k, v in list(tool_refs.items())[:3]))

    return out


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="airules install simulator")
    parser.add_argument("--keep", metavar="DIR",
                        help="собрать в DIR и не удалять (по умолчанию — временный каталог)")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.keep) if args.keep else tempfile.mkdtemp(prefix="airules-sim-")
    problems = []
    try:
        summary = build(target, problems)
        results = verify(target)
    finally:
        if not args.keep:
            shutil.rmtree(target, ignore_errors=True)

    print("разложено: {rules} правил, {roles} ролей, {files} файлов в манифесте".format(**summary))
    print("\n== ПРОВЕРОЧНЫЙ ЛИСТ §10 ==")
    for ok, name, detail in results:
        print(("  PASS  " if ok else "  FAIL  ") + name + (
            "  <- " + detail if detail and not ok else ""))
    failed = [r for r in results if not r[0]]
    if problems:
        print("\n== ПРОБЛЕМЫ СБОРКИ ==")
        for severity, where, text in problems:
            print("  {0}  {1}: {2}".format(severity, where, text))
    print("\nитого: {0}/{1}".format(len(results) - len(failed), len(results)))
    return 1 if (failed or problems) else 0


if __name__ == "__main__":
    sys.exit(main())
