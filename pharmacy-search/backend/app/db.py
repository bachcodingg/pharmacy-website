import contextlib
import json
import sqlite3
import time

from app import config
from app.corrector import search_key

BASE_DIR = config.BASE_DIR
DB_PATH = config.DB_PATH

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
    created_at REAL NOT NULL,
    -- Recorded at review time from the reviewer's own order history. Reviews
    -- are still open to any signed-in account - restricting them to buyers is
    -- a policy switch, and this is the data it would switch on - but a reader
    -- can now tell which ratings came from someone who actually bought the
    -- thing.
    verified_purchase INTEGER NOT NULL DEFAULT 0
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

-- Every privileged mutation is recorded: price and stock edits, order status
-- changes, prescription decisions, admin promotions. A pharmacy selling
-- prescription-only medicines has to be able to answer "who approved this,
-- and when" after the fact.
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT,
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

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Not one index existed beyond the implicit primary and unique keys, so every
# cart read, order listing, review lookup and session validation was a full
# table scan. Invisible at 1,894 products and a handful of users; linear
# degradation with every row after that.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_addresses_user ON addresses(user_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_wishlist_items_user ON wishlist_items(user_id);
-- Unique, not just an index: "one review per user per product" was enforced
-- only by a SELECT-then-INSERT in the handler, which two concurrent requests
-- pass together. Declared here rather than in CREATE TABLE so existing
-- databases get it too.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reviews_product_user ON reviews(product_id, user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_log(created_at DESC);
"""

# Forward-only, numbered, idempotent. Not Alembic - but it replaces "the
# schema is whatever CREATE TABLE IF NOT EXISTS last left behind" with a
# recorded version you can read off a running database, which is the property
# that was actually missing.
MIGRATIONS: list[tuple[int, str]] = [
    (1, "ALTER TABLE products ADD COLUMN search_text TEXT"),
    (2, "ALTER TABLE orders ADD COLUMN requires_prescription INTEGER NOT NULL DEFAULT 0"),
    (3, "ALTER TABLE orders ADD COLUMN prescription_status TEXT"),
    (4, "ALTER TABLE orders ADD COLUMN prescription_reference TEXT"),
    (5, "ALTER TABLE reviews ADD COLUMN verified_purchase INTEGER NOT NULL DEFAULT 0"),
]

# Bumped whenever search_key() changes how a name is folded. The startup
# reconciliation used to rewrite all 1,894 product rows on every single boot;
# now it only does that when the folding logic itself moved.
SEARCH_TEXT_FOLD_VERSION = "1"

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
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers run while a writer holds the lock, which matters now
    # that checkout takes the write lock up front (see write_transaction).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextlib.contextmanager
def write_transaction():
    """A transaction that takes SQLite's write lock immediately.

    SQLite defaults to deferred transactions: the lock is only acquired at the
    first write, so two callers can both read, both decide they have enough
    stock, and both write. BEGIN IMMEDIATE makes the second caller wait at the
    start instead of discovering the conflict after it has already made its
    decision. Used by checkout, where that interleaving oversells inventory."""
    conn = get_connection()
    conn.isolation_level = None  # explicit transaction control, no implicit BEGIN
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _run_migrations(conn: sqlite3.Connection) -> int:
    """Apply every migration newer than the recorded schema_version.

    A statement that a fresh CREATE TABLE already satisfies (a column the
    current SCHEMA declares) raises "duplicate column name"; that is the
    expected path on a new database, not a failure, so it is swallowed and the
    version still advances. Anything else is a real error and propagates."""
    current = int(get_meta(conn, "schema_version") or 0)
    applied = 0
    for version, statement in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        set_meta(conn, "schema_version", str(version))
        current = version
        applied += 1
    return applied


def _ensure_search_text(conn: sqlite3.Connection) -> None:
    """Keep products.search_text present and populated.

    The column holds the accent- and tone-stripped form of web_name that
    catalog search matches against, so a query typed without diacritics
    ("ban chai") still finds "Bàn chải ...".

    Rows are only re-folded when SEARCH_TEXT_FOLD_VERSION has moved since the
    last run; otherwise just the rows missing a value are filled in. Before
    this marker existed every boot rewrote the entire products table."""
    fold_changed = get_meta(conn, "search_text_fold_version") != SEARCH_TEXT_FOLD_VERSION
    if fold_changed:
        rows = conn.execute("SELECT id, web_name, search_text FROM products")
    else:
        rows = conn.execute(
            "SELECT id, web_name, search_text FROM products WHERE search_text IS NULL OR search_text = ''"
        )
    stale = [
        (key, row["id"])
        for row in rows
        for key in [search_key(row["web_name"])]
        if key != row["search_text"]
    ]
    if stale:
        conn.executemany("UPDATE products SET search_text = ? WHERE id = ?", stale)
    if fold_changed:
        set_meta(conn, "search_text_fold_version", SEARCH_TEXT_FOLD_VERSION)


def purge_expired_sessions() -> int:
    """Expired sessions were never deleted, so the table grew without bound and
    every one of those rows stayed a valid-looking token in a backup."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        conn.execute("DELETE FROM password_reset_tokens WHERE expires_at <= ?", (time.time(),))
        return cursor.rowcount


def record_admin_action(conn, admin_user_id: int, action: str, entity: str,
                        entity_id=None, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO admin_audit_log (admin_user_id, action, entity, entity_id, detail_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (admin_user_id, action, entity, str(entity_id) if entity_id is not None else None,
         json.dumps(detail, ensure_ascii=False) if detail else None, time.time()),
    )


def init_db() -> None:
    config.ensure_dirs()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        conn.executescript(INDEXES)
        _ensure_search_text(conn)
    seed_discount_codes()
    purge_expired_sessions()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}
