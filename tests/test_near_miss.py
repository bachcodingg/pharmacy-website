import unittest

from crawl_longchau import generate_near_misses


class NearMissStage4Tests(unittest.TestCase):
    def test_generates_typo_variants_and_flags_ambiguity(self):
        keywords = [
            {"keyword": "estrogen", "type": "ingredient", "popularity": 10},
            {"keyword": "retinol", "type": "ingredient", "popularity": 8},
        ]

        rows = generate_near_misses(keywords)
        self.assertTrue(any(r["variant"] == "etrogen" for r in rows))
        self.assertTrue(any(r["keyword"] == "estrogen" and r["is_ambiguous"] is False for r in rows))


if __name__ == "__main__":
    unittest.main()
