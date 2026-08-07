import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.db import get_connection, init_db  # noqa: E402


def promote(email: str) -> bool:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row["id"],))
    return True


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Grant admin access to an existing account. No self-serve admin signup on purpose.")
    parser.add_argument("email")
    args = parser.parse_args()

    if promote(args.email):
        print(f"{args.email} is now an admin.")
    else:
        print(f"No account found for {args.email} - they need to register first.")
