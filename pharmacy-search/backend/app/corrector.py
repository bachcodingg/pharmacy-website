import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

PROTECTED_TOKENS = {"viên", "vỉ", "hộp", "ống", "gói", "vien", "vi", "goi", "ong", "hop"}
THRESHOLD = 0.75
MARGIN = 0.15

# Fuzzy-fallback tuning
MAX_EDIT_DIST = 3
LEN_BUCKET_SLACK = 2  # only compare tokens whose length differs by <= this
MIN_FUZZY_LEN = 4  # below this a token has no shape to match on - "c" is not a typo of "1"

# A fuzzy hit may only be applied *silently* when it is a single edit away. Two
# or more edits still get offered, never assumed: "panadol" -> "panactol" is a
# different drug, and in a pharmacy that has to be the user's call.
FUZZY_AUTO_MAX_DIST = 1.0

# Longest keyword phrase we try to match as a unit. build_lexicon.py emits
# n-grams up to 4 tokens, and two thirds of the vocabulary is multi-word, so
# phrases have to be looked up whole before falling back to single tokens.
MAX_PHRASE_LEN = 4

# ---------------------------------------------------------------------------
# QWERTY physical-adjacency map. Telex is typed on an ordinary Latin keyboard,
# so a fat-finger slip lands on a physically neighboring key far more often
# than on a random one — "thuoc" -> "thuov" (c/v are next to each other) is
# a much more likely accident than "thuoc" -> "thuoq". Substitutions between
# neighboring keys get a discounted edit cost so these typos are recognized
# with higher confidence than an equal-length but implausible substitution.
# ---------------------------------------------------------------------------
KEYBOARD_NEIGHBORS = {
    "q": "wa", "w": "qeas", "e": "wrds", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yihj", "i": "uojk", "o": "ipkl", "p": "ol",
    "a": "qwsz", "s": "awedxz", "d": "serfcx", "f": "drtgvc", "g": "ftyhbv",
    "h": "gyujnb", "j": "huikmn", "k": "jiolm", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
}
SUB_COST_ADJACENT = 0.5
SUB_COST_DEFAULT = 1.0


def is_keyboard_adjacent(a: str, b: str) -> bool:
    return b in KEYBOARD_NEIGHBORS.get(a, "") or a in KEYBOARD_NEIGHBORS.get(b, "")


def char_signature(s: str) -> int:
    """Bitmask of which distinct characters a string contains.

    Used to skip the edit-distance DP entirely for forms that cannot possibly
    be within the distance cap. Every distinct character present in one string
    and absent from the other needs at least one edit operation of its own,
    and the cheapest operation in this metric is a keyboard-adjacent
    substitution at SUB_COST_ADJACENT, so

        edit_distance(a, b) >= popcount(sig(a) & ~sig(b)) * SUB_COST_ADJACENT

    and symmetrically. The SUB_COST_ADJACENT factor is the part that is easy
    to get wrong: dropping it looks like a tighter bound but is simply false -
    "thuov" -> "thuoc" style adjacent-key slips cost half a point each, so two
    of them change two character classes for a total distance of 1.0. Pruning
    on the unscaled count silently loses exactly the typos this corrector
    exists to catch.

    With the factor, it is a true lower bound rather than a heuristic, so the
    prune cannot drop a candidate the full scan would have found."""
    mask = 0
    for ch in s:
        mask |= 1 << (ord(ch) & 63)
    return mask


