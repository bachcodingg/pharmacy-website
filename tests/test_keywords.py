import unittest

from crawl_longchau import extract_keywords


class KeywordExtractionStage3Tests(unittest.TestCase):
    def test_extracts_phrases_from_product_text(self):
        products = [{
            "webName": "Vitamin C Plus",
            "shortDescription": "supplement for immune support",
            "ingredients": [{"name": "vitamin c"}],
            "normalizedWebName": "vitamin c plus",
            "normalizedShortDescription": "supplement for immune support",
            "normalizedIngredients": "vitamin c",
        }]

        rows = extract_keywords(products, max_keywords=20)
        self.assertTrue(any(r["keyword"] == "vitamin c" for r in rows))
        self.assertTrue(any(r["keyword"] == "immune support" for r in rows))
        self.assertTrue(any(r["type"] == "ingredient" for r in rows if r["keyword"] == "vitamin c"))


if __name__ == "__main__":
    unittest.main()
