"""Environment-driven settings.

Everything the container needs to write to lives behind a variable here.
Before this existed only PHARMACY_SEARCH_DB was overridable, so the query
logs, the click logs and the pharmacist-approved correction pairs all
resolved to paths *inside the image* - and Fly stops the machine whenever
traffic idles, so every restart silently discarded them. The learning loop
could never accumulate anything. Anything stateful now defaults under
DATA_DIR, which production points at the mounted volume.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


# Where mutable state lives. In production this is the Fly volume mount
# (/data); locally it falls back to backend/data so a checkout runs with no
# configuration at all.
DATA_DIR = _path_from_env("PHARMACY_DATA_DIR", BASE_DIR / "data")

DB_PATH = _path_from_env("PHARMACY_SEARCH_DB", DATA_DIR / "app.db")

# Query and click logs. Analytics input for eval/query_log.py and
# learning/mine_pairs.py - worthless if a redeploy resets them.
LOG_DIR = _path_from_env("PHARMACY_LOG_DIR", DATA_DIR / "logs")
QUERY_LOG_PATH = LOG_DIR / "queries.jsonl"
CLICK_LOG_PATH = LOG_DIR / "clicks.jsonl"

# Mined candidate pairs and the pharmacist's approvals. These represent human
# review time; losing them costs more than losing the logs.
LEARNING_DIR = _path_from_env("PHARMACY_LEARNING_DIR", DATA_DIR / "learning")
CANDIDATES_PATH = LEARNING_DIR / "candidate_pairs.json"
APPROVED_PATH = LEARNING_DIR / "approved_pairs.json"

# Derived search index. Rebuilt from the catalogue at image-build time, so it
# belongs in the image rather than on the volume.
INDEX_DIR = _path_from_env("PHARMACY_INDEX_DIR", BASE_DIR / "index")
KEYWORDS_PATH = INDEX_DIR / "keywords.json"
NEARMISS_PATH = INDEX_DIR / "nearmiss.json"

PRODUCTS_JSONL_PATH = _path_from_env("PHARMACY_PRODUCTS_PATH", BASE_DIR / "data" / "products.jsonl")


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Returning a password-reset token in the HTTP response is an account-takeover
# vector: anyone who knows an email address can request the token and use it.
# It is useful exactly once - in local development, before an email provider
# is wired up - so it is off unless explicitly switched on, and it must never
# be set in production.
EXPOSE_RESET_TOKEN = _flag("PHARMACY_EXPOSE_RESET_TOKEN", False)

# Rate limiting is per-process and in-memory, which is correct for the current
# single-machine deployment and would move to Redis or the edge on the day a
# second machine exists.
RATE_LIMIT_ENABLED = _flag("PHARMACY_RATE_LIMIT_ENABLED", True)

# Caps on anything a caller can make arbitrarily large. The fuzzy corrector
# runs an O(n*m) edit distance against ~15k vocabulary forms, and the query
# and click logs are appended to by unauthenticated endpoints.
MAX_QUERY_LENGTH = int(os.environ.get("PHARMACY_MAX_QUERY_LENGTH", "200"))
MAX_LOG_FIELD_LENGTH = int(os.environ.get("PHARMACY_MAX_LOG_FIELD_LENGTH", "500"))


def ensure_dirs() -> None:
    for directory in (DATA_DIR, LOG_DIR, LEARNING_DIR):
        directory.mkdir(parents=True, exist_ok=True)
