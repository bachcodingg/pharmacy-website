import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import normalize, strip_accents

KEYWORDS_PATH = BASE_DIR / "index" / "keywords.json"
OUT_PATH = BASE_DIR / "index" / "nearmiss.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

QWERTY = {
    "q": "ws", "w": "qesad", "e": "wrsdf", "r": "etdfg", "t": "ryfgh", "y": "tughj", "u": "yihjk", "i": "uojkl", "o": "ipkl", "p": "ol",
    "a": "qwsz", "s": "awedx", "d": "serfcx", "f": "drtgvc", "g": "ftybhv", "h": "gyujnb", "j": "hukm", "k": "ijl", "l": "okp",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk"
}

WEIGHTS = {
    "delete": 0.85,
    "transpose": 0.90,
    "keyboard": 0.95,
    "phonetic": 0.85,
    "pharma-suffix": 0.80,
    "inn-hdrop": 0.80,
    "trailing-e": 0.75,
    "diacritics": 0.90,
    "spacing": 0.85,
}


def gen_deletes(w: str):
    return {(w[:i] + w[i + 1:], "delete") for i in range(len(w))}


def gen_transposes(w: str):
    out = set()
    for i in range(len(w) - 1):
        chars = list(w)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        out.add(("".join(chars), "transpose"))
    return out


def gen_keyboard(w: str):
    out = set()
    for i, ch in enumerate(w):
        if ch in QWERTY:
            for neigh in QWERTY[ch]:
                out.add((w[:i] + neigh + w[i + 1:], "keyboard"))
    return out



PHONETIC_PAIRS = [("ph", "f"), ("c", "k"), ("k", "q"), ("c", "q"), ("y", "i"), ("s", "x"), ("z", "d")]
PHARMA_SUFFIX_PAIRS = [("ae", "e"), ("oe", "e"), ("ine", "in"), ("ole", "ol")]
INN_HDROP_PREFIXES = ["ch", "th", "kh", "gh", "ph"]


def _substitute_at_each_occurrence(w: str, a: str, b: str, rule: str):
    """Swap one occurrence of `a` for `b` at a time (real typos rarely hit every
    occurrence of a letter in a word), plus the all-occurrences form for short
    words where that's the more natural single "spelling style" swap."""
    out = set()
    start = 0
    while True:
        idx = w.find(a, start)
        if idx == -1:
            break
        variant = w[:idx] + b + w[idx + len(a):]
        out.add((variant, rule))
        start = idx + 1
    if w.count(a) > 1:
        out.add((w.replace(a, b), rule))
    return out


def gen_phonetic(w: str):
    """Single-letter phonetic swaps are position-specific typos: substitute one
    occurrence at a time (a typo in 'amoxicillin' hits the 'oxi', not every i)."""
    out = set()
    for a, b in PHONETIC_PAIRS:
        if a in w:
            out |= _substitute_at_each_occurrence(w, a, b, "phonetic")
        if b in w:
            out |= _substitute_at_each_occurrence(w, b, a, "phonetic")
    return {(variant, rule) for variant, rule in out if variant != w}


def gen_pharma_suffix(w: str):
    """ae/oe/-ine/-ole spelling-convention swaps apply to the whole word at
    once — a word is spelled the British way or the simplified way, not a
    mix — so this is a single whole-word substitution, not per-occurrence."""
    out = set()
    for a, b in PHARMA_SUFFIX_PAIRS:
        if a in w:
            variant = w.replace(a, b)
            if variant != w:
                out.add((variant, "pharma-suffix"))
        if b in w:
            variant = w.replace(b, a)
            if variant != w:
                out.add((variant, "pharma-suffix"))
    return out


def gen_inn_hdrop(w: str):
    out = set()
    for prefix in INN_HDROP_PREFIXES:
        if w.startswith(prefix) and len(w) > len(prefix) + 1:
            out.add((prefix[0] + w[len(prefix):], "inn-hdrop"))
    return out


def gen_trailing_e(w: str):
    if w.endswith("e") and len(w) > 3:
        return {(w[:-1], "trailing-e")}
    return set()


def gen_diacritics(w: str):
    stripped = strip_accents(w)
    if stripped != w:
        return {(stripped, "diacritics")}
    return set()


def gen_spacing(w: str):
    out = set()
    if " " in w:
        out.add((w.replace(" ", ""), "spacing"))
        out.add((w.replace(" ", "-"), "spacing"))
    elif "-" in w:
        out.add((w.replace("-", ""), "spacing"))
        out.add((w.replace("-", " "), "spacing"))
    return out


