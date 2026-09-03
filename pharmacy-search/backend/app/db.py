import os
import sqlite3
from pathlib import Path

from app.corrector import search_key

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("PHARMACY_SEARCH_DB", str(BASE_DIR / "data" / "app.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    label TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    line1 TEXT NOT NULL,
    line2 TEXT,
    city TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    source_sku TEXT,
    source_url TEXT UNIQUE,
    web_name TEXT NOT NULL,
    short_description TEXT,
    category TEXT,
    brand TEXT,
    brand_is_estimated INTEGER NOT NULL DEFAULT 0,
    prescription INTEGER,
    ingredients_json TEXT,
    price INTEGER,
    price_unit TEXT,
    currency TEXT NOT NULL DEFAULT 'VND',
    price_is_estimated INTEGER NOT NULL DEFAULT 0,
    stock INTEGER,
    stock_is_estimated INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    image_url TEXT,
    search_text TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    address_id INTEGER REFERENCES addresses(id),
    shipping_method TEXT NOT NULL,
    shipping_fee INTEGER NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    discount_code TEXT,
    discount_amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    web_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    price_was_estimated INTEGER NOT NULL DEFAULT 0,
    line_total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS click_counts (
    product_id INTEGER PRIMARY KEY REFERENCES products(id),
    count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    saved_for_later INTEGER NOT NULL DEFAULT 0,
    added_at REAL NOT NULL,
    UNIQUE(user_id, product_id)
);

CREATE TABLE IF NOT EXISTS discount_codes (
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cart_discounts (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    code TEXT NOT NULL REFERENCES discount_codes(code)
);

CREATE TABLE IF NOT EXISTS wishlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    added_at REAL NOT NULL,
    UNIQUE(user_id, product_id)
);
"""

SEED_DISCOUNT_CODES = [
    ("WELCOME10", "percent", 10),
    ("SAVE20K", "fixed", 20000),
]


def seed_discount_codes() -> None:
    with get_connection() as conn:
        for code, kind, value in SEED_DISCOUNT_CODES:
            conn.execute(
                "INSERT INTO discount_codes (code, kind, value, active) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(code) DO NOTHING",
                (code, kind, value),
            )


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_search_text(conn: sqlite3.Connection) -> None:
    """Keep products.search_text present and populated.

    The column holds the accent- and tone-stripped form of web_name that
    catalog search matches against, so a query typed without diacritics
    ("ban chai") still finds "Bàn chải ...". Databases created before the
    column existed get it added and backfilled here rather than needing a
    rebuild."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
    if "search_text" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN search_text TEXT")
    # Every row is reconciled, not just the empty ones, so that a change to how
    # names are folded takes effect on the next start and a write site that
    # forgot to update the column repairs itself. That is a full table scan at
    # startup - fine for a catalog this size, but it would want a stored
    # fold-version marker before the catalog grew much larger.
    stale = [
        (key, row["id"])
        for row in conn.execute("SELECT id, web_name, search_text FROM products")
        for key in [search_key(row["web_name"])]
        if key != row["search_text"]
    ]
    if stale:
        conn.executemany("UPDATE products SET search_text = ? WHERE id = ?", stale)


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_search_text(conn)
    seed_discount_codes()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}
