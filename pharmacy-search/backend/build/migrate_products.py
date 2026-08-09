import hashlib
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.db import get_connection, init_db  # noqa: E402

DATA_PATH = BASE_DIR / "data" / "products.jsonl"

PRICE_BANDS = {
    "thuoc": (30_000, 250_000),
    "thuc-pham-chuc-nang": (80_000, 600_000),
    "duoc-my-pham": (60_000, 450_000),
    "cham-soc-ca-nhan": (20_000, 200_000),
    "trang-thiet-bi-y-te": (50_000, 900_000),
}
DEFAULT_PRICE_BAND = (30_000, 300_000)

_KNOWN_PACK_WORDS = {"viên", "vỉ", "hộp", "ống", "gói", "chai", "tuýp", "vi", "hop"}


def guess_brand(web_name: str):
    """Best-effort heuristic only: the last capitalized word-run before a
    parenthesis or digit, e.g. "Thuốc Panadol Extra 500mg" -> "Panadol Extra".
    This is frequently wrong for generic/compound names - callers must treat
    it as a low-confidence guess, which is why brand_is_estimated exists."""
    cleaned = re.split(r"[\(\d]", web_name)[0]
    words = cleaned.split()
    brand_words = []
    for word in reversed(words):
        stripped = word.strip(",.-")
        if not stripped:
            continue
        if stripped.lower() in _KNOWN_PACK_WORDS:
            break
        if stripped[0].isupper():
            brand_words.insert(0, stripped)
        else:
            break
    return " ".join(brand_words) if brand_words else None


def deterministic_seed(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)


def estimate_price(category: str, seed: int) -> int:
    low, high = PRICE_BANDS.get(category, DEFAULT_PRICE_BAND)
    span = high - low
    value = low + (seed % span)
    return round(value / 1000) * 1000


def estimate_stock(seed: int) -> int:
    return (seed // 97) % 120


def migrate():
    init_db()
    if not DATA_PATH.exists():
        print(f"no data file at {DATA_PATH}, nothing to migrate")
        return 0, 0

    inserted = 0
    skipped = 0
    with get_connection() as conn:
        with DATA_PATH.open("r", encoding="utf-8") as handle:
            for i, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                product = json.loads(line)
                source_url = product.get("url")
                web_name = product.get("webName")
                if not web_name:
                    skipped += 1
                    continue

                existing = conn.execute("SELECT id FROM products WHERE source_url = ?", (source_url,)).fetchone()
                if existing:
                    continue

                category = product.get("category")
                seed = deterministic_seed(source_url or web_name)

                real_brand = product.get("brand")
                brand = real_brand or guess_brand(web_name)
                brand_is_estimated = real_brand is None and brand is not None

                real_price = product.get("price")
                price_is_estimated = real_price is None
                price = real_price if real_price is not None else estimate_price(category, seed)

                sku = f"LC-{i:05d}"

                conn.execute(
                    """INSERT INTO products
                    (sku, source_sku, source_url, web_name, short_description, category, brand, brand_is_estimated,
                     prescription, ingredients_json, price, price_unit, currency, price_is_estimated, stock, stock_is_estimated,
                     image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VND', ?, ?, 1, ?)""",
                    (
                        sku,
                        product.get("sourceSku"),
                        source_url,
                        web_name,
                        product.get("shortDescription"),
                        category,
                        brand,
                        int(brand_is_estimated),
                        product.get("prescription"),
                        json.dumps(product.get("ingredients", []), ensure_ascii=False),
                        price,
                        product.get("priceUnit"),
                        int(price_is_estimated),
                        estimate_stock(seed),
                        product.get("image"),
                    ),
                )
                inserted += 1
    return inserted, skipped


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    inserted, skipped = migrate()
    print(f"migrated {inserted} products ({skipped} skipped for missing webName)")
    print("Price and brand are real where the site exposed them (see products.jsonl); every row still")
    print("carries price_is_estimated / brand_is_estimated so the fallback cases are always distinguishable.")
    print("Stock has no real source at all (the site's product JSON has no quantity field) - always estimated.")
