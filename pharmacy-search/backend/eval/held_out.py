"""Held-out rule-group evaluation (Step 11 of the build guide).

The trap the guide warns about: testing against variants your own generator
produced always scores ~100% and tells you nothing, because the lookup is
tautological (you generate variant V from rule R -> you build the table with
rule R -> of course looking up V finds it).

The fix: hold out ~20% of the rule groups, build a *second* nearmiss table
that never saw those rules, then generate test cases using ONLY the held-out
rules and see whether the corrector - built without ever being told about
them - still recovers the right keyword through some other path (a
coincidental delete/keyboard/transpose match, or another domain rule that
happens to reach the same variant). That's a real measurement of whether the
overall approach generalizes, not just whether the code runs.
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import Corrector, normalize
from build.build_nearmiss import (
    RULE_GROUPS,
    build_table,
    gen_diacritics,
    gen_inn_hdrop,
    gen_pharma_suffix,
    gen_spacing,
    gen_trailing_e,
)

KEYWORDS_PATH = BASE_DIR / "index" / "keywords.json"

HELD_OUT_RULES = {"pharma-suffix", "inn-hdrop"}

HELD_OUT_GENERATORS = {
    "pharma-suffix": gen_pharma_suffix,
    "inn-hdrop": gen_inn_hdrop,
}


def generate_held_out_cases(keywords: dict):
    """(typo, expected_keyword, rule) triples produced ONLY by the held-out rules.

    Returned in a canonical sorted order, which the sampling below depends on.
    HELD_OUT_RULES is a set and every generator returns a set, so the order
    cases were appended in followed set iteration over strings - randomized per
    process by PYTHONHASHSEED. random.sample() with a fixed seed then picked
    the same *indices* out of a differently ordered list, i.e. a different 500
    test cases on every run. That is what made this harness swing ~0.012 on
    top-1 accuracy between runs of identical code, which is wide enough to hide
    the effect of a real change. Sorting pins the sample.
    """
    cases = []
    for keyword in keywords:
        word = normalize(keyword)
        if not word or len(word) <= 2 or " " in word:
            continue
        for rule_name in sorted(HELD_OUT_RULES):
            for variant, rule in sorted(HELD_OUT_GENERATORS[rule_name](word)):
                if variant and variant != word and variant not in keywords:
                    cases.append((variant, keyword, rule))
    return sorted(cases)


def run(sample_limit: int = 500) -> dict:
    keywords = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))

    held_out_table = build_table(keywords, excluded_rules=HELD_OUT_RULES)
    eval_nearmiss_path = BASE_DIR / "eval" / "_held_out_nearmiss.json"
    eval_nearmiss_path.write_text(json.dumps(held_out_table, ensure_ascii=False), encoding="utf-8")
    corrector = Corrector(KEYWORDS_PATH, eval_nearmiss_path)

    cases = generate_held_out_cases(keywords)
    if len(cases) > sample_limit:
        import random

        random.seed(0)
        cases = random.sample(cases, sample_limit)

    top1_hits = 0
    top3_hits = 0
    no_candidates = 0
    for variant, expected, _rule in cases:
        result = corrector.correct_token(variant)
        candidates = result.get("candidates", [])
        keywords_ranked = [c["keyword"] for c in candidates]
        if not keywords_ranked:
            no_candidates += 1
            continue
        if keywords_ranked[0] == expected:
            top1_hits += 1
        if expected in keywords_ranked[:3]:
            top3_hits += 1

    eval_nearmiss_path.unlink(missing_ok=True)

    total = len(cases)
    return {
        "held_out_rules": sorted(HELD_OUT_RULES),
        "total_cases": total,
        "top1_accuracy": round(top1_hits / total, 4) if total else None,
        "top3_recall": round(top3_hits / total, 4) if total else None,
        "no_candidates_rate": round(no_candidates / total, 4) if total else None,
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2))
