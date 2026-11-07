#!/usr/bin/env python3
"""Regression tests for composition inheritance and target safety."""

from __future__ import annotations

import unittest
from pathlib import Path

from composition import (
    Catalog,
    CompositionError,
    Declaration,
    _merge_profiles,
    _safe_repo_ref,
    _validate_profile_graph,
    load_catalog,
    resolve_composition,
)


ROOT = Path(__file__).resolve().parents[1]


class CompositionTests(unittest.TestCase):
    def test_required_capability_promotes_optional(self):
        catalog = load_catalog(ROOT)
        resolved = resolve_composition(catalog, "dsh-deepseek", "s0lo")
        capabilities = resolved["profile"]["capabilities"]
        self.assertIn("mcp-code-facade", capabilities["required"])
        self.assertNotIn("mcp-code-facade", capabilities["optional"])

    def test_logical_server_override_is_keyed_by_role(self):
        parent = {
            "capabilities": {"required": [], "optional": []},
            "mcp": {"logical_servers": [{
                "role": "memory", "selector": "old", "access": "read-only",
                "required": False,
            }]},
        }
        child = {
            "capabilities": {"required": [], "optional": []},
            "mcp": {"logical_servers": [{
                "role": "memory", "selector": "new", "access": "project-defined",
                "required": True,
            }]},
        }
        merged = _merge_profiles(parent, child)
        self.assertEqual(1, len(merged["mcp"]["logical_servers"]))
        self.assertEqual("new", merged["mcp"]["logical_servers"][0]["selector"])

    def test_profile_cycle_is_rejected(self):
        def declaration(identifier, parent):
            return Declaration("profile", ROOT / (identifier + ".json"), {
                "id": identifier, "extends": parent,
            })

        catalog = Catalog(
            root=ROOT,
            layers={},
            profiles={
                "alpha": declaration("alpha", "beta"),
                "beta": declaration("beta", "alpha"),
            },
            targets={},
        )
        with self.assertRaisesRegex(CompositionError, "inheritance cycle"):
            _validate_profile_graph(catalog)

    def test_repo_reference_cannot_escape(self):
        with self.assertRaisesRegex(CompositionError, "stay inside repository"):
            _safe_repo_ref(ROOT, "../outside", ROOT / "fixture.json", "layout", "1c")

    def test_dsh_target_is_explicitly_pending_and_safe_by_default(self):
        catalog = load_catalog(ROOT)
        target = resolve_composition(catalog, "dsh-deepseek", "s0lo")["target"]
        self.assertEqual("experimental", target["status"])
        self.assertEqual("pending", target["renderer_status"])
        self.assertEqual("off", target["environment"]["ONEC_FOREIGN_AGENT_RULES"])
        self.assertFalse(target["mcp"]["import_project_config"])


if __name__ == "__main__":
    unittest.main()
