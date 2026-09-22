"""Capture raw backend responses into `fixtures.local/`.

Run this against a live pair of servers whenever an image is updated and the
parser gate reports drift. Endpoints come from the environment so no machine
address is baked into the distribution:

    FACADE_CODE_URL   code_metadata  MCP endpoint
    FACADE_GRAPH_URL  graph_metadata MCP endpoint

The cases below are deliberately a mix of populated, empty and not-found
answers: the parsers have to keep those three outcomes distinguishable, which
is exactly what the facade needs in order to tell "nothing found" from
"backend down".

Pipeline: capture.py -> anonymise.py -> test_parsers.py --update
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "norm"))

from mcp_client import Client                       # noqa: E402

OUT = os.path.join(HERE, "fixtures.local")
CODE_URL = os.environ.get("FACADE_CODE_URL")
GRAPH_URL = os.environ.get("FACADE_GRAPH_URL")
# Platform servers (optional): cases for a server whose URL is not set are skipped.
PLATFORM_URLS = {
    "docs": os.environ.get("FACADE_DOCS_URL"),
    "syntax": os.environ.get("FACADE_SYNTAX_URL"),
    "codecheck": os.environ.get("FACADE_CODECHECK_URL"),
    "templates": os.environ.get("FACADE_TEMPLATES_URL"),
}

# A routine with several callers, an object with several typed references, and
# names that exist in no configuration -- pick equivalents for your own corpus.
ROUTINE = os.environ.get("FACADE_SAMPLE_ROUTINE", "ОтправкаПочты")
ROUTINE2 = os.environ.get("FACADE_SAMPLE_ROUTINE2", "ОбработатьВходящиеПараметрыСервиса")
OBJECT = os.environ.get("FACADE_SAMPLE_OBJECT", "ДоговорыКонтрагентов")
ABSENT_ROUTINE = "НетТакогоМетодаВообще"
ABSENT_OBJECT = "НетТакогоОбъекта"
# A form of OBJECT, a module path as the code backend mounts it, and a phrase
# that should hit forms and code chunks alike.
FORM = os.environ.get("FACADE_SAMPLE_FORM", "ФормаЭлемента")
MODULE = os.environ.get(
    "FACADE_SAMPLE_MODULE",
    "/app/code/Documents/СчетФактураВыданный/Forms/ФормаСписка/Ext/Form/Module.bsl")
PHRASE = os.environ.get("FACADE_SAMPLE_PHRASE", "договор контрагента")

CASES = (
    ("graph_call_chain__callers", "graph", "trace_call_chain",
     {"routine_name": ROUTINE, "direction": "callers", "depth": 1}),
    ("graph_call_chain__callees", "graph", "trace_call_chain",
     {"routine_name": ROUTINE2, "direction": "callees", "depth": 1}),
    ("graph_call_chain__deep", "graph", "trace_call_chain",
     {"routine_name": ROUTINE, "direction": "callers", "depth": 2}),
    ("graph_call_chain__empty", "graph", "trace_call_chain",
     {"routine_name": ABSENT_ROUTINE, "direction": "callers", "depth": 1}),
    ("graph_usages__ok", "graph", "find_usages_of_object",
     {"object_name": OBJECT, "limit": 30}),
    ("graph_usages__empty", "graph", "find_usages_of_object",
     {"object_name": ABSENT_OBJECT, "limit": 10}),
    ("graph_search_code__ok", "graph", "search_code",
     {"query": "отправка почты", "top_k": 3}),
    ("graph_dossier__ok", "graph", "get_object_dossier", {"object_name": OBJECT}),
    ("code_call_hierarchy__ok", "code", "get_method_call_hierarchy",
     {"method_name": ROUTINE, "direction": "callers", "depth": 1}),
    ("code_search_function__ok", "code", "search_function",
     {"name": ROUTINE, "exact": True, "limit": 3}),
    ("code_metadata_details__ok", "code", "get_metadata_details", {"object_name": OBJECT}),
    ("code_dependencies__reverse", "code", "graph_dependencies",
     {"object_name": OBJECT, "direction": "reverse", "limit": 10}),
    # facade 0.2: forms, modules, metadata and code search parsed, not raw
    ("code_search_forms__ok", "code", "search_forms", {"query": PHRASE, "limit": 5}),
    ("code_search_forms__empty", "code", "search_forms",
     {"query": ABSENT_OBJECT + " " + ABSENT_ROUTINE, "limit": 0}),
    ("code_form_layout__ok", "code", "inspect_form_layout",
     {"object_name": "Справочники." + OBJECT, "form_name": FORM}),
    ("code_module_structure__ok", "code", "get_module_structure", {"module_path": MODULE}),
    ("code_module_structure__missing", "code", "get_module_structure",
     {"module_path": "/app/code/CommonModules/" + ABSENT_OBJECT + "/Ext/Module.bsl"}),
    ("code_metadatasearch__ok", "code", "metadatasearch", {"query": OBJECT, "limit": 5}),
    ("code_metadatasearch__names", "code", "metadatasearch",
     {"query": OBJECT, "limit": 5, "names_only": True}),
    ("code_metadatasearch__empty", "code", "metadatasearch",
     {"query": ABSENT_OBJECT, "limit": 5}),
    ("code_codesearch__ok", "code", "codesearch", {"query": PHRASE, "limit": 5}),
    # platform servers: public documentation, ITS titles, analyzer output
    ("platform_docsearch__ok", "docs", "docsearch", {"query": "найти строку в таблице значений"}),
    ("platform_docinfo__ok", "docs", "docinfo", {"name": "ТаблицаЗначений.Найти"}),
    ("platform_docinfo__missing", "docs", "docinfo", {"name": "НетТакогоМетодаВообще"}),
    ("platform_its__ok", "codecheck", "its_help", {"query": "управляемые блокировки"}),
    ("platform_syntax__issues", "syntax", "syntaxcheck",
     {"code": "Процедура Проверка()\n\tА = 1\nКонецПроцедуры"}),
    ("platform_templates__ok", "templates", "templatesearch",
     {"query": "запрос к регистру остатков"}),
    ("platform_template__one", "templates", "get_template", {"template_id": "1"}),
)


def main(argv=None):
    # `--only a,b` re-captures just those cases: a new parser should not force
    # re-baselining every old fixture against whatever the corpus holds today
    argv = sys.argv[1:] if argv is None else argv
    only = None
    if len(argv) == 2 and argv[0] == "--only":
        only = set(argv[1].split(","))
    if not CODE_URL or not GRAPH_URL:
        print("set FACADE_CODE_URL and FACADE_GRAPH_URL to the two MCP endpoints")
        return 2
    os.makedirs(OUT, exist_ok=True)
    clients = {"code": Client(CODE_URL), "graph": Client(GRAPH_URL)}
    for kind, url in PLATFORM_URLS.items():
        if url:
            clients[kind] = Client(url)
    failed = 0
    for name, backend, tool, args in CASES:
        if only is not None and name not in only:
            continue
        if backend not in clients:
            print("  %-30s skip  (FACADE_%s_URL not set)" % (name, backend.upper()))
            continue
        elapsed, status, text = clients[backend].call(tool, args)
        extension = "json" if name.startswith("code_") else "txt"
        with io.open(os.path.join(OUT, name + "." + extension),
                     "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("  %-30s %-5s %5.1fs %7d симв" % (name, status, elapsed, len(text)))
        if status in ("ERR", "FAIL"):
            failed += 1
    print()
    print("следующий шаг: python anonymise.py")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