def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = s.lower()
    s = re.sub(r"[^\w%.\-+]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_accents(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def compact(s: str) -> str:
    """Remove hyphens/spaces so 'oral-b' and 'oralb' line up."""
    return re.sub(r"[\s\-]", "", s)


# ---------------------------------------------------------------------------
# Telex encoding: turn a *correct* Vietnamese keyword into the ASCII sequence
# a Telex typist would produce for it. This direction (accented -> telex) is
# a clean, deterministic table lookup. The reverse direction (telex -> accented)
# is ambiguous (you have to guess which vowel is the tone "nucleus"), so we
# never try to decode user input — we instead pre-encode our vocabulary and
# match the user's raw keystrokes against that.
# ---------------------------------------------------------------------------

_TONE_MARK_TO_LETTER = {
    0x0301: "s",  # acute   - sắc
    0x0300: "f",  # grave   - huyền
    0x0309: "r",  # hook    - hỏi
    0x0303: "x",  # tilde   - ngã
    0x0323: "j",  # dot     - nặng
}

_MODIFIER_SUFFIX = {
    ("a", 0x0302): "a",  # â  -> aa
    ("a", 0x0306): "w",  # ă  -> aw
    ("e", 0x0302): "e",  # ê  -> ee
    ("o", 0x0302): "o",  # ô  -> oo
    ("o", 0x031B): "w",  # ơ  -> ow
    ("u", 0x031B): "w",  # ư  -> uw
}

TELEX_TONE_KEYS = "sfrxj"
_SYLLABLE_SEPARATORS = " -"


def telex_encode(word: str) -> str:
    """Deterministically render a Vietnamese word/phrase as Telex keystrokes.

    The tone key is flushed at the end of the syllable it belongs to, not at
    the end of the whole string: "kem đánh răng" is typed "kem ddanhs rawng",
    and carrying the tone to the end would have mis-encoded every one of the
    ~10k multi-word keywords in the lexicon."""
    word = unicodedata.normalize("NFD", word.lower())
    out = []
    tone_letter = ""
    i = 0
    while i < len(word):
        ch = word[i]
        if ch in _SYLLABLE_SEPARATORS:
            out.append(tone_letter)
            tone_letter = ""
            out.append(ch)
            i += 1
            continue
        if ch == "đ":
            out.append("dd")
            i += 1
            continue
        if unicodedata.category(ch) == "Mn":
            i += 1  # stray combining mark, skip
            continue
        j = i + 1
        marks = []
        while j < len(word) and unicodedata.category(word[j]) == "Mn":
            marks.append(ord(word[j]))
            j += 1
        piece = ch
        for m in marks:
            if m in _TONE_MARK_TO_LETTER:
                tone_letter = _TONE_MARK_TO_LETTER[m]
            elif (ch, m) in _MODIFIER_SUFFIX:
                piece += _MODIFIER_SUFFIX[(ch, m)]
        out.append(piece)
        i = j
    out.append(tone_letter)
    return "".join(out)


# ---------------------------------------------------------------------------
# Telex skeleton. Real users rarely produce clean Telex — they produce a bit of
# it. "kem đánh răng" arrives as "kem ddanhs rawng", "kem danhs rang",
# "kem danh rang", or any mixture, because the tone and vowel-modifier keys are
# the first thing dropped when typing quickly. Stripping *all* of that
# decoration off both the vocabulary and the query puts every one of those
# spellings in the same place, so a half-typed word still finds its product.
# ---------------------------------------------------------------------------

# A Vietnamese syllable is onset + nucleus + coda drawn from three small closed
# sets. Parsing against them is what makes aggressive key-stripping safe:
# "tranhs" may be read as "tranh" plus a tone key because "tr" is an onset and
# "nh" is a coda, while "aspirin" is left untouched because nothing in it can
# be a coda. Without that test, stripping every stray s/f/r/x/j would shred the
# Latin drug names that fill half the catalog.
VOWELS = "aeiouy"
ONSETS = frozenset((
    "", "b", "c", "ch", "d", "g", "gh", "gi", "h", "k", "kh", "l", "m", "n",
    "ng", "ngh", "nh", "p", "ph", "qu", "r", "s", "t", "th", "tr", "v", "x",
))
# Final consonants, plus the i/o/u/y offglides that close a diphthong. None of
# s, f, r, x or j is a legal coda - that is precisely why a trailing one can
# only ever be a tone key.
CODAS = frozenset(("", "c", "ch", "m", "n", "ng", "nh", "p", "t", "i", "o", "u", "y"))
_MAX_ONSET = max(len(o) for o in ONSETS)
_MAX_CODA = max(len(c) for c in CODAS)
MAX_NUCLEUS_VOWELS = 3  # "khuyu", "nguoi" - no Vietnamese nucleus runs longer

_TONE_KEYS = frozenset(TELEX_TONE_KEYS)
# VNI types the same marks as digits: 1-5 are the tones, 6/7/8 the vowel
# shapes (â/ê/ô, ơ/ư, ă), 9 the đ. They are only read as keys in a token of at
# least this length, because below it every "syllable + digit" in the catalog
# is a product code - A4, B12, D3, CO2 - and reading the digit as a tone would
# collapse all of them onto a single letter.
_VNI_TONE_DIGITS = frozenset("12345")
_VNI_VOWEL_DIGITS = frozenset("678")
MIN_VNI_LEN = 4


def _read_nucleus(token: str, i: int, digits: bool):
    """Consume the vowel run at i, swallowing vowel-shape keys as it goes.

    "uwow" reads as ươ and "uoo" as uô, so the decorated and the bare spelling
    of a nucleus come out identical."""
    vowels = []
    n = len(token)
    while i < n and len(vowels) < MAX_NUCLEUS_VOWELS:
        ch = token[i]
        if ch in VOWELS:
            i += 1
            if i < n and token[i] == ch and ch in "aeo":
                i += 1  # aa / ee / oo -> â / ê / ô
            vowels.append(ch)
            if i < n and (
                (token[i] == "w" and ch in "aou")
                or (digits and token[i] in _VNI_VOWEL_DIGITS)
            ):
                i += 1  # aw / ow / uw, or the VNI digit spelling of the same
        elif ch == "w" and not vowels:
            vowels.append("u")  # a lone w is how ư gets typed by itself
            i += 1
        else:
            break
    if not vowels:
        return None
    return "".join(vowels), i


def _is_trailing_keys(tail: str, digits: bool, tone_used: bool) -> bool:
    """Whether tail is the keys a Telex/VNI typist flushes at the end of a
    syllable: "rangw" (ă), "tranhs" (tone), "rangwf" (both).

    At most one of each kind, which is all a syllable can carry - and which is
    what keeps English doubles out: the "ss" of "loss" is two tone keys, so
    "loss" is not a decorated syllable and survives intact."""
    if len(tail) > 2:
        return False
    seen = {"tone"} if tone_used else set()
    if tone_used and not tail:
        return False
    for ch in tail:
        if ch in _TONE_KEYS or (digits and ch in _VNI_TONE_DIGITS):
            kind = "tone"
        elif ch == "w" or (digits and ch in _VNI_VOWEL_DIGITS):
            kind = "shape"
        else:
            return False
        if kind in seen:
            return False
        seen.add(kind)
    return bool(tail)


def _parse_syllable(token: str):
    """Return the bare skeleton if token is one Vietnamese syllable, else None.

    A tone key may sit either between the nucleus and the coda ("traxnh") or
    after it ("tranhs") - both spellings are common, because the key gets
    pressed wherever the typist happens to be in the word. An undecorated
    spelling is just the case where no key is found, so this one pass accepts
    "tranh" and "tranhs" alike."""
    n = len(token)
    digits = n >= MIN_VNI_LEN
    for onset_len in range(min(_MAX_ONSET, n - 1), -1, -1):
        onset = token[:onset_len]
        if onset not in ONSETS:
            continue
        read = _read_nucleus(token, onset_len, digits)
        if read is None:
            continue
        nucleus, after_nucleus = read
        for inner_tone in (True, False):
            i = after_nucleus
            if inner_tone:
                if i >= n or not (
                    token[i] in _TONE_KEYS
                    or (digits and token[i] in _VNI_TONE_DIGITS)
                ):
                    continue
                i += 1
            for coda_len in range(min(_MAX_CODA, n - i), -1, -1):
                coda = token[i:i + coda_len]
                if coda not in CODAS:
                    continue
                end = i + coda_len
                if end == n or _is_trailing_keys(token[end:], digits, inner_tone):
                    return onset + nucleus + coda
    return None


def _fold_syllable(token: str) -> str:
    if not token:
        return token
    bare = token
    if token.startswith("dd"):
        bare = token[1:]  # đ typed as dd
    elif token.startswith("d9") and len(token) >= MIN_VNI_LEN:
        bare = "d" + token[2:]  # đ typed the VNI way
    decorated = _parse_syllable(bare)
    # Not a Vietnamese syllable at all - a brand or an INN. Leave it exactly as
    # it is rather than guessing keys out of "Paracetamol".
    return decorated if decorated is not None else token


def telex_skeleton(s: str) -> str:
    """Reduce text to bare syllables, dropping every tone and vowel-shape key
    however it was written - as a real diacritic ("đánh"), as full Telex
    ("ddanhs"), as VNI ("d9anh1"), or as the half-finished Telex people
    actually type ("danhs", "danh"). All of them collapse to "danh"."""
    if not s:
        return ""
    return " ".join(_fold_syllable(tok) for tok in strip_accents(s).split(" "))


def merge_detached_tone_keys(tokens: List[str]) -> List[str]:
    """Reattach a tone key that got typed as its own word. "banf chai r danhs"
    is one space away from "banf chair danhs" — the space lands before the tone
    key often enough that treating a lone s/f/r/x/j as a word of its own turns
    it into a garbage token to be "corrected"."""
    merged: List[str] = []
    for token in tokens:
        if merged and len(token) == 1 and token in TELEX_TONE_KEYS:
            merged[-1] += token
        else:
            merged.append(token)
    return merged


def edit_distance(a: str, b: str, max_dist: float = MAX_EDIT_DIST) -> float:
    """Levenshtein + adjacent-transposition (OSA) distance, capped for speed.

    Substitutions between physically neighboring keyboard keys cost less than
    a full point, so "thuov" lands much closer to "thuoc" (c/v are adjacent)
    than an equal-length but keyboard-implausible typo would."""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    la, lb = len(a), len(b)
    d = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            ca, cb = a[i - 1], b[j - 1]
            if ca == cb:
                cost = 0.0
            elif is_keyboard_adjacent(ca, cb):
                cost = SUB_COST_ADJACENT
            else:
                cost = SUB_COST_DEFAULT
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def is_protected(token: str) -> bool:
    token = normalize(token)
    if not token:
        return False
    if re.fullmatch(r"\d+", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?%", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(ml|mg|mcg|g)", token):
        return True
    if token in PROTECTED_TOKENS:
        return True
    return False


def search_key(s: str) -> str:
    """Reduce text to the form product names and queries are compared in.

    Accents, tone keys and half-typed Telex all fall away, so "bàn chải",
    "ban chai", "banf chair" and "ban2 chai3" become one string. Product rows
    store this once (products.search_text); queries are reduced the same way at
    lookup time so a match is a plain substring test.

    Hyphens become spaces so a brand splits into the words people type it as:
    "Oral-B" is searched for as "oral b" at least as often as "oral-b"."""
    return telex_skeleton(normalize(s).replace("-", " "))


def _term_matches(term: str, folded_name: str) -> bool:
    """A one-letter term has to land on a whole word - as a substring it is in
    nearly every name, which would make the "c" of "vitamin c" free."""
    if len(term) == 1:
        return f" {term} " in f" {folded_name} "
    return term in folded_name


class Corrector:
    def __init__(self, keywords_path, nearmiss_path, products_path=None):
        self.keywords_path = Path(keywords_path)
        self.nearmiss_path = Path(nearmiss_path)
        self.products_path = Path(products_path) if products_path else None
        self.keywords = self._load_json(self.keywords_path)
        self.nearmiss = self._load_json(self.nearmiss_path)
        self.products = self._load_products(self.products_path) if self.products_path else []

        # cached once, not recomputed per-token like the original implementation
        self._max_popularity = max(
            (float(v.get("popularity", 1)) for v in self.keywords.values()), default=1.0
        )

        # multiple "views" of the vocabulary so different typo styles all hit something
        self._telex_index: Dict[str, List[str]] = {}
        self._noaccent_index: Dict[str, List[str]] = {}
        self._compact_index: Dict[str, List[str]] = {}
        self._skeleton_index: Dict[str, List[str]] = {}
        for kw in self.keywords:
            self._telex_index.setdefault(telex_encode(kw), []).append(kw)
            self._noaccent_index.setdefault(strip_accents(kw), []).append(kw)
            self._compact_index.setdefault(compact(kw), []).append(kw)
            self._skeleton_index.setdefault(telex_skeleton(kw), []).append(kw)

        # Bucket each view separately by length for cheap pruning during the
        # fuzzy fallback. One shared bucket made every lookup walk the other
        # view's forms too, only to discard them.
        #
        # Each bucket entry carries the form's character signature, so the
        # fuzzy scan can reject most of the vocabulary with one integer AND
        # instead of an O(n*m) dynamic-programming table. Built once here,
        # where it costs a single pass over ~15k keywords at startup.
        self._by_length: Dict[int, Dict[int, List[tuple]]] = {}
        for view in (self._telex_index, self._noaccent_index):
            buckets: Dict[int, List[tuple]] = {}
            for form in view:
                buckets.setdefault(len(form), []).append((form, char_signature(form)))
            self._by_length[id(view)] = buckets

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _load_products(self, path: Path) -> List[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    # Folded once at load. Doing it per query per product made
                    # every search pay for parsing the whole catalog's names.
                    row["_search_key"] = search_key(row.get("webName", ""))
                    rows.append(row)
        return rows

    # ---- scoring helpers -------------------------------------------------

    def _popularity(self, keyword: str) -> float:
        return float(self.keywords.get(keyword, {}).get("popularity", 1))

    def _sort_candidates(self, candidates: List[dict]) -> List[dict]:
        """Confidence first, popularity only to break ties.

        Popularity used to be folded into the score itself, which let a fuzzy
        guess on a popular keyword (scoring up to 2.0) outrank an exact match
        (1.0) and made THRESHOLD/MARGIN meaningless. Scores now stay in [0, 1]
        and mean what they say."""
        return sorted(
            candidates,
            key=lambda c: (c["score"], self._popularity(c["keyword"])),
            reverse=True,
        )

    def _candidates_from_keywords(self, keywords: List[str], weight: float, rule: str) -> List[dict]:
        out = []
        for kw in keywords:
            out.append({
                "keyword": kw,
                "score": round(weight, 3),
                "rule": rule,
            })
        return self._sort_candidates(out)

    def _fuzzy_lookup(self, token: str) -> List[dict]:
        """Edit-distance fallback against telex + accent-stripped vocabulary views."""
        if len(token) < MIN_FUZZY_LEN:
            # Too short to carry a recognizable shape - every candidate would be
            # a coincidence, which is how "c" used to be "corrected" to "1".
            return []
        found: Dict[str, float] = {}  # keyword -> best distance
        # The cap actually applied further down, hoisted here so the prune can
        # use the real bound rather than the looser MAX_EDIT_DIST.
        allowed = min(MAX_EDIT_DIST, max(1, len(token) // 4 + 1))
        # How many distinct character classes may differ before the cheapest
        # possible sequence of edits already exceeds the cap.
        max_class_diff = int(allowed / SUB_COST_ADJACENT)
        token_sig = char_signature(token)
        for view in (self._telex_index, self._noaccent_index):
            buckets = self._by_length[id(view)]
            for length in range(len(token) - LEN_BUCKET_SLACK, len(token) + LEN_BUCKET_SLACK + 1):
                for form, form_sig in buckets.get(length, []):
                    # Exact lower bound on the distance, computed with two
                    # integer operations. Everything it rejects the DP would
                    # have rejected too, several hundred cell updates later.
                    if (token_sig & ~form_sig).bit_count() > max_class_diff:
                        continue
                    if (form_sig & ~token_sig).bit_count() > max_class_diff:
                        continue
                    dist = edit_distance(token, form, max_dist=allowed)
                    if dist > allowed:
                        continue
                    for kw in view[form]:
                        if kw not in found or dist < found[kw]:
                            found[kw] = dist
        candidates = []
        for kw, dist in found.items():
            if dist > allowed:
                continue
            similarity = max(0.0, 1 - dist / max(len(token), 1))
            if similarity <= 0:
                continue
            # a fractional distance means at least one keyboard-adjacent
            # substitution was used to reach this candidate cheaply
            rule = "fuzzy_keyboard" if dist != int(dist) else f"fuzzy_edit{int(dist)}"
            candidates.append({
                "keyword": kw,
                "score": round(similarity, 3),
                "rule": rule,
                "dist": dist,
            })
        return candidates

    def _can_auto_apply(self, candidate: dict) -> bool:
        """A curated or deterministic rule may correct silently. A fuzzy guess
        may only do so when it is one edit away - beyond that the user gets
        asked, because two edits is enough to reach a different drug."""
        if not candidate["rule"].startswith("fuzzy"):
            return True
        return candidate.get("dist", MAX_EDIT_DIST) <= FUZZY_AUTO_MAX_DIST

    # ---- vocabulary views --------------------------------------------------

    def _view_lookup(self, text: str):
        """Try every deterministic view of the vocabulary, most confident first,
        and report which keywords the text lands on. Shared by single-token
        correction and whole-phrase resolution so both see the same vocabulary
        through the same lenses."""
        for key, view, weight, rule in (
            (text, self._telex_index, 1.0, "telex_exact"),
            (compact(text), self._compact_index, 0.95, "compact_exact"),
            (strip_accents(text), self._noaccent_index, 0.9, "noaccent_exact"),
            (telex_skeleton(text), self._skeleton_index, 0.85, "skeleton_exact"),
        ):
            keywords = view.get(key)
            if keywords:
                return keywords, weight, rule
        return None, 0.0, ""

    def _resolve_phrase(self, phrase: str) -> Optional[dict]:
        """Resolve a multi-token span as a unit, but only when it is
        unambiguous. Phrase context is what separates "chống nắng" from
        "chóng nắng" - information that per-token correction throws away."""
        if phrase in self.keywords:
            return {
                "status": "exact",
                "token": phrase,
                "candidates": [{"keyword": phrase, "score": 1.0, "rule": "exact"}],
            }
        keywords, weight, rule = self._view_lookup(phrase)
        if not keywords or len(keywords) != 1:
            return None
        candidates = self._candidates_from_keywords(keywords, weight, rule)
        return {
            "status": "corrected",
            "token": phrase,
            "candidates": candidates,
            "suggestion": candidates[0]["keyword"],
        }

    # ---- per-token correction ---------------------------------------------

    def correct_token(self, tok: str) -> dict:
        token = normalize(tok)
        if not token:
            return {"status": "unknown", "token": tok, "candidates": []}
        if is_protected(token):
            return {"status": "protected", "token": token, "candidates": []}
        if token in self.keywords:
            return {"status": "exact", "token": token, "candidates": [{"keyword": token, "score": 1.0, "rule": "exact"}]}

        # 1-4. Deterministic views: telex keystrokes, hyphen/space-insensitive
        #      brand forms, dropped accents, and half-typed telex. No typo is
        #      involved in any of these - the user just spelled a real keyword
        #      a different way - so they outrank anything fuzzy.
        keywords, weight, rule = self._view_lookup(token)
        if keywords:
            candidates = self._candidates_from_keywords(keywords, weight, rule)
            if len(keywords) > 1:
                # Several keywords share this spelling. When they differ only in
                # their diacritics ("mat" -> mắt/mặt/mật) that is not an error to
                # resolve, it is simply how Vietnamese gets typed - flagged
                # separately so the query survives it (see _correct).
                status = "accent_ambiguous" if rule in ("noaccent_exact", "skeleton_exact") else "ambiguous"
                return {"status": status, "token": token, "candidates": candidates[:3]}
            return {"status": "corrected", "token": token, "candidates": candidates, "suggestion": candidates[0]["keyword"]}

        # 5. Legacy curated typo table, kept for the domain spelling rules
        #    (phonetic, pharma-suffix, inn-hdrop) edit distance cannot derive.
        variant_entry = self.nearmiss.get(token)
        legacy_candidates = []
        is_ambiguous = False
        if variant_entry:
            is_ambiguous = bool(variant_entry.get("amb"))
            best_by_keyword = {}
            for item in variant_entry.get("c", []):
                keyword = item.get("keyword")
                if keyword and keyword in self.keywords:
                    weight = float(item.get("weight", 0.5))
                    cand = {
                        "keyword": keyword,
                        "score": round(weight, 3),
                        "rule": item.get("rule", "nearmiss"),
                    }
                    cur = best_by_keyword.get(keyword)
                    if cur is None or cand["score"] > cur["score"]:
                        best_by_keyword[keyword] = cand
            legacy_candidates = list(best_by_keyword.values())

        # An unambiguous curated entry is authoritative. The table now holds
        # only the domain spelling conventions and pharmacist-approved pairs, so
        # it is better evidence than any live guess: "amoxycillin" has a real
        # phonetic rule behind it and must not lose a photo-finish to whichever
        # near-neighbours the fuzzy scan happens to turn up.
        if legacy_candidates and not is_ambiguous:
            best = self._sort_candidates(legacy_candidates)[0]
            if best["score"] >= THRESHOLD:
                return {"status": "corrected", "token": token, "candidates": [best], "suggestion": best["keyword"]}

        # 6. Live fuzzy fallback: catches novel typos (incl. typos on top of
        #    telex, like a transposed letter) that no static table anticipated.
        fuzzy_candidates = self._fuzzy_lookup(token)

        scored = {c["keyword"]: c for c in legacy_candidates}
        for c in fuzzy_candidates:
            cur = scored.get(c["keyword"])
            if cur is None or c["score"] > cur["score"]:
                scored[c["keyword"]] = c
        scored = self._sort_candidates([c for c in scored.values() if c["score"] > 0])

        if not scored:
            return {"status": "unknown", "token": token, "candidates": []}

        if is_ambiguous:
            return {"status": "ambiguous", "token": token, "candidates": scored[:3]}

        top = scored[0]
        second = scored[1] if len(scored) > 1 else None
        confident = top["score"] >= THRESHOLD and (second is None or top["score"] - second["score"] >= MARGIN)
        if confident and self._can_auto_apply(top):
            return {"status": "corrected", "token": token, "candidates": scored[:3], "suggestion": top["keyword"]}
        return {"status": "did_you_mean", "token": token, "candidates": scored[:3]}

    def suggest(self, prefix: str, limit: int = 10) -> list:
        prefix = normalize(prefix)
        if not prefix:
            return []
        matches = []
        for keyword, meta in self.keywords.items():
            if keyword.startswith(prefix):
                matches.append({"keyword": keyword, "popularity": meta.get("popularity", 0)})
        matches.sort(key=lambda item: item["popularity"], reverse=True)
        return matches[:limit]

    def find_products(self, query: str, limit: int = 10, min_coverage: float = 0.6) -> list:
        """Score by fraction of terms matched instead of requiring every term
        to hit, so one still-unresolved token doesn't zero out a good query."""
        terms = search_key(query).split()
        if not terms:
            return []
        results = []
        for product in self.products:
            name_key = product["_search_key"]
            hits = 0
            for term in terms:
                if _term_matches(term, name_key):
                    hits += 1
            coverage = hits / len(terms)
            if coverage >= min_coverage:
                results.append({
                    "webName": product.get("webName"),
                    "category": product.get("category"),
                    "imageUrl": product.get("image"),
                    "coverage": round(coverage, 2),
                })
        results.sort(key=lambda r: r["coverage"], reverse=True)
        return results[:limit]

    def correct(self, query: str) -> dict:
        start = time.perf_counter()
        result = self._correct(query)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return result

    def _resolve_tokens(self, tokens: List[str]) -> List[dict]:
        """Greedy longest-match: try the longest phrase first, fall back to a
        single token only when no phrase resolves. Two thirds of the lexicon is
        multi-word, so matching per token first left most of the vocabulary
        unreachable and forced guesses on words that were never ambiguous in
        context."""
        results = []
        i = 0
        while i < len(tokens):
            span = None
            for n in range(min(MAX_PHRASE_LEN, len(tokens) - i), 1, -1):
                span = self._resolve_phrase(" ".join(tokens[i:i + n]))
                if span:
                    i += n
                    break
            if span:
                results.append(span)
                continue
            results.append(self.correct_token(tokens[i]))
            i += 1
        return results

    def _correct(self, query: str) -> dict:
        tokens = merge_detached_tone_keys(normalize(query).split())
        if not tokens:
            return {"decision": "no_results", "query": query, "tokens": []}
        normalized = " ".join(tokens)

        token_results = self._resolve_tokens(tokens)

        # Build one best-effort reconstruction using EVERY token's info instead
        # of bailing out on the first problem token. An ambiguous token used to
        # abort the whole query, which meant any unaccented Vietnamese search
        # containing one ordinary homograph returned nothing at all.
        rebuilt = []
        unresolved = 0
        open_choices: List[dict] = []
        low_confidence: List[dict] = []
        for r in token_results:
            status = r["status"]
            if status in ("protected", "exact"):
                rebuilt.append(r["token"])
            elif status == "corrected":
                rebuilt.append(r["suggestion"])
            elif status == "accent_ambiguous":
                # The letters are right and only the diacritics are in doubt.
                # Keep what was typed - find_products matches accent-insensitively,
                # so committing to one arbitrary accenting could only bias the
                # results - and offer the readings alongside.
                rebuilt.append(r["token"])
                open_choices.extend(r["candidates"])
            elif status == "ambiguous":
                rebuilt.append(r["candidates"][0]["keyword"])
                open_choices.extend(r["candidates"])
                unresolved += 1
            elif status == "did_you_mean" and r["candidates"]:
                rebuilt.append(r["candidates"][0]["keyword"])  # best guess, low confidence
                low_confidence.extend(r["candidates"])
                unresolved += 1
            else:  # unknown -> pass through raw token rather than discarding the query
                rebuilt.append(r["token"])
                unresolved += 1

        suggestion = " ".join(rebuilt)
        products = self.find_products(suggestion) if self.products else []

        if open_choices:
            decision = "did_you_mean"  # real readings to choose between, results shown anyway
        elif unresolved == 0:
            decision = "auto_correct" if suggestion != normalized else "no_change"
        elif products:
            decision = "did_you_mean"  # show best guess + partial results together
        else:
            decision = "no_results"

        out = {"decision": decision, "query": query, "suggestion": suggestion, "tokens": token_results}
        # Whatever we are unsure about is what the "did you mean" panel offers.
        # Genuine readings come first; a low-confidence guess is better than the
        # empty panel a did_you_mean with nothing attached used to render.
        choices = open_choices or low_confidence
        if decision == "did_you_mean" and choices:
            out["candidates"] = self._sort_candidates(choices)[:5]
        if products:
            out["products"] = products
        return out


# ---------------------------------------------------------------------------
# Shared entry points for the rest of the app. The catalog needs the same
# notion of "these two spellings are the same word" that the corrector uses
# internally, and it needs it against the SQL product table rather than the
# JSONL snapshot - so the reduction is exported rather than reimplemented.
# ---------------------------------------------------------------------------


_shared: Optional["Corrector"] = None


def get_corrector() -> "Corrector":
    """Process-wide corrector over the built lexicon. Loading it costs ~15k
    keywords plus the product snapshot, so the API shares one instance rather
    than building it per request or per module."""
    global _shared
    if _shared is None:
        from app import config

        _shared = Corrector(
            config.KEYWORDS_PATH,
            config.NEARMISS_PATH,
            config.PRODUCTS_JSONL_PATH,
        )
    return _shared
