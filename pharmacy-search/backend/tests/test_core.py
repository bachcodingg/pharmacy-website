import json
import sys
from pathlib import Path

from app.corrector import Corrector, normalize, is_protected

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
    assert result["latency_ms"] < 50


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
