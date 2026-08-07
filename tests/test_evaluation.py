import unittest

from crawl_longchau import evaluate_corrections


class EvaluationStage8Tests(unittest.TestCase):
    def test_reports_precision_and_recall(self):
        gold = [{"query": "etrogen", "target": "estrogen"}]
        predictions = [{"query": "etrogen", "prediction": "estrogen"}]

        metrics = evaluate_corrections(gold, predictions)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
