"""Cache behaviour for Corrector.correct().

The cache is only safe because corrections are pure - the lexicon is immutable
once loaded, so an entry can never go stale. These tests pin the three things
that would quietly break that: the result must be identical to an uncached
one, callers must not be able to mutate the cached entry through the value
they are handed, and the raw `query` echo must survive normalization.
"""
import sys
from pathlib import Path

from app.corrector import CORRECTION_CACHE_SIZE, Corrector

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def _make_corrector():
    return Corrector(
        BASE_DIR / "index" / "keywords.json",
        BASE_DIR / "index" / "nearmiss.json",
        BASE_DIR / "data" / "products.jsonl",
    )


def _payload(result: dict) -> dict:
    """Everything except the per-call fields, which are expected to differ."""
    return {k: v for k, v in result.items() if k not in ("latency_ms", "query")}


def test_cached_result_matches_uncached():
    corrector = _make_corrector()
    first = corrector.correct("etrogen")
    second = corrector.correct("etrogen")
    assert _payload(first) == _payload(second)
    assert corrector.cache_stats()["hits"] == 1


def test_cache_key_is_normalized():
    """Case and runs of whitespace must not each burn their own entry."""
    corrector = _make_corrector()
    corrector.correct("etrogen")
    corrector.correct("  ETROGEN  ")
    stats = corrector.cache_stats()
    assert stats["size"] == 1
    assert stats["hits"] == 1


def test_raw_query_is_echoed_not_the_cache_key():
    """A hit must report what *this* caller typed, not what populated the entry."""
    corrector = _make_corrector()
    corrector.correct("etrogen")
    assert corrector.correct("ETROGEN")["query"] == "ETROGEN"


def test_caller_cannot_mutate_the_cached_entry():
    corrector = _make_corrector()
    corrector.correct("etrogen")
    leaked = corrector.correct("etrogen")
    leaked["decision"] = "CLOBBERED"
    leaked["tokens"].clear()  # nested, so a shallow copy would not save us
    assert corrector.correct("etrogen")["decision"] != "CLOBBERED"
    assert corrector.correct("etrogen")["tokens"] != []


def test_cache_is_bounded_and_evicts_oldest_first():
    corrector = _make_corrector()
    corrector.correct("etrogen")
    for i in range(CORRECTION_CACHE_SIZE):
        corrector.correct(f"zzq{i}")  # nonsense tokens, distinct keys
    stats = corrector.cache_stats()
    assert stats["size"] == CORRECTION_CACHE_SIZE
    # The first query is the least recently used, so it is the one evicted.
    hits_before = stats["hits"]
    corrector.correct("etrogen")
    assert corrector.cache_stats()["hits"] == hits_before


def test_repeated_query_is_served_faster_than_the_first():
    """The whole point: the fuzzy fallback runs once per distinct query."""
    corrector = _make_corrector()
    miss = corrector.correct("etrogen")["latency_ms"]
    hit = corrector.correct("etrogen")["latency_ms"]
    assert hit < miss
