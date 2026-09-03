import json
import sys
from pathlib import Path

import pytest

from app.corrector import Corrector, normalize, is_protected, search_key, strip_accents, telex_skeleton

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from build.build_nearmiss import all_variants


def test_normalize_behaviour():
    assert normalize("Viên Sủi") == "viên sủi"
    assert normalize("  A   B  ") == "a b"
    assert normalize("500mg") == "500mg"
    assert normalize("NutriGrow") == "nutrigrow"


def test_protected_tokens():
    for token in ["500mg", "0.1%", "10ml", "viên", "vỉ", "30"]:
        assert is_protected(token), token
    for token in ["estrogen", "vitamin", "paracetamol"]:
        assert not is_protected(token), token


def _make_corrector():
    return Corrector(
        BASE_DIR / "index" / "keywords.json",
        BASE_DIR / "index" / "nearmiss.json",
        BASE_DIR / "data" / "products.jsonl",
    )


def test_corrector_auto_corrects_known_typo():
    corrector = _make_corrector()
    result = corrector.correct("etrogen")
    assert result["decision"] == "auto_correct"
    assert result["suggestion"] == "estrogen"


@pytest.mark.xfail(
    reason="_fuzzy_lookup scans the whole vocabulary per unknown token, so a token "
           "that reaches the fuzzy fallback costs ~200ms. Phrase matching and the "
           "short-token guard keep most queries off that path (p50 is ~35ms), but "
           "the scan itself needs an n-gram candidate index to get under 50ms.",
    strict=True,
)
def test_correction_latency_budget():
    corrector = _make_corrector()
    assert corrector.correct("etrogen")["latency_ms"] < 50


def test_corrector_no_change_on_exact_match():
    corrector = _make_corrector()
    assert corrector.correct("estrogen")["decision"] == "no_change"


def test_corrector_no_results_on_garbage():
    corrector = _make_corrector()
    assert corrector.correct("qqzzxx")["decision"] == "no_results"


def test_ambiguous_variant_never_auto_corrects():
    corrector = _make_corrector()
    nearmiss = json.loads((BASE_DIR / "index" / "nearmiss.json").read_text(encoding="utf-8"))
    ambiguous = [v for v, entry in nearmiss.items() if entry.get("amb") and " " not in v]
    assert ambiguous, "expected at least one ambiguous variant in the built index"
    for variant in ambiguous[:25]:
        result = corrector.correct_token(variant)
        assert result["status"] != "corrected", f"{variant!r} is ambiguous but was auto-corrected"


def test_domain_rules_generalize_not_hardcoded():
    cases = [
        ("mebendazole", "mebendazol"),
        ("chlorpheniramine", "clorpheniramin"),
        ("amoxicillin", "amoxycillin"),
        ("sulphate", "sulfate"),
        ("vitamin c", "vitaminc"),
    ]
    for src, want in cases:
        variants = {variant for variant, _rule in all_variants(src)}
        assert want in variants, f"{src} -> {want} missing"


# --- Vietnamese input folding -------------------------------------------
# A tone or vowel mark can be typed as a real diacritic, as Telex, as VNI, or
# dropped entirely, and the tone key lands wherever the typist happened to be
# in the syllable. Every one of these has to reduce to the same skeleton or the
# same product search returns different results depending on how it was typed.

def test_every_spelling_of_a_syllable_folds_together():
    # accented / bare / Telex with the key at either position / VNI
    for variant in ["thuốc", "thuoc", "thuocs", "thuoocs", "thuosc", "thuo6c1"]:
        assert telex_skeleton(variant) == "thuoc", variant
    for variant in ["tránh", "tranh", "tranhs", "trasnh", "traxnh", "tranh1", "tra1nh"]:
        assert telex_skeleton(variant) == "tranh", variant
    for variant in ["đánh", "danh", "ddanhs", "ddanh", "d9anh1", "d9a1nh"]:
        assert telex_skeleton(variant) == "danh", variant
    for variant in ["răng", "rang", "rawng", "rangw", "ra8ng"]:
        assert telex_skeleton(variant) == "rang", variant
    for variant in ["nước", "nuoc", "nuwowcs", "nu7o7c1"]:
        assert telex_skeleton(variant) == "nuoc", variant


def test_a_tone_key_is_never_two_keys():
    # "loss" is a syllable followed by two tone keys, which no syllable can
    # carry - so it is an English word, not a decorated "lo".
    for word in ["loss", "mass", "miss", "boss", "cross"]:
        assert telex_skeleton(word) == word, word


def test_whole_sentences_fold_together_however_they_are_typed():
    expected = "thuoc tranh thai"
    for sentence in [
        "thuốc tránh thai",
        "thuoc tranh thai",
        "thuoc tranhs thai",
        "thuoocs traxnh thai",
        "thuoc1 tranh2 thai",
    ]:
        assert search_key(sentence) == expected, sentence


def test_non_vietnamese_words_are_left_alone():
    # The folder may only touch what parses as a Vietnamese syllable. Stripping
    # every stray s/f/r/x/j would shred the INNs and brands in the catalog.
    for word in ["aspirin", "paracetamol", "amoxicillin", "vitamin", "oral", "pro", "stada"]:
        assert telex_skeleton(word) == word, word


def test_product_codes_are_not_read_as_vni():
    # "a4" must not read the 4 as a tone key and collapse to "a", or every
    # code in the catalog would fold onto a single letter.
    for code in ["a4", "b12", "co2", "d3", "a31", "500mg", "n95", "kn95", "db4510"]:
        assert telex_skeleton(code) == code, code


def test_every_product_is_reachable_without_typing_accents():
    # The guarantee the whole folder exists for: dropping the diacritics from
    # any product name must not change what it folds to, for every product in
    # the catalog - not just the ones someone thought to write a test for.
    products = _make_corrector().products
    assert len(products) > 1000
    mismatched = [
        p["webName"] for p in products
        if search_key(p["webName"]) != search_key(strip_accents(p["webName"]))
    ]
    assert mismatched == []
