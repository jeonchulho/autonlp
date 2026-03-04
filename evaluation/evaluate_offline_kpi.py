from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp import ConditionExtractorPipeline


TIME_HINTS = {
    "ko": ["어제", "오늘", "내일", "최근", "지난", "이날", "당일"],
    "en": ["yesterday", "today", "tomorrow", "last", "recent", "tonight"],
    "ja": ["昨日", "今日", "明日", "直近", "当日"],
    "zh": ["昨天", "今天", "明天", "最近", "当日"],
    "fr": ["hier", "aujourd", "demain", "dernier"],
    "de": ["gestern", "heute", "morgen", "letzten"],
    "ar": ["أمس", "اليوم", "غد", "آخر"],
}

RECIPIENT_HINTS = {
    "ko": ["에게", "한테", "께"],
    "en": [" to ", " for "],
    "ja": ["に", "宛て", "向け"],
    "zh": ["给", "向", "对"],
    "fr": [" à ", " pour "],
    "de": [" an ", " für "],
    "ar": ["إلى", "لـ"],
}


@dataclass
class CaseResult:
    lang: str
    domain: str
    length: str
    noise: str
    has_expected_predicates: bool
    has_expected_objects: bool
    predicate_match: bool
    object_match: bool
    has_time_hint: bool
    has_recipient_hint: bool
    time_covered: bool
    recipient_covered: bool
    runtime_error: bool


def _contains_hint(text: str, lang: str, hint_map: dict[str, list[str]]) -> bool:
    lowered = text.lower()
    for hint in hint_map.get(lang, []):
        if hint.lower() in lowered:
            return True
    return False


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _safe_div(num: int, den: int) -> float:
    return 0.0 if den == 0 else num / den


def _compare(metric: float, op: str, target: float) -> bool:
    if op == ">=":
        return metric >= target
    if op == "<=":
        return metric <= target
    raise ValueError(f"Unsupported op: {op}")


def _predicates(result: dict) -> list[str]:
    return [item.get("predicate") for item in result.get("sentences", []) if item.get("predicate")]


def _objects(result: dict) -> list[str]:
    return [(item.get("object") or "").strip() for item in result.get("sentences", []) if item.get("predicate")]


def _has_time_condition(result: dict) -> bool:
    for sentence in result.get("sentences", []):
        for condition in sentence.get("conditions", []):
            if condition.get("label") == "TIME":
                return True
    return False


def _has_recipient(result: dict) -> bool:
    for sentence in result.get("sentences", []):
        recipients = sentence.get("recipients") or []
        if recipients:
            return True
        for condition in sentence.get("conditions", []):
            if condition.get("label") == "RECIPIENT":
                return True
    return False


def _evaluate_row(row: dict, pipeline: ConditionExtractorPipeline) -> CaseResult:
    lang = (row.get("lang") or "ko").lower()
    domain = row.get("domain") or "unknown"
    length = row.get("length") or "unknown"
    noise = row.get("noise") or "unknown"
    text = row.get("text") or ""

    expected_predicates = row.get("expected_predicates") if isinstance(row.get("expected_predicates"), list) else []
    expected_objects = row.get("expected_objects") if isinstance(row.get("expected_objects"), list) else []

    has_expected_predicates = len(expected_predicates) > 0
    has_expected_objects = len(expected_objects) > 0

    has_time_hint = _contains_hint(text, lang, TIME_HINTS)
    has_recipient_hint = _contains_hint(text, lang, RECIPIENT_HINTS)

    try:
        result = pipeline.extract(text).to_dict()
    except Exception:
        return CaseResult(
            lang=lang,
            domain=domain,
            length=length,
            noise=noise,
            has_expected_predicates=has_expected_predicates,
            has_expected_objects=has_expected_objects,
            predicate_match=False,
            object_match=False,
            has_time_hint=has_time_hint,
            has_recipient_hint=has_recipient_hint,
            time_covered=False,
            recipient_covered=False,
            runtime_error=True,
        )

    predicted_predicates = _predicates(result)
    predicted_objects = _objects(result)

    predicate_match = (predicted_predicates == expected_predicates) if has_expected_predicates else False
    object_match = (predicted_objects == expected_objects) if has_expected_objects else False

    return CaseResult(
        lang=lang,
        domain=domain,
        length=length,
        noise=noise,
        has_expected_predicates=has_expected_predicates,
        has_expected_objects=has_expected_objects,
        predicate_match=predicate_match,
        object_match=object_match,
        has_time_hint=has_time_hint,
        has_recipient_hint=has_recipient_hint,
        time_covered=_has_time_condition(result),
        recipient_covered=_has_recipient(result),
        runtime_error=False,
    )


