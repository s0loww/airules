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

# A routine with several callers, an object with several typed references, and
# names that exist in no configuration -- pick equivalents for your own corpus.
ROUTINE = os.environ.get("FACADE_SAMPLE_ROUTINE", "ОтправкаПочты")
ROUTINE2 = os.environ.get("FACADE_SAMPLE_ROUTINE2", "ОбработатьВходящиеПараметрыСервиса")
OBJECT = os.environ.get("FACADE_SAMPLE_OBJECT", "ДоговорыКонтрагентов")
ABSENT_ROUTINE = "НетТакогоМетодаВообще"
ABSENT_OBJECT = "НетТакогоОбъекта"

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
)


def main():
    if not CODE_URL or not GRAPH_URL:
        print("set FACADE_CODE_URL and FACADE_GRAPH_URL to the two MCP endpoints")
        return 2
    os.makedirs(OUT, exist_ok=True)
    clients = {"code": Client(CODE_URL), "graph": Client(GRAPH_URL)}
    failed = 0
    for name, backend, tool, args in CASES:
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
