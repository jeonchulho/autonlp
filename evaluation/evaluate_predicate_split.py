from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp import ConditionExtractorPipeline
from evaluation.golden_predicate_samples import GOLDEN_PREDICATE_SAMPLES, REFERENCE_DATETIME


def _safe_div(num: int, den: int) -> float:
    if den == 0:
        return 0.0
    return num / den


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", type=str, default="", help="comma-separated language codes (e.g. ko,en,ja)")
    args = parser.parse_args()

    lang_filter = {item.strip() for item in args.langs.split(",") if item.strip()} if args.langs else None

    reference_dt = datetime.fromisoformat(REFERENCE_DATETIME)
    stats = defaultdict(
        lambda: {
            "samples": 0,
            "exact": 0,
            "tp": 0,
            "pred": 0,
            "gold": 0,
            "obj_exact": 0,
            "obj_tp": 0,
            "obj_pred": 0,
            "obj_gold": 0,
        }
    )
    failures: list[tuple[str, str]] = []

    for sample in GOLDEN_PREDICATE_SAMPLES:
        lang = sample["lang"]
        if lang_filter is not None and lang not in lang_filter:
            continue
        text = sample["text"]
        expected = sample["expected_predicates"]
        expected_objects = sample.get("expected_objects", [])

        try:
            pipeline = ConditionExtractorPipeline(lang=lang, reference_datetime=reference_dt)
            result = pipeline.extract(text)
            predicted = [sentence.predicate for sentence in result.sentences if sentence.predicate]
            predicted_objects = [(sentence.object or "").strip() for sentence in result.sentences if sentence.predicate]
        except Exception as exc:
            failures.append((lang, str(exc)))
            continue

        pred_set = set(predicted)
        gold_set = set(expected)

        tp = len(pred_set & gold_set)
        stats[lang]["samples"] += 1
        stats[lang]["exact"] += int(predicted == expected)
        stats[lang]["tp"] += tp
        stats[lang]["pred"] += len(pred_set)
        stats[lang]["gold"] += len(gold_set)

        if expected_objects:
            pred_obj_set = {value for value in predicted_objects if value}
            gold_obj_set = {value for value in expected_objects if value}
            obj_tp = len(pred_obj_set & gold_obj_set)
            stats[lang]["obj_exact"] += int(predicted_objects == expected_objects)
            stats[lang]["obj_tp"] += obj_tp
            stats[lang]["obj_pred"] += len(pred_obj_set)
            stats[lang]["obj_gold"] += len(gold_obj_set)

    langs = sorted(stats.keys())
    total = {
        "samples": 0,
        "exact": 0,
        "tp": 0,
        "pred": 0,
        "gold": 0,
        "obj_exact": 0,
        "obj_tp": 0,
        "obj_pred": 0,
        "obj_gold": 0,
    }
    for lang in langs:
        for key in total:
            total[key] += stats[lang][key]

    print("== Predicate Split Evaluation ==")
    print(f"Reference datetime: {REFERENCE_DATETIME}")
    print()
    print("lang\tsamples\texact\tprecision\trecall\tf1\tobj_exact\tobj_p\tobj_r\tobj_f1")

    for lang in langs:
        precision = _safe_div(stats[lang]["tp"], stats[lang]["pred"])
        recall = _safe_div(stats[lang]["tp"], stats[lang]["gold"])
        f1 = _safe_div(2 * precision * recall, precision + recall) if precision + recall > 0 else 0.0
        obj_precision = _safe_div(stats[lang]["obj_tp"], stats[lang]["obj_pred"])
        obj_recall = _safe_div(stats[lang]["obj_tp"], stats[lang]["obj_gold"])
        obj_f1 = _safe_div(2 * obj_precision * obj_recall, obj_precision + obj_recall) if obj_precision + obj_recall > 0 else 0.0
        print(
            f"{lang}\t{stats[lang]['samples']}\t{stats[lang]['exact']}\t"
            f"{precision:.3f}\t{recall:.3f}\t{f1:.3f}\t"
            f"{stats[lang]['obj_exact']}\t{obj_precision:.3f}\t{obj_recall:.3f}\t{obj_f1:.3f}"
        )

    total_precision = _safe_div(total["tp"], total["pred"])
    total_recall = _safe_div(total["tp"], total["gold"])
    total_f1 = _safe_div(2 * total_precision * total_recall, total_precision + total_recall) if total_precision + total_recall > 0 else 0.0
    total_obj_precision = _safe_div(total["obj_tp"], total["obj_pred"])
    total_obj_recall = _safe_div(total["obj_tp"], total["obj_gold"])
    total_obj_f1 = _safe_div(2 * total_obj_precision * total_obj_recall, total_obj_precision + total_obj_recall) if total_obj_precision + total_obj_recall > 0 else 0.0
    print()
    print(
        f"TOTAL\t{total['samples']}\t{total['exact']}\t"
        f"{total_precision:.3f}\t{total_recall:.3f}\t{total_f1:.3f}\t"
        f"{total['obj_exact']}\t{total_obj_precision:.3f}\t{total_obj_recall:.3f}\t{total_obj_f1:.3f}"
    )

    if failures:
        print()
        print("Failures:")
        for lang, message in failures:
            print(f"- {lang}: {message}")


if __name__ == "__main__":
    main()
