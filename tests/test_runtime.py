import unittest

from crawl_longchau import resolve_query


class RuntimeStage6Tests(unittest.TestCase):
    def test_resolves_simple_misspelling(self):
        table = {
            "etrogen": [
                {"variant": "etrogen", "keyword": "estrogen", "rule": "basic_edit", "weight": 0.8, "is_ambiguous": False}
            ]
        }
        result = resolve_query("etrogen", table)
        self.assertEqual(result["decision"], "autocorrect")
        self.assertEqual(result["suggestion"], "estrogen")

    def test_returns_disambiguation_for_ambiguous_match(self):
        table = {
            "retinold": [
                {"variant": "retinold", "keyword": "retinol", "rule": "basic_edit", "weight": 0.7, "is_ambiguous": True}
            ]
        }
        result = resolve_query("retinold", table)
        self.assertEqual(result["decision"], "disambiguate")
        self.assertEqual(result["candidates"][0]["keyword"], "retinol")


if __name__ == "__main__":
    unittest.main()
