import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

_test_db_dir = tempfile.mkdtemp(prefix="pharmacy-search-test-db-")
os.environ["PHARMACY_SEARCH_DB"] = str(Path(_test_db_dir) / "test.db")
