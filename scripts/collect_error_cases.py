from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp import ConditionExtractorPipeline


@dataclass
class CaseIssue:
    index: int
    lang: str
    text: str
    issues: list[str]


TIME_HINTS = {
    "ko": ["어제", "오늘", "내일", "최근", "지난", "이날"],
    "en": ["yesterday", "today", "tomorrow", "last", "recent"],
    "ja": ["昨日", "今日", "明日", "直近"],
    "zh": ["昨天", "今天", "明天", "最近"],
    "fr": ["hier", "aujourd", "demain", "dernier"],
    "de": ["gestern", "heute", "morgen", "letzten"],
    "ar": ["أمس", "اليوم", "غد", "آخر"],
}

RECIPIENT_HINTS = {
    "ko": ["에게", "한테", "께"],
    "en": [" to ", " for "],
    "ja": ["に", "宛て"],
    "zh": ["给", "向", "对"],
    "fr": [" à ", " pour "],
    "de": [" an ", " für "],
    "ar": ["إلى", "لـ"],
}


def _contains_hint(text: str, lang: str, hint_map: dict[str, list[str]]) -> bool:
    hints = hint_map.get(lang, [])
    lowered = text.lower()
    for hint in hints:
        if hint.lower() in lowered:
            return True
    return False


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _predicates(result: dict) -> list[str]:
    return [item.get("predicate") for item in result.get("sentences", []) if item.get("predicate")]


def _objects(result: dict) -> list[str]:
    return [item.get("object") for item in result.get("sentences", []) if item.get("predicate")]


def _condition_labels(result: dict) -> set[str]:
    labels = set()
    for sentence in result.get("sentences", []):
        for condition in sentence.get("conditions", []):
            label = condition.get("label")
            if label:
                labels.add(label)
    return labels


def _has_recipients(result: dict) -> bool:
    for sentence in result.get("sentences", []):
        if sentence.get("recipients"):
            return True
    return False


def evaluate_case(index: int, row: dict, reference_dt: datetime | None) -> CaseIssue:
    lang = (row.get("lang") or "ko").lower()
    text = row.get("text") or ""
    config = row.get("config") if isinstance(row.get("config"), dict) else {}

    pipeline = ConditionExtractorPipeline(lang=lang, reference_datetime=reference_dt, config=config)
    result = pipeline.extract(text).to_dict()

    issues: list[str] = []

    preds = _predicates(result)
    objs = _objects(result)
    labels = _condition_labels(result)

    if not preds:
        issues.append("no_predicate")

    if preds and all((obj is None or str(obj).strip() == "") for obj in objs):
        issues.append("all_objects_empty")

    if _contains_hint(text, lang, TIME_HINTS) and "TIME" not in labels:
        issues.append("time_hint_but_no_time_condition")

    if _contains_hint(text, lang, RECIPIENT_HINTS) and not _has_recipients(result):
        issues.append("recipient_hint_but_no_recipient")

    expected_predicates = row.get("expected_predicates")
    if isinstance(expected_predicates, list) and expected_predicates:
        if preds != expected_predicates:
            issues.append("predicate_sequence_mismatch")

    expected_objects = row.get("expected_objects")
    if isinstance(expected_objects, list) and expected_objects:
        if objs != expected_objects:
            issues.append("object_sequence_mismatch")

    return CaseIssue(index=index, lang=lang, text=text, issues=issues)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="path to jsonl input cases")
    parser.add_argument("--output", default="evaluation/error_case_report.jsonl", help="path to output report jsonl")
    parser.add_argument("--ref-datetime", default="", help="ISO datetime for deterministic normalization")
    parser.add_argument("--langs", default="", help="comma-separated languages to process (e.g. ko,en)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference_dt = datetime.fromisoformat(args.ref_datetime) if args.ref_datetime else None
    rows = _load_jsonl(input_path)
    lang_filter = {item.strip().lower() for item in args.langs.split(",") if item.strip()} if args.langs else None

    if lang_filter is not None:
        rows = [row for row in rows if (row.get("lang") or "ko").lower() in lang_filter]

    issues_total = 0
    with output_path.open("w", encoding="utf-8") as output:
        for idx, row in enumerate(rows, start=1):
            lang = (row.get("lang") or "ko").lower()
            print(f"[collect] case={idx} lang={lang}", flush=True)
            try:
                case_issue = evaluate_case(idx, row, reference_dt)
            except Exception as exc:
                case_issue = CaseIssue(index=idx, lang=lang, text=row.get("text") or "", issues=[f"runtime_error:{exc}"])
            if case_issue.issues:
                issues_total += 1
            output.write(
                json.dumps(
                    {
                        "index": case_issue.index,
                        "lang": case_issue.lang,
                        "text": case_issue.text,
                        "issues": case_issue.issues,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"Input cases: {len(rows)}")
    print(f"Cases with issues: {issues_total}")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
