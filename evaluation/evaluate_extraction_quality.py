from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp import ConditionExtractorPipeline
from evaluation.golden_extraction_samples import GOLDEN_EXTRACTION_SAMPLES, REFERENCE_DATETIME


def _safe_div(num: int, den: int) -> float:
    return 0.0 if den == 0 else num / den


def _condition_label_set(sentence: dict) -> set[str]:
    return {condition.get("label") for condition in sentence.get("conditions", []) if condition.get("label")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", type=str, default="", help="comma-separated language codes")
    args = parser.parse_args()

    lang_filter = {item.strip() for item in args.langs.split(",") if item.strip()} if args.langs else None
    reference_dt = datetime.fromisoformat(REFERENCE_DATETIME)

    stats = defaultdict(lambda: {
        "samples": 0,
        "sent_total": 0,
        "pred_ok": 0,
        "subj_ok": 0,
        "obj_ok": 0,
        "cond_ok": 0,
        "all_ok": 0,
    })
    failures: list[tuple[str, str]] = []
    pipelines: dict[str, ConditionExtractorPipeline] = {}

    for sample in GOLDEN_EXTRACTION_SAMPLES:
        lang = sample["lang"]
        if lang_filter is not None and lang not in lang_filter:
            continue

        text = sample["text"]
        expected = sample["expected"]

        try:
            pipeline = pipelines.get(lang)
            if pipeline is None:
                pipeline = ConditionExtractorPipeline(lang=lang, reference_datetime=reference_dt)
                pipelines[lang] = pipeline
            result = pipeline.extract(text).to_dict()
        except Exception as exc:
            failures.append((lang, str(exc)))
            continue

        predicted_sentences = result.get("sentences", [])
        compare_count = min(len(expected), len(predicted_sentences))

        stats[lang]["samples"] += 1
        stats[lang]["sent_total"] += len(expected)

        for idx in range(compare_count):
            exp = expected[idx]
            pred = predicted_sentences[idx]

            pred_ok = (pred.get("predicate") == exp.get("predicate"))
            subj_ok = (pred.get("subject") == exp.get("subject"))
            obj_ok = (pred.get("object") == exp.get("object"))
            cond_ok = (_condition_label_set(pred) == set(exp.get("condition_labels", [])))

            stats[lang]["pred_ok"] += int(pred_ok)
            stats[lang]["subj_ok"] += int(subj_ok)
            stats[lang]["obj_ok"] += int(obj_ok)
            stats[lang]["cond_ok"] += int(cond_ok)
            stats[lang]["all_ok"] += int(pred_ok and subj_ok and obj_ok and cond_ok)

        missing = len(expected) - compare_count
        if missing > 0:
            pass

    langs = sorted(stats.keys())
    total = {k: 0 for k in ["samples", "sent_total", "pred_ok", "subj_ok", "obj_ok", "cond_ok", "all_ok"]}
    for lang in langs:
        for key in total:
            total[key] += stats[lang][key]

    print("== Extraction Quality Evaluation ==")
    print(f"Reference datetime: {REFERENCE_DATETIME}")
    print()
    print("lang\tsamples\tsents\tpred_acc\tsubj_acc\tobj_acc\tcond_acc\tall_acc")

    for lang in langs:
        sent_total = stats[lang]["sent_total"]
        pred_acc = _safe_div(stats[lang]["pred_ok"], sent_total)
        subj_acc = _safe_div(stats[lang]["subj_ok"], sent_total)
        obj_acc = _safe_div(stats[lang]["obj_ok"], sent_total)
        cond_acc = _safe_div(stats[lang]["cond_ok"], sent_total)
        all_acc = _safe_div(stats[lang]["all_ok"], sent_total)

        print(
            f"{lang}\t{stats[lang]['samples']}\t{sent_total}\t"
            f"{pred_acc:.3f}\t{subj_acc:.3f}\t{obj_acc:.3f}\t{cond_acc:.3f}\t{all_acc:.3f}"
        )

    if total["sent_total"] > 0:
        print()
        print(
            f"TOTAL\t{total['samples']}\t{total['sent_total']}\t"
            f"{_safe_div(total['pred_ok'], total['sent_total']):.3f}\t"
            f"{_safe_div(total['subj_ok'], total['sent_total']):.3f}\t"
            f"{_safe_div(total['obj_ok'], total['sent_total']):.3f}\t"
            f"{_safe_div(total['cond_ok'], total['sent_total']):.3f}\t"
            f"{_safe_div(total['all_ok'], total['sent_total']):.3f}"
        )

    if failures:
        print()
        print("Failures:")
        for lang, message in failures:
            print(f"- {lang}: {message}")


if __name__ == "__main__":
    main()
