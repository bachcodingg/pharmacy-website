import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from learning.mine_pairs import find_candidate_pairs  # noqa: E402
from build.build_nearmiss import build_table  # noqa: E402


def test_mines_pair_when_first_query_failed_and_second_was_clicked():
    query_events = [
        {"session_id": "s1", "ts": 0, "query": "etrogen", "result_count": 0},
        {"session_id": "s1", "ts": 10, "query": "estrogen", "result_count": 4},
        {"session_id": "s2", "ts": 0, "query": "etrogen", "result_count": 0},
        {"session_id": "s2", "ts": 5, "query": "estrogen", "result_count": 4},
    ]
    click_events = [
        {"session_id": "s1", "ts": 11, "query": "estrogen"},
        {"session_id": "s2", "ts": 6, "query": "estrogen"},
    ]

    candidates = find_candidate_pairs(query_events, click_events)
    match = next((c for c in candidates if c["from_query"] == "etrogen" and c["to_query"] == "estrogen"), None)
    assert match is not None
    assert match["distinct_sessions"] == 2
    assert match["meets_threshold"] is True


def test_does_not_mine_pair_when_first_query_already_worked():
    query_events = [
        {"session_id": "s1", "ts": 0, "query": "paracetamol", "result_count": 3},
        {"session_id": "s1", "ts": 5, "query": "vitamin c", "result_count": 2},
    ]
    click_events = [
        {"session_id": "s1", "ts": 1, "query": "paracetamol"},
        {"session_id": "s1", "ts": 6, "query": "vitamin c"},
    ]

    candidates = find_candidate_pairs(query_events, click_events)
    assert not any(c["from_query"] == "paracetamol" for c in candidates)


def test_does_not_mine_pair_when_queries_are_unrelated():
    query_events = [
        {"session_id": "s1", "ts": 0, "query": "etrogen", "result_count": 0},
        {"session_id": "s1", "ts": 5, "query": "completely different thing", "result_count": 2},
    ]
    click_events = [
        {"session_id": "s1", "ts": 6, "query": "completely different thing"},
    ]

    candidates = find_candidate_pairs(query_events, click_events)
    assert not any(c["from_query"] == "etrogen" for c in candidates)


def test_does_not_mine_pair_outside_session_window():
    query_events = [
        {"session_id": "s1", "ts": 0, "query": "etrogen", "result_count": 0},
        {"session_id": "s1", "ts": 500, "query": "estrogen", "result_count": 4},
    ]
    click_events = [
        {"session_id": "s1", "ts": 501, "query": "estrogen"},
    ]

    candidates = find_candidate_pairs(query_events, click_events)
    assert not any(c["from_query"] == "etrogen" for c in candidates)


def test_approved_pair_feeds_into_nearmiss_table_and_respects_ambiguity():
    keywords = {"estrogen": {}, "estradiol": {}}
    learned_pairs = [{"from_query": "etrogen", "to_query": "estrogen"}]

    table = build_table(keywords, learned_pairs=learned_pairs)
    assert "etrogen" in table
    rules = {c["rule"] for c in table["etrogen"]["c"]}
    assert "learned" in rules

    ambiguous_learned_pairs = [
        {"from_query": "estroXen", "to_query": "estrogen"},
        {"from_query": "estroXen", "to_query": "estradiol"},
    ]
    table2 = build_table(keywords, learned_pairs=ambiguous_learned_pairs)
    assert table2["estroxen"]["amb"] is True
