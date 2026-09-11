import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from app import config  # noqa: E402

from app.db import get_connection, init_db  # noqa: E402

CLICK_LOG_PATH = config.CLICK_LOG_PATH


def aggregate():
    """Recompute click_counts from logs/clicks.jsonl. This is the closest
    proxy this project has to "best-selling" - a click on a search result is
    not a purchase, there is no checkout yet to produce real order data, so
    this measures search-result popularity, not sales. Matches clicks to
    products by exact webName text (that's what the frontend sends), so a
    click only counts if it matches a product currently in the catalog."""
    init_db()
    if not CLICK_LOG_PATH.exists():
        return 0

    counts = Counter()
    with CLICK_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            product_name = entry.get("product")
            if product_name:
                counts[product_name] += 1

    updated = 0
    with get_connection() as conn:
        conn.execute("DELETE FROM click_counts")
        for web_name, count in counts.items():
            row = conn.execute("SELECT id FROM products WHERE web_name = ?", (web_name,)).fetchone()
            if not row:
                continue
            conn.execute(
                "INSERT INTO click_counts (product_id, count) VALUES (?, ?) "
                "ON CONFLICT(product_id) DO UPDATE SET count = count + excluded.count",
                (row["id"], count),
            )
            updated += 1
    return updated


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n = aggregate()
    print(f"updated click_counts for {n} products from {CLICK_LOG_PATH}")
