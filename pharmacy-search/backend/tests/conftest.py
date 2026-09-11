import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

# Every mutable path is redirected into a throwaway directory, so a test run
# never touches the developer's database, query logs or approved correction
# pairs - and so the suite exercises the same env-var plumbing production uses.
_test_data_dir = tempfile.mkdtemp(prefix="pharmacy-search-test-")
os.environ["PHARMACY_DATA_DIR"] = _test_data_dir
os.environ["PHARMACY_SEARCH_DB"] = str(Path(_test_data_dir) / "test.db")
os.environ["PHARMACY_LOG_DIR"] = str(Path(_test_data_dir) / "logs")
os.environ["PHARMACY_LEARNING_DIR"] = str(Path(_test_data_dir) / "learning")

# Off by default: the suite registers dozens of accounts from one client and
# would otherwise trip its own limiter. test_ratelimit.py turns it back on for
# the tests that are specifically about it.
os.environ["PHARMACY_RATE_LIMIT_ENABLED"] = "0"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Keep limiter state from leaking between tests that do enable it."""
    from app import ratelimit

    ratelimit.reset_all()
    yield
    ratelimit.reset_all()
