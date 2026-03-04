REFERENCE_DATETIME = "2026-03-04T12:00:00"


def _range(expression: str, start: str, end: str) -> dict:
    return {
        "kind": "TIME_RANGE",
        "expression": expression,
        "start": start,
        "end": end,
    }


def _point(expression: str, point: str) -> dict:
    return {
        "kind": "TIME_POINT",
        "expression": expression,
        "point": point,
    }


GOLDEN_TIME_SAMPLES = [
    # ko
    {"lang": "ko", "text": "어제", "expected": [_range("어제", "20260303000000", "20260304000000")]},
    {"lang": "ko", "text": "오늘", "expected": [_range("오늘", "20260304000000", "20260305000000")]},
    {
        "lang": "ko",
        "text": "어제,오늘",
        "expected": [
            _range("어제", "20260303000000", "20260304000000"),
            _range("오늘", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "ko", "text": "어제 이후로", "expected": [_range("어제 이후로", "20260303000000", "20260305000000")]},
    {"lang": "ko", "text": "최근 7일", "expected": [_range("최근 7일", "20260226000000", "20260305000000")]},
    {
        "lang": "ko",
        "text": "2026년 3월 4일",
        "expected": [_range("2026년 3월 4일", "20260304000000", "20260305000000")],
    },
    {"lang": "ko", "text": "내일 오전 10시", "expected": [_point("내일 오전 10시", "20260305100000")]},
    # en
    {"lang": "en", "text": "yesterday", "expected": [_range("yesterday", "20260303000000", "20260304000000")]},
    {"lang": "en", "text": "today", "expected": [_range("today", "20260304000000", "20260305000000")]},
    {
        "lang": "en",
        "text": "yesterday,today",
        "expected": [
            _range("yesterday", "20260303000000", "20260304000000"),
            _range("today", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "en", "text": "since yesterday", "expected": [_range("since yesterday", "20260303000000", "20260305000000")]},
    {"lang": "en", "text": "recent 7 days", "expected": [_range("recent 7 days", "20260226000000", "20260305000000")]},
    {"lang": "en", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "en", "text": "tomorrow 10am", "expected": [_point("tomorrow 10am", "20260305100000")]},
    # ja
    {"lang": "ja", "text": "昨日", "expected": [_range("昨日", "20260303000000", "20260304000000")]},
    {"lang": "ja", "text": "今日", "expected": [_range("今日", "20260304000000", "20260305000000")]},
    {
        "lang": "ja",
        "text": "昨日、今日",
        "expected": [
            _range("昨日", "20260303000000", "20260304000000"),
            _range("今日", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "ja", "text": "昨日以降", "expected": [_range("昨日以降", "20260303000000", "20260305000000")]},
    {"lang": "ja", "text": "直近7日", "expected": [_range("直近7日", "20260226000000", "20260305000000")]},
    {"lang": "ja", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "ja", "text": "明日午前10時", "expected": [_point("明日午前10時", "20260305100000")]},
    # zh
    {"lang": "zh", "text": "昨天", "expected": [_range("昨天", "20260303000000", "20260304000000")]},
    {"lang": "zh", "text": "今天", "expected": [_range("今天", "20260304000000", "20260305000000")]},
    {
        "lang": "zh",
        "text": "昨天，今天",
        "expected": [
            _range("昨天", "20260303000000", "20260304000000"),
            _range("今天", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "zh", "text": "昨天以后", "expected": [_range("昨天以后", "20260303000000", "20260305000000")]},
    {"lang": "zh", "text": "最近7天", "expected": [_range("最近7天", "20260226000000", "20260305000000")]},
    {"lang": "zh", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "zh", "text": "明天上午10点", "expected": [_point("明天上午10点", "20260305100000")]},
    # fr
    {"lang": "fr", "text": "hier", "expected": [_range("hier", "20260303000000", "20260304000000")]},
    {"lang": "fr", "text": "aujourd'hui", "expected": [_range("aujourd'hui", "20260304000000", "20260305000000")]},
    {
        "lang": "fr",
        "text": "hier,aujourd'hui",
        "expected": [
            _range("hier", "20260303000000", "20260304000000"),
            _range("aujourd'hui", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "fr", "text": "depuis hier", "expected": [_range("depuis hier", "20260303000000", "20260305000000")]},
    {"lang": "fr", "text": "derniers 7 jours", "expected": [_range("derniers 7 jours", "20260226000000", "20260305000000")]},
    {"lang": "fr", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "fr", "text": "demain 10h", "expected": [_point("demain 10h", "20260305100000")]},
    # de
    {"lang": "de", "text": "gestern", "expected": [_range("gestern", "20260303000000", "20260304000000")]},
    {"lang": "de", "text": "heute", "expected": [_range("heute", "20260304000000", "20260305000000")]},
    {
        "lang": "de",
        "text": "gestern,heute",
        "expected": [
            _range("gestern", "20260303000000", "20260304000000"),
            _range("heute", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "de", "text": "seit gestern", "expected": [_range("seit gestern", "20260303000000", "20260305000000")]},
    {"lang": "de", "text": "letzten 7 tage", "expected": [_range("letzten 7 tage", "20260226000000", "20260305000000")]},
    {"lang": "de", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "de", "text": "morgen 10 uhr", "expected": [_point("morgen 10 uhr", "20260305100000")]},
    # ar
    {"lang": "ar", "text": "أمس", "expected": [_range("أمس", "20260303000000", "20260304000000")]},
    {"lang": "ar", "text": "اليوم", "expected": [_range("اليوم", "20260304000000", "20260305000000")]},
    {
        "lang": "ar",
        "text": "أمس،اليوم",
        "expected": [
            _range("أمس", "20260303000000", "20260304000000"),
            _range("اليوم", "20260304000000", "20260305000000"),
        ],
    },
    {"lang": "ar", "text": "منذ أمس", "expected": [_range("منذ أمس", "20260303000000", "20260305000000")]},
    {"lang": "ar", "text": "آخر 7 أيام", "expected": [_range("آخر 7 أيام", "20260226000000", "20260305000000")]},
    {"lang": "ar", "text": "2026-03-04", "expected": [_range("2026-03-04", "20260304000000", "20260305000000")]},
    {"lang": "ar", "text": "غدًا 10", "expected": [_point("غدًا 10", "20260305100000")]},
]