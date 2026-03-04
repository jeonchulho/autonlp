from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonlp.time_normalizer import normalize_time_expression


def _to_key(item: dict) -> tuple:
    return (
        item.get("kind"),
        item.get("expression"),
        item.get("start"),
        item.get("end"),
        item.get("point"),
    )


def main() -> None:
    cases = [
        {
            "lang": "ko",
            "text": "오늘",
            "reference": "2026-03-04T12:00:00+09:00",
            "expected": [
                {
                    "kind": "TIME_RANGE",
                    "expression": "오늘",
                    "start": "20260303150000",
                    "end": "20260304150000",
                }
            ],
        },
        {
            "lang": "ko",
            "text": "내일 오전 10시",
            "reference": "2026-03-04T12:00:00+09:00",
            "expected": [
                {
                    "kind": "TIME_POINT",
                    "expression": "내일 오전 10시",
                    "point": "20260305010000",
                },
                {
                    "kind": "TIME_RANGE",
                    "expression": "내일",
                    "start": "20260304150000",
                    "end": "20260305150000",
                },
            ],
        },
        {
            "lang": "en",
            "text": "today",
            "reference": "2026-03-04T00:30:00-05:00",
            "expected": [
                {
                    "kind": "TIME_RANGE",
                    "expression": "today",
                    "start": "20260304050000",
                    "end": "20260305050000",
                }
            ],
        },
    ]

    print("== Timezone Conversion Evaluation ==")
    passed = 0
    for index, case in enumerate(cases, start=1):
        ref = datetime.fromisoformat(case["reference"])
        predicted = [x.to_dict() for x in normalize_time_expression(case["text"], case["lang"], ref)]
        pred_set = {_to_key(x) for x in predicted}
        exp_set = {_to_key(x) for x in case["expected"]}

        ok = pred_set == exp_set
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] case#{index} lang={case['lang']} text={case['text']} ref={case['reference']}")
        if not ok:
            print(f"  expected={case['expected']}")
            print(f"  predicted={predicted}")
        else:
            passed += 1

    print(f"Result: {passed}/{len(cases)} passed")
    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()