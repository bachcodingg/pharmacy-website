import os
import tempfile
import unittest

from crawl_longchau import (
    build_lookup_table,
    learn_from_logs,
    load_learned_pairs,
    resolve_query,
    save_learned_pairs,
)


class ConfidenceAndPersistenceTests(unittest.TestCase):
    def test_resolves_low_confidence_match_as_review(self):
        table = {
            "etrogen": [
                {
                    "variant": "etrogen",
                    "keyword": "estrogen",
                    "rule": "basic_edit",
                    "weight": 0.3,
                    "is_ambiguous": False,
                }
            ]
        }
        result = resolve_query("etrogen", table, min_confidence=0.5)
        self.assertEqual(result["decision"], "review")
        self.assertLess(result["confidence"], 0.5)

    def test_learned_pairs_are_persisted_and_loaded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "learned_pairs.json")
            pairs = [
                {"from_query": "azotel", "to_query": "azoltel", "confidence": 0.93},
            ]
            save_learned_pairs(pairs, path)
            loaded = load_learned_pairs(path)
            self.assertEqual(loaded[0]["to_query"], "azoltel")

            logs = [
                {"session_id": "s1", "query": "azotel", "result_count": 0, "clicked": False},
                {"session_id": "s1", "query": "azoltel", "result_count": 3, "clicked": True},
            ]
            merged = learn_from_logs(logs, store_path=path)
            self.assertTrue(any(item["to_query"] == "azoltel" for item in merged))


if __name__ == "__main__":
    unittest.main()