def _aggregate(results: list[CaseResult]) -> dict[str, float]:
    pred_den = sum(1 for r in results if r.has_expected_predicates)
    obj_den = sum(1 for r in results if r.has_expected_objects)
    time_den = sum(1 for r in results if r.has_time_hint)
    recipient_den = sum(1 for r in results if r.has_recipient_hint)
    total_den = len(results)

    return {
        "predicate_seq_acc": _safe_div(sum(1 for r in results if r.has_expected_predicates and r.predicate_match), pred_den),
        "object_seq_acc": _safe_div(sum(1 for r in results if r.has_expected_objects and r.object_match), obj_den),
        "time_hint_coverage": _safe_div(sum(1 for r in results if r.has_time_hint and r.time_covered), time_den),
        "recipient_hint_coverage": _safe_div(sum(1 for r in results if r.has_recipient_hint and r.recipient_covered), recipient_den),
        "runtime_error_rate": _safe_div(sum(1 for r in results if r.runtime_error), total_den),
        "pred_den": float(pred_den),
        "obj_den": float(obj_den),
        "time_den": float(time_den),
        "recipient_den": float(recipient_den),
        "total_den": float(total_den),
    }


def _metric_denominator(metric: str, agg: dict[str, float]) -> float:
    if metric == "predicate_seq_acc":
        return agg.get("pred_den", 0.0)
    if metric == "object_seq_acc":
        return agg.get("obj_den", 0.0)
    if metric == "time_hint_coverage":
        return agg.get("time_den", 0.0)
    if metric == "recipient_hint_coverage":
        return agg.get("recipient_den", 0.0)
    if metric == "runtime_error_rate":
        return agg.get("total_den", 0.0)
    return agg.get("total_den", 0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/offline_eval_dataset.v1.jsonl", help="offline evaluation dataset jsonl")
    parser.add_argument("--kpi", default="evaluation/kpi_targets.v1.json", help="kpi target json")
    parser.add_argument("--ref-datetime", default="2026-03-04T12:00:00+09:00", help="reference datetime")
    parser.add_argument("--langs", default="", help="comma-separated language filter")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    kpi_path = Path(args.kpi)

    rows = _load_jsonl(dataset_path)
    lang_filter = {item.strip().lower() for item in args.langs.split(",") if item.strip()} if args.langs else None
    if lang_filter is not None:
        rows = [row for row in rows if (row.get("lang") or "ko").lower() in lang_filter]

    with kpi_path.open("r", encoding="utf-8") as file:
        targets = json.load(file)

    reference_dt = datetime.fromisoformat(args.ref_datetime)
    rows = sorted(rows, key=lambda row: (row.get("lang") or "ko", row.get("case_id") or ""))

    results: list[CaseResult] = []
    current_lang: str | None = None
    current_pipeline: ConditionExtractorPipeline | None = None
    for row in rows:
        lang = (row.get("lang") or "ko").lower()
        if current_lang != lang or current_pipeline is None:
            current_lang = lang
            current_pipeline = ConditionExtractorPipeline(lang=lang, reference_datetime=reference_dt)
        results.append(_evaluate_row(row, current_pipeline))
    overall = _aggregate(results)

    print("== Offline KPI Evaluation ==")
    print(f"Dataset: {dataset_path}")
    print(f"Cases: {len(results)}")
    print()

    failed = False

    print("[Overall]")
    for metric, rule in targets.get("overall", {}).items():
        value = overall.get(metric, 0.0)
        denominator = _metric_denominator(metric, overall)
        if denominator == 0:
            print(f"- SKIP {metric}: denominator=0")
            continue
        op = rule["op"]
        target = float(rule["value"])
        ok = _compare(value, op, target)
        status = "PASS" if ok else "FAIL"
        print(f"- {status} {metric}: {value:.3f} {op} {target:.3f}")
        if not ok:
            failed = True

    print()
    print("[Slices]")
    slice_cfg = targets.get("slice", {})
    min_cases = int(slice_cfg.get("min_cases", 2))

    for group_key in ["lang", "domain", "length", "noise"]:
        grouped: dict[str, list[CaseResult]] = defaultdict(list)
        for result in results:
            grouped[getattr(result, group_key)].append(result)

        print(f"- by {group_key}")
        for value, subset in sorted(grouped.items(), key=lambda item: item[0]):
            if len(subset) < min_cases:
                print(f"  - SKIP {value}: cases={len(subset)} < min_cases={min_cases}")
                continue
            agg = _aggregate(subset)
            line = f"  - {value}: cases={len(subset)}"
            local_ok = True
            for metric, rule in slice_cfg.items():
                if metric == "min_cases":
                    continue
                metric_value = agg.get(metric, 0.0)
                denominator = _metric_denominator(metric, agg)
                if denominator == 0:
                    line += f", {metric}=N/A (SKIP)"
                    continue
                op = rule["op"]
                target = float(rule["value"])
                ok = _compare(metric_value, op, target)
                local_ok = local_ok and ok
                line += f", {metric}={metric_value:.3f} ({'OK' if ok else 'NG'})"
            print(line)
            if not local_ok:
                failed = True

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
