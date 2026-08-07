"""Run all Step 11 evaluation checks and print a report.

Metrics, in the guide's priority order (precision outranks recall - that's
what makes this a pharmacy system rather than generic e-commerce search):
  1. Correction precision   - needs session-linked query logs (not yet captured, see query_log.py)
  2. Zero-result rate        - from logs/queries.jsonl, once the app has real traffic
  3. Recall on known typos   - held-out rule-group accuracy + human-typed set
  4. Latency p95              - measured directly, no data collection needed
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import held_out
import human_typed
import latency
import query_log


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report = {
        "1_correction_precision_and_2_zero_result_rate": query_log.run(),
        "3a_recall_held_out_rules": held_out.run(),
        "3b_recall_human_typed": human_typed.run(),
        "4_latency": latency.run(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
