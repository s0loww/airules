"""Golden master: the profile mechanism must not change a tenant's prompts.

`fixtures/ec_golden.json` was captured from the original single-product prompt module before
it was split into a generic template plus per-tenant profiles; `fixtures/tenant_ec/assistant-profile.md` is
that product's profile. Every assembled prompt, both classifiers and the localized strings
must match byte for byte — the tenant's QA sweep was calibrated on exactly this text, and a
drift of one line is a behaviour change nobody reviewed.
"""

import json
import os

import pytest

from app.kb import Chunk
from app.prompt import (
    DEFAULT_PROFILE,
    build_context_block,
    build_system_prompt,
    difficulty_classifier,
    load_profile,
    normalize_lang,
    topic_classifier,
)

HERE = os.path.dirname(__file__)
GOLDEN = json.load(open(os.path.join(HERE, "fixtures", "ec_golden.json"), encoding="utf-8"))
EC = load_profile(os.path.join(HERE, "fixtures", "tenant_ec", "assistant-profile.md"))


@pytest.mark.parametrize("key", sorted(GOLDEN["system"]))
def test_system_prompt_is_byte_identical(key):
    lang, mode, today = key.split("|")
    got = build_system_prompt(lang, with_tools=(mode == "tools"),
                              today="" if today == "-" else today, profile=EC)
    assert got == GOLDEN["system"][key]


def test_classifiers_are_byte_identical():
    assert topic_classifier(EC) == GOLDEN["classifiers"]["topic"]
    assert difficulty_classifier(EC) == GOLDEN["classifiers"]["difficulty"]


@pytest.mark.parametrize("key", ["no_context", "not_configured", "empty_query", "sources"])
def test_strings_are_kept(key):
    for lang, text in GOLDEN["strings"][key].items():
        assert EC.string(key, lang) == text


def test_context_block_label():
    hit = Chunk(topic_id="t", title="T", subsystem="", lang="es", text="x")
    for lang, text in GOLDEN["context_label"].items():
        assert build_context_block([hit], lang, EC) == text


def test_language_normalisation():
    for raw, want in GOLDEN["normalize"].items():
        assert normalize_lang(raw, EC) == want


def test_generic_profile_names_no_product():
    """Without a profile the prompt must not leak any one tenant's product or country."""
    text = build_system_prompt("ru", with_tools=True, profile=DEFAULT_PROFILE)
    for leak in ("Contabilidad", "Ecuador", "SRI", "Contabilizar"):
        assert leak not in text
    assert "Reply in Russian" in text


def test_unknown_section_is_refused(tmp_path):
    bad = tmp_path / "p.md"
    bad.write_text("<!-- section:nonsense -->\ntext\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(str(bad))
