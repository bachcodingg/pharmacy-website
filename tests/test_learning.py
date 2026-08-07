import unittest

from crawl_longchau import learn_from_logs


class LearningStage7Tests(unittest.TestCase):
    def test_extracts_approved_typo_pairs_from_logs(self):
        logs = [
            {"session_id": "s1", "query": "etrogen", "result_count": 0, "clicked": False, "added_to_cart": False},
            {"session_id": "s1", "query": "estrogen", "result_count": 1, "clicked": True, "added_to_cart": True},
        ]

        pairs = learn_from_logs(logs)
        self.assertEqual(pairs[0]["from_query"], "etrogen")
        self.assertEqual(pairs[0]["to_query"], "estrogen")


if __name__ == "__main__":
    unittest.main()
