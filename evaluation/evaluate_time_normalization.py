from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp.time_normalizer import normalize_time_expression
from evaluation.golden_time_samples import GOLDEN_TIME_SAMPLES, REFERENCE_DATETIME


def _to_signature(item: dict) -> str:
    kind = item.get("kind", "")
    expression = item.get("expression", "")
    start = item.get("start", "")
    end = item.get("end", "")
    point = item.get("point", "")
    return f"{kind}|{expression}|{start}|{end}|{point}"


def _safe_div(num: int, den: int) -> float:
    if den == 0:
        return 0.0
    return num / den


def main() -> None:
    reference_dt = datetime.fromisoformat(REFERENCE_DATETIME)

    stats = defaultdict(lambda: {"tp": 0, "pred": 0, "gold": 0, "samples": 0, "exact": 0})

    for sample in GOLDEN_TIME_SAMPLES:
        lang = sample["lang"]
        text = sample["text"]
        expected = sample["expected"]

        predicted = [
            item.to_dict()
            for item in normalize_time_expression(
                text=text,
                lang=lang,
                reference_dt=reference_dt,
            )
        ]

        pred_set = {_to_signature(x) for x in predicted}
        gold_set = {_to_signature(x) for x in expected}

        tp = len(pred_set & gold_set)

        stats[lang]["tp"] += tp
        stats[lang]["pred"] += len(pred_set)
        stats[lang]["gold"] += len(gold_set)
        stats[lang]["samples"] += 1
        stats[lang]["exact"] += int(pred_set == gold_set)

    langs = sorted(stats.keys())
    total = {"tp": 0, "pred": 0, "gold": 0, "samples": 0, "exact": 0}
    for lang in langs:
        for key in total:
            total[key] += stats[lang][key]

    print("== Time Normalization Evaluation ==")
    print(f"Reference datetime: {REFERENCE_DATETIME}")
    print("Metric uses half-open intervals [start, end)")
    print()
    print("lang\tsamples\texact\tprecision\trecall\tf1")

    for lang in langs:
        precision = _safe_div(stats[lang]["tp"], stats[lang]["pred"])
        recall = _safe_div(stats[lang]["tp"], stats[lang]["gold"])
        f1 = _safe_div(2 * precision * recall, precision + recall) if precision + recall > 0 else 0.0
        print(
            f"{lang}\t{stats[lang]['samples']}\t{stats[lang]['exact']}\t"
            f"{precision:.3f}\t{recall:.3f}\t{f1:.3f}"
        )

    total_precision = _safe_div(total["tp"], total["pred"])
    total_recall = _safe_div(total["tp"], total["gold"])
    total_f1 = _safe_div(2 * total_precision * total_recall, total_precision + total_recall) if total_precision + total_recall > 0 else 0.0
    print()
    print(
        f"TOTAL\t{total['samples']}\t{total['exact']}\t"
        f"{total_precision:.3f}\t{total_recall:.3f}\t{total_f1:.3f}"
    )


if __name__ == "__main__":
    main()