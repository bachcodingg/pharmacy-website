import json
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import normalize, is_protected

DATA_PATH = BASE_DIR / "data" / "products.jsonl"
OUT_PATH = BASE_DIR / "index" / "keywords.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

STOPWORDS = {
    "va", "và", "của", "cua", "cho", "la", "là", "các", "cac", "có", "co", "đi", "di", "de", "để",
    "giúp", "giup", "hỗ", "ho", "trợ", "tro", "sản", "san", "phẩm", "pham", "thuốc", "thuoc",
    "dùng", "dung", "cùng", "cung", "hàng", "hang", "nhà", "nha", "trong", "làm", "lam",
    "do", "được", "duoc", "thành", "thanh", "phần", "phan", "chính", "chinh", "khi", "khi",
    "này", "nay", "đó", "do", "với", "voi", "từ", "tu", "theo", "như", "nhu", "hoặc", "hoac",
    "một", "mot", "những", "nhung", "rất", "rat", "nên", "nen", "sau", "trước", "truoc",
    "điều", "dieu",
}

MIN_NGRAM_FREQ = 2

_CATEGORY_SUFFIX_RE = re.compile(r"\s+Danh mục\s+.*$", re.IGNORECASE)


def clean_ingredient_name(name: str) -> str:
    return _CATEGORY_SUFFIX_RE.sub("", name).strip()


def tokenise(text: str):
    return [t for t in normalize(text).split() if t]


def is_stop_or_protected(token: str) -> bool:
    return token in STOPWORDS or is_protected(token)


def build_keywords():
    ingredient_names = {}
    single_word_counts = Counter()
    ngram_counts = Counter()
    samples = {}

    def remember_sample(term, web_name):
        if term not in samples and web_name:
            samples[term] = web_name[:120]

    with DATA_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            product = json.loads(line)
            web_name = product.get("webName", "")

            for ingredient in product.get("ingredients", []):
                name = clean_ingredient_name((ingredient or {}).get("name") or "")
                if not name:
                    continue
                token = normalize(name)
                if token:
                    ingredient_names[token] = ingredient_names.get(token, 0) + 1
                    remember_sample(token, web_name)
                for word in tokenise(name):
                    if len(word) > 2 and not is_stop_or_protected(word):
                        single_word_counts[word] += 1
                        remember_sample(word, web_name)

            tokens = [t for t in tokenise(web_name) if not is_stop_or_protected(t)]
            for tok in tokens:
                if len(tok) > 1:
                    single_word_counts[tok] += 1
                    remember_sample(tok, web_name)
            for n in range(2, 5):
                for i in range(len(tokens) - n + 1):
                    phrase = " ".join(tokens[i:i + n])
                    ngram_counts[phrase] += 1
                    remember_sample(phrase, web_name)

    rows = {}

    for name, freq in ingredient_names.items():
        rows[name] = {"type": "ingredient", "popularity": freq * 5, "ascii": name, "sample": samples.get(name, "")}

    for word, freq in single_word_counts.items():
        if word in rows:
            continue
        rows[word] = {"type": "word", "popularity": freq, "ascii": word, "sample": samples.get(word, "")}

    for phrase, freq in ngram_counts.items():
        if freq < MIN_NGRAM_FREQ or phrase in rows:
            continue
        rows[phrase] = {"type": "ngram", "popularity": freq, "ascii": phrase, "sample": samples.get(phrase, "")}

    with OUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    return rows


if __name__ == "__main__":
    rows = build_keywords()
    top = sorted(rows.items(), key=lambda kv: kv[1]["popularity"], reverse=True)[:20]
    print(f"wrote {OUT_PATH} ({len(rows)} keywords)")
    print("top 20 by popularity:")
    for term, meta in top:
        print(f"  {term!r:40s} {meta['type']:10s} pop={meta['popularity']}")
