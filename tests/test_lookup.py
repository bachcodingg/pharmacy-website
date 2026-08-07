import unittest

from crawl_longchau import build_lookup_table, lookup_variant


class LookupStage5Tests(unittest.TestCase):
    def test_builds_and_queries_lookup_table(self):
        rows = [
            {"variant": "etrogen", "keyword": "estrogen", "rule": "basic_edit", "weight": 0.8, "is_ambiguous": False},
            {"variant": "retinold", "keyword": "retinol", "rule": "basic_edit", "weight": 0.7, "is_ambiguous": True},
        ]

        table = build_lookup_table(rows)
        self.assertIn("etrogen", table)
        self.assertEqual(lookup_variant(table, "etrogen")[0]["keyword"], "estrogen")


if __name__ == "__main__":
    unittest.main()
