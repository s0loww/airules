#!/usr/bin/env python3
"""CI gate for airules composition declarations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

from composition import CompositionError, load_catalog, resolve_composition


REQUIRED_COMPOSITIONS = (
    ("claude", "public", "1c", "stable", "implemented"),
    ("dsh-deepseek", "s0lo", "1c", "experimental", "pending"),
    ("codex", "public", "1c", "experimental", "implemented"),
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="validate airules compositions")
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument(
        "--json",
        action="store_true",
        help="print resolved required compositions as JSON",
    )
    args = parser.parse_args(argv)

    resolved = []
    try:
        catalog = load_catalog(args.root, "1c")
        for target_id, profile_id, stack, status, renderer_status in REQUIRED_COMPOSITIONS:
            item = resolve_composition(catalog, target_id, profile_id, stack, "common")
            if item["target"]["status"] != status or item["target"]["renderer_status"] != renderer_status:
                raise CompositionError(
                    "target '{0}' expected {1}/{2}, got {3}/{4}".format(
                        target_id,
                        status,
                        renderer_status,
                        item["target"]["status"],
                        item["target"]["renderer_status"],
                    )
                )
            resolved.append(item)
        for test_name in ("test_composition.py", "test_dsh_renderer.py", "test_codex_target.py", "test_codex_hooks.py"):
            tests = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(test_name))],
                cwd=str(args.root or Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            if tests.returncode != 0:
                raise CompositionError(
                    "{0} failed: {1}".format(
                        test_name, (tests.stderr or tests.stdout).strip()
                    )
                )
    except CompositionError as exc:
        print("composition-check: FAIL: {0}".format(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resolved, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "composition-check: PASS: {0} layer(s), {1} profile(s), {2} target(s)".format(
                len(catalog.layers), len(catalog.profiles), len(catalog.targets)
            )
        )
        for item in resolved:
            print(
                "  {0}/{1}/{2} [{3}/{4}]".format(
                    item["target"]["id"], item["profile"]["id"], item["stack"],
                    item["target"]["status"], item["target"]["renderer_status"]
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