def domain_variants(word: str):
    """Stage the consonant/phonetic rules, then suffix rules fed by that
    output, then diacritics/spacing over everything accumulated so far. Each
    generator runs exactly once per stage — re-running a stage on its own
    output would compound a single rule onto itself indefinitely."""
    tagged = {}

    stage_a_phonetic = gen_phonetic(word) | gen_inn_hdrop(word)
    for variant, rule in stage_a_phonetic:
        tagged.setdefault(variant, rule)
    stage_a_forms = {word} | {v for v, _ in stage_a_phonetic}

    stage_b_forms = set(stage_a_forms)
    for form in stage_a_forms:
        for variant, rule in gen_pharma_suffix(form) | gen_trailing_e(form):
            tagged.setdefault(variant, rule)
            stage_b_forms.add(variant)

    for form in stage_a_forms | stage_b_forms:
        for variant, rule in gen_diacritics(form) | gen_spacing(form):
            tagged.setdefault(variant, rule)

    tagged.pop(word, None)
    return {(variant, rule) for variant, rule in tagged.items()}


def all_variants(word: str):
    return set().union(
        gen_deletes(word),
        gen_transposes(word),
        gen_keyboard(word),
        domain_variants(word),
    )



RULE_GROUPS = ["delete", "transpose", "keyboard", "phonetic", "pharma-suffix", "inn-hdrop", "trailing-e", "diacritics", "spacing"]

# Rules the corrector now reproduces live, at query time: plain edit distance
# covers delete/transpose/keyboard, and the accent-stripped, telex-skeleton and
# compact vocabulary views cover diacritics and spacing. Baking them into the
# table too cost 47MB of index and 236k redundant entries loaded into memory on
# every boot. What stays is the part edit distance genuinely cannot derive -
# the domain spelling conventions ("chlorpheniramine" -> "clorpheniramin" is
# three edits, far outside any safe fuzzy radius) - plus pharmacist-approved
# learned pairs.
LIVE_REPRODUCIBLE_RULES = frozenset({"delete", "transpose", "keyboard", "diacritics", "spacing"})


def build_table(keywords: dict, excluded_rules=frozenset(), learned_pairs=()) -> dict:
    """Pure table-building logic, reusable by both the production build and
    eval/held_out.py (which builds a second table with some rule groups
    excluded, to measure whether the corrector generalizes beyond rules it
    was directly given).

    learned_pairs are pharmacist-approved (variant -> keyword) mappings mined
    from real query logs (see learning/). They go through the exact same
    ambiguity computation as every generated rule - an approved pair that
    collides with something else still won't auto-correct silently."""
    table = defaultdict(list)
    for keyword in keywords:
        word = normalize(keyword)
        if not word or len(word) <= 2:
            continue
        variant_pairs = gen_spacing(word) if " " in word else all_variants(word)
        for variant, rule in variant_pairs:
            if not variant or variant == word or rule in excluded_rules:
                continue
            if rule in LIVE_REPRODUCIBLE_RULES:
                continue
            table[variant].append({"keyword": keyword, "weight": WEIGHTS.get(rule, 0.6), "rule": rule})

    for pair in learned_pairs:
        variant = normalize(pair.get("from_query", ""))
        keyword = normalize(pair.get("to_query", ""))
        if not variant or not keyword or keyword not in keywords:
            continue
        table[variant].append({"keyword": keyword, "weight": 1.0, "rule": "learned"})

    out = {}
    for variant, items in table.items():
        if variant in keywords:
            continue
        # Rank before truncating. The generators above return *sets* of
        # (variant, rule) tuples, so the order items land in `table` follows
        # set iteration order over strings - which Python randomizes per
        # process via PYTHONHASHSEED. A plain items[:3] therefore kept three
        # arbitrary candidates that changed from one build to the next: the
        # shipped nearmiss.json was not reproducible, and eval/held_out.py
        # swung ~0.012 on top-1 accuracy between runs of identical code,
        # which is wide enough to swamp the effect of a real change.
        #
        # Sorting on a total order (weight, then keyword, then rule) fixes
        # both problems at once: the build is reproducible, and the three
        # candidates kept are the highest-weighted ones rather than whichever
        # three the hash seed happened to surface.
        ranked = sorted(items, key=lambda i: (-i["weight"], i["keyword"], i["rule"]))
        out[variant] = {"c": ranked[:3], "amb": len({item["keyword"] for item in items}) > 1}
    return out


def load_approved_pairs():
    from app import config

    path = config.APPROVED_PATH
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def build_nearmiss():
    with KEYWORDS_PATH.open("r", encoding="utf-8") as handle:
        keywords = json.load(handle)
    out = build_table(keywords, learned_pairs=load_approved_pairs())
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    return out


def demo(word: str):
    word = normalize(word)
    by_rule = defaultdict(set)
    for variant, rule in all_variants(word):
        by_rule[rule].add(variant)
    print(f"variants for {word!r}:")
    for rule in sorted(by_rule):
        variants = sorted(by_rule[rule])
        print(f"  [{rule}] ({len(variants)}) {variants[:15]}{' ...' if len(variants) > 15 else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", help="print variants for one word, grouped by rule, instead of building the table")
    args = parser.parse_args()

    if args.demo:
        demo(args.demo)
    else:
        out = build_nearmiss()
        print(f"wrote {OUT_PATH} ({len(out)} variants, {sum(1 for v in out.values() if v['amb'])} ambiguous)")
