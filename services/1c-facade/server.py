"""MCP server publishing the six verbs.

Deliberately written against `http.server` and `json` rather than a framework:
the distribution installs into environments we do not control, and a tool whose
first requirement is a dependency tree is a tool that does not get switched on.
The protocol surface actually needed is small -- initialize, tools/list,
tools/call, ping.

The point of the whole component is on display in TOOLS below: six schemas,
roughly 3 KB, replacing some 31 KB across five servers. What disappears is not
just tokens but the choice itself -- which backend answers which question is
decided here, in code, from measurements.

    FACADE_REGISTRY=... python server.py --port 8770
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

import registry as registry_mod                    # noqa: E402
from health import Health                          # noqa: E402
from mcp_client import Client                      # noqa: E402
from verbs import Facade                           # noqa: E402

PROTOCOL = "2025-03-26"
NAME = "1c-facade"
VERSION = "0.2.0"

_PROJECT = {"type": "string",
            "description": "Проект из реестра; опущен — проект по умолчанию."}

TOOLS = [
    {
        "name": "find",
        "description": (
            "Найти в конфигурации: процедуру по имени (kind=routine), объект "
            "метаданных (kind=metadata), форму по элементам и заголовкам "
            "(kind=form) или код по описанию (kind=text). По описанию "
            "опрашиваются оба индекса и выдачи объединяются — поодиночке "
            "каждый неполон."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": _PROJECT,
                "kind": {"type": "string",
                         "enum": ["any", "routine", "metadata", "form", "text"],
                         "default": "any"},
                "exact": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "describe",
        "description": (
            "Досье объекта метаданных: структура, реквизиты с типами, формы, "
            "зависимости в обе стороны. id вида Справочники.X.Форма.Y — "
            "раскладка формы (элементы, реквизиты, команды, обработчики) и "
            "структура её модуля; путь .../Module.bsl или имя общего модуля — "
            "процедуры модуля с строками и директивами. sections: modules, "
            "form — добавить модули объекта или раскладку его формы."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string",
                       "description": "Справочники.Контрагенты, "
                                      "Справочники.Контрагенты.Форма.ФормаЭлемента "
                                      "или путь модуля."},
                "project": _PROJECT,
                "sections": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id"],
        },
    },
    {
        "name": "calls",
        "description": (
            "Граф вызовов процедуры: кто вызывает (callers) или что вызывает "
            "она (callees). Имя канонизируется до обращения к индексу, поэтому "
            "одноимённые процедуры разных модулей не смешиваются. Без "
            "графового индекса отвечает code-индекс — это помечено в coverage."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string",
                       "description": "Имя процедуры, можно квалифицированное."},
                "project": _PROJECT,
                "direction": {"type": "string", "enum": ["callers", "callees"],
                              "default": "callers"},
                "depth": {"type": "integer", "default": 1},
            },
            "required": ["id"],
        },
    },
    {
        "name": "usages",
        "description": (
            "Использования объекта метаданных: в метаданных (реквизиты с этим "
            "типом и ссылки объект→объект) и/или в коде. Использования в коде "
            "не покрыты ни одним индексом и берутся с диска — это помечено в "
            "coverage."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "project": _PROJECT,
                "where": {"type": "string", "enum": ["metadata", "code", "both"],
                          "default": "both"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "check",
        "description": "Проверить изменения правилами проекта.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "scope": {"type": "string", "enum": ["staged", "path", "diff"],
                          "default": "staged"},
            },
        },
    },
    {
        "name": "docs",
        "description": (
            "Документация платформы 1С и база знаний ИТС. Имя вида "
            "ТаблицаЗначений.Найти ищется точно, описание — поиском; scope=its — "
            "методические статьи ИТС, any — оба источника сразу. version — "
            "документация конкретной версии платформы."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string", "enum": ["platform", "its", "any"],
                          "default": "platform"},
                "version": {"type": "string",
                            "description": "Версия документации, например v8.3.27."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lint",
        "description": (
            "Проверить код BSL: mode=syntax — быстрый анализатор (диагностики со "
            "строками), check — корректность и производительность, review — стиль "
            "и стандарты (check и review работают через модель, десятки секунд). "
            "Код передаётся строкой или путём модуля в выгрузке проекта."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "path": {"type": "string",
                         "description": "Путь модуля относительно выгрузки проекта."},
                "project": _PROJECT,
                "mode": {"type": "string", "enum": ["syntax", "check", "review"],
                         "default": "syntax"},
            },
        },
    },
    {
        "name": "template",
        "description": "Шаблоны кода 1С: поиск по описанию задачи или один шаблон по id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "status",
        "description": (
            "Состояние парка: отвечает ли бэкенд, поднят ли контейнер, возраст "
            "индекса, строится ли он прямо сейчас. Отличает «объекта нет» от "
            "«сервер выключен». reindex=true пересобирает индекс проекта и "
            "запускает переиндексацию code-бэкенда — нужно после замены "
            "выгрузки-снимка на диске."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "reindex": {"type": "boolean", "default": False,
                            "description": "Пересобрать индекс проекта."},
            },
        },
    },
]


class Dispatcher(object):
    """JSON-RPC over the facade. Errors come back as data, never as a stack."""

    def __init__(self, facade):
        # No lock here: it used to serialise every call, so a slow graph walk
        # held up a 0.1 s lookup behind it. What is shared -- resolvers, client
        # sessions, container starts -- is guarded where it lives.
        self.facade = facade

    def handle(self, message):
        method = message.get("method")
        message_id = message.get("id")
        if message_id is None:
            return None                       # notification: nothing to answer
        if method == "initialize":
            return self._ok(message_id, {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": NAME, "version": VERSION}})
        if method == "ping":
            return self._ok(message_id, {})
        if method == "tools/list":
            return self._ok(message_id, {"tools": TOOLS + self._exposed()})
        if method == "tools/call":
            return self._call(message_id, message.get("params") or {})
        return self._error(message_id, -32601, "method not found: %s" % method)

    def _exposed(self):
        try:
            return self.facade.exposed_tools()
        except Exception:                     # noqa: BLE001 - never break the listing
            return []

    def _call(self, message_id, params):
        name = params.get("name")
        arguments = dict(params.get("arguments") or {})
        if name not in {tool["name"] for tool in TOOLS}:
            return self._pass_through(message_id, name, arguments)
        verb = getattr(self.facade, name, None)
        if verb is None:
            return self._error(message_id, -32602, "unknown tool: %s" % name)
        try:
            envelope = verb(**arguments)
            payload = json.dumps(envelope.as_dict(), ensure_ascii=False)
            return self._ok(message_id, {"content": [{"type": "text", "text": payload}]})
        except KeyError as exc:               # unknown project -- caller's mistake
            return self._tool_error(message_id, str(exc))
        except TypeError as exc:              # bad arguments -- caller's mistake
            return self._tool_error(message_id, "bad arguments: %s" % exc)
        except Exception as exc:              # noqa: BLE001 - never kill the server
            return self._tool_error(message_id, "%s: %s" % (type(exc).__name__, exc))

    def _pass_through(self, message_id, name, arguments):
        """A published backend tool: the reply goes back verbatim, unnormalised --
        these tools have a single source, so there is nothing to merge."""
        try:
            text, notes = self.facade.call_exposed(name, arguments)
        except KeyError as exc:
            if "unknown tool" in str(exc):
                return self._error(message_id, -32602, "unknown tool: %s" % name)
            return self._tool_error(message_id, str(exc).strip("'\""))
        except Exception as exc:              # noqa: BLE001 - never kill the server
            return self._tool_error(message_id, "%s: %s" % (type(exc).__name__, exc))
        if text is None:
            return self._tool_error(message_id, "; ".join(notes) or "backend gave no answer")
        return self._ok(message_id, {"content": [{"type": "text", "text": text}]})

    @staticmethod
    def _ok(message_id, result):
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    @staticmethod
    def _error(message_id, code, text):
        return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": text}}

    def _tool_error(self, message_id, text):
        return self._ok(message_id, {"isError": True,
                                     "content": [{"type": "text", "text": text}]})


def make_handler(dispatcher, path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass                              # keep the console for real output

        def _send(self, code, payload=None):
            body = b"" if payload is None else json.dumps(
                payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_POST(self):                    # noqa: N802 - http.server contract
            if self.path.rstrip("/") != path.rstrip("/"):
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                message = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError:
                return self._send(400, {"jsonrpc": "2.0", "id": None,
                                        "error": {"code": -32700, "message": "parse error"}})
            reply = dispatcher.handle(message)
            if reply is None:
                return self._send(202)
            return self._send(200, reply)

        def do_GET(self):                     # noqa: N802 - http.server contract
            if self.path.rstrip("/") == path.rstrip("/") + "/health":
                return self._send(200, {"server": NAME, "version": VERSION})
            return self._send(404, {"error": "not found"})

    return Handler


def build_facade():
    reg = registry_mod.load()
    if not len(reg):
        print("реестр пуст: создайте facade-registry.json по registry.example.json "
              "или укажите путь в FACADE_REGISTRY", file=sys.stderr)
    return Facade(reg, Health(Client), Client)


def warm(facade):
    """Build every project's index in the background.

    The index is built lazily on first use, and over a bind mount that first use
    costs seconds while the caller waits. Doing it at boot moves the cost to
    where nobody is watching; `status` answers without an index, so the server is
    useful immediately either way. Failures are reported, not fatal: a project
    whose export is not mounted must not stop the rest from serving.
    """
    def run():
        for name in facade.registry.names():
            project = facade.registry.get(name)
            # Announce the start, not just the finish: a full ERP base is
            # 121 000 files, and over a bind mount that is minutes, not the
            # seconds it takes on the host. Silence there reads as a hang.
            print("индекс %s: строится из %s…" % (name, project.source))
            started = time.time()
            try:
                stats = facade.resolver(project).stats()
                print("индекс %s: %s за %.0f с" % (name, stats, time.time() - started))
            except Exception as exc:             # noqa: BLE001 - one bad project
                print("индекс %s не собран: %s: %s"
                      % (name, type(exc).__name__, exc), file=sys.stderr)
    thread = threading.Thread(target=run, name="facade-warm", daemon=True)
    thread.start()
    return thread


def main(argv=None):
    parser = argparse.ArgumentParser(description="MCP-фасад для 1С")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--path", default="/mcp")
    args = parser.parse_args(argv)

    facade = build_facade()
    warm(facade)
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(Dispatcher(facade), args.path))
    print("%s %s: http://%s:%d%s  (проектов в реестре: %d)"
          % (NAME, VERSION, args.host, args.port, args.path, len(facade.registry)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
