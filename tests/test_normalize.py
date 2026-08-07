import unittest

from crawl_longchau import normalize, accent_fold


class NormalizeStage2Tests(unittest.TestCase):
    def test_normalize_lowercases_and_removes_punctuation(self):
        self.assertEqual(normalize("Cà phê 500mg, Vitamin C!"), "cà phê 500mg vitamin c")

    def test_normalize_keeps_brand_names_intact(self):
        self.assertEqual(normalize("NutriGrow & LactoBiomin"), "nutrigrow lactobiomin")

    def test_accent_fold_is_available_for_lookup(self):
        self.assertEqual(accent_fold("Kẽm và Calcium"), "kem va calcium")


if __name__ == "__main__":
    unittest.main()
