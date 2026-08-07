import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import normalize  # noqa: E402

QUERY_LOG_PATH = BASE_DIR / "logs" / "queries.jsonl"
CLICK_LOG_PATH = BASE_DIR / "logs" / "clicks.jsonl"
CANDIDATES_PATH = BASE_DIR / "learning" / "candidate_pairs.json"

SESSION_WINDOW_SECONDS = 60
MAX_EDIT_DISTANCE = 3
MIN_OCCURRENCES = 2
MIN_DISTINCT_SESSIONS = 2


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def find_candidate_pairs(query_events, click_events):
    """Mine (from_query, to_query) pairs from session logs.

    A pair is only a candidate if ALL of:
      - q1 returned zero results, or nothing was clicked for it
      - q2 happened in the same session within SESSION_WINDOW_SECONDS and got a click
      - q1 and q2 are close enough to plausibly be the same typo (small edit distance)

    This deliberately does NOT accept "user searched X then bought Y" as a signal on
    its own - if q1 already got a click, it already worked, so there is nothing to
    correct. Naively pairing consecutive queries would poison the dictionary with
    unrelated searches.
    """
    clicked_by_session_query = defaultdict(set)
    for c in click_events:
        clicked_by_session_query[c.get("session_id")].add(normalize(c.get("query", "")))

    by_session = defaultdict(list)
    for q in query_events:
        by_session[q.get("session_id")].append(q)
    for session_id in by_session:
        by_session[session_id].sort(key=lambda e: e.get("ts", 0))

    pair_sessions = defaultdict(set)
    pair_occurrences = defaultdict(int)

    for session_id, events in by_session.items():
        clicked_queries = clicked_by_session_query.get(session_id, set())
        for i, q1 in enumerate(events):
            q1_norm = normalize(q1.get("query", ""))
            if not q1_norm:
                continue
            q1_failed = q1.get("result_count", 0) == 0 or q1_norm not in clicked_queries
            if not q1_failed:
                continue

            for q2 in events[i + 1:]:
                if q2.get("ts", 0) - q1.get("ts", 0) > SESSION_WINDOW_SECONDS:
                    break
                q2_norm = normalize(q2.get("query", ""))
                if not q2_norm or q2_norm == q1_norm:
                    continue
                if q2_norm not in clicked_queries:
                    continue
                if _levenshtein(q1_norm, q2_norm) > MAX_EDIT_DISTANCE:
                    continue

                key = (q1_norm, q2_norm)
                pair_sessions[key].add(session_id)
                pair_occurrences[key] += 1
                break

    candidates = []
    for (from_query, to_query), occurrences in pair_occurrences.items():
        distinct_sessions = len(pair_sessions[(from_query, to_query)])
        candidates.append({
            "from_query": from_query,
            "to_query": to_query,
            "occurrences": occurrences,
            "distinct_sessions": distinct_sessions,
            "meets_threshold": occurrences >= MIN_OCCURRENCES and distinct_sessions >= MIN_DISTINCT_SESSIONS,
        })
    candidates.sort(key=lambda c: (c["distinct_sessions"], c["occurrences"]), reverse=True)
    return candidates


def load_candidates():
    if not CANDIDATES_PATH.exists():
        return []
    return json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))


def save_candidates(candidates):
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")


def run():
    """Mine logs, merge with any existing candidate pairs (preserving review status),
    and write the merged set back. Nothing here touches the live near-miss table -
    see learning/review.py for the pharmacist-approval gate that does."""
    query_events = _read_jsonl(QUERY_LOG_PATH)
    click_events = _read_jsonl(CLICK_LOG_PATH)
    mined = find_candidate_pairs(query_events, click_events)

    existing = {(c["from_query"], c["to_query"]): c for c in load_candidates()}
    for candidate in mined:
        key = (candidate["from_query"], candidate["to_query"])
        if key in existing:
            candidate["status"] = existing[key].get("status", "pending")
        else:
            candidate["status"] = "pending"
    save_candidates(mined)
    return mined


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = run()
    pending = [c for c in result if c["status"] == "pending" and c["meets_threshold"]]
    print(f"{len(result)} candidate pairs total, {len(pending)} pending and above threshold")
    for c in pending:
        print(f"  {c['from_query']!r} -> {c['to_query']!r}  (occurrences={c['occurrences']}, sessions={c['distinct_sessions']})")
