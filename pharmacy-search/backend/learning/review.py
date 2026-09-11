import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import config  # noqa: E402

# Under PHARMACY_LEARNING_DIR (the mounted volume in production) rather than
# next to this file inside the image. These are a pharmacist's decisions;
# they have to outlive a redeploy.
CANDIDATES_PATH = config.CANDIDATES_PATH
APPROVED_PATH = config.APPROVED_PATH


def load(path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_pending():
    candidates = load(CANDIDATES_PATH)
    pending = [c for c in candidates if c.get("status") == "pending" and c.get("meets_threshold")]
    if not pending:
        print("No candidate pairs awaiting review.")
        return
    print(f"{len(pending)} candidate pair(s) awaiting review:\n")
    for c in pending:
        print(f"  {c['from_query']!r} -> {c['to_query']!r}  (occurrences={c['occurrences']}, sessions={c['distinct_sessions']})")
    print("\nApprove with:  python review.py --approve \"<from_query>\" \"<to_query>\"")
    print("Reject with:   python review.py --reject  \"<from_query>\" \"<to_query>\"")


def set_status(from_query, to_query, status):
    candidates = load(CANDIDATES_PATH)
    match = next((c for c in candidates if c["from_query"] == from_query and c["to_query"] == to_query), None)
    if not match:
        print(f"No candidate pair found for {from_query!r} -> {to_query!r}")
        return
    match["status"] = status
    save(CANDIDATES_PATH, candidates)

    if status == "approved":
        approved = load(APPROVED_PATH)
        if not any(a["from_query"] == from_query and a["to_query"] == to_query for a in approved):
            approved.append({"from_query": from_query, "to_query": to_query})
        save(APPROVED_PATH, approved)
        print(f"Approved: {from_query!r} -> {to_query!r}. Run build/build_nearmiss.py to apply it.")
    else:
        print(f"Rejected: {from_query!r} -> {to_query!r}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Pharmacist approval gate for learned typo pairs. Nothing enters the near-miss table without going through --approve here.")
    parser.add_argument("--approve", nargs=2, metavar=("FROM_QUERY", "TO_QUERY"))
    parser.add_argument("--reject", nargs=2, metavar=("FROM_QUERY", "TO_QUERY"))
    args = parser.parse_args()

    if args.approve:
        set_status(args.approve[0], args.approve[1], "approved")
    elif args.reject:
        set_status(args.reject[0], args.reject[1], "rejected")
    else:
        list_pending()
