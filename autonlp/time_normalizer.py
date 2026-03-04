from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class NormalizedTemporal:
    kind: str
    expression: str
    start: str | None = None
    end: str | None = None
    point: str | None = None
    timezone_assumption: str | None = None
    output_timezone: str = "UTC"

    def to_dict(self) -> dict:
        data = {
            "kind": self.kind,
            "expression": self.expression,
        }
        if self.start is not None:
            data["start"] = self.start
        if self.end is not None:
            data["end"] = self.end
        if self.point is not None:
            data["point"] = self.point
        if self.timezone_assumption is not None:
            data["timezone_assumption"] = self.timezone_assumption
        data["output_timezone"] = self.output_timezone
        return data


def _start_of_day(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return datetime(dt.year, dt.month, dt.day)
    return datetime(dt.year, dt.month, dt.day, tzinfo=dt.tzinfo)


def _utc14(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")


def _range(expression: str, start: datetime, end: datetime) -> NormalizedTemporal:
    return NormalizedTemporal(
        kind="TIME_RANGE",
        expression=expression,
        start=_utc14(start),
        end=_utc14(end),
    )


def _point(expression: str, point: datetime) -> NormalizedTemporal:
    return NormalizedTemporal(
        kind="TIME_POINT",
        expression=expression,
        point=_utc14(point),
    )


def _timezone_assumption(ref: datetime) -> str:
    if ref.tzinfo is None:
        return "naive_reference_assumed_utc"
    return f"reference_tz={ref.tzinfo}"


def _split_segments(text: str) -> list[str]:
    segments = [seg.strip() for seg in re.split(r"[,，、،]+", text) if seg.strip()]
    return segments or [text.strip()]


def normalize_time_expression(text: str, lang: str, reference_dt: datetime | None = None) -> list[NormalizedTemporal]:
    if not text.strip():
        return []

    ref = reference_dt or datetime.now()
    tz_assumption = _timezone_assumption(ref)
    today_start = _start_of_day(ref)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    day_after_tomorrow_start = today_start + timedelta(days=2)

    results: list[NormalizedTemporal] = []
    for segment in _split_segments(text):
        normalized = _normalize_single_segment(segment, lang=lang, ref=ref)
        results.extend(normalized)

    lowered = text.lower()
    if lang == "ko":
        if ("어제 이후" in text or "어제 이후로" in text) and all(item.expression != "어제 이후로" for item in results):
            results.append(_range("어제 이후로", yesterday_start, tomorrow_start))
        if "어제" in text and all(item.expression != "어제" for item in results) and not any(item.expression == "어제 이후로" for item in results):
            results.append(_range("어제", yesterday_start, today_start))
        if "오늘" in text and all(item.expression != "오늘" for item in results):
            results.append(_range("오늘", today_start, tomorrow_start))
        if "내일" in text and all(item.expression != "내일" for item in results):
            results.append(_range("내일", tomorrow_start, day_after_tomorrow_start))
        if "이날" in text and all(item.expression != "이날" for item in results):
            results.append(_range("이날", today_start, tomorrow_start))
        if "당일" in text and all(item.expression != "당일" for item in results):
            results.append(_range("당일", today_start, tomorrow_start))
    if lang == "en":
        if "since yesterday" in lowered and all(item.expression != "since yesterday" for item in results):
            results.append(_range("since yesterday", yesterday_start, tomorrow_start))
        if "yesterday" in lowered and all(item.expression != "yesterday" for item in results) and not any(item.expression == "since yesterday" for item in results):
            results.append(_range("yesterday", yesterday_start, today_start))
        if "today" in lowered and all(item.expression != "today" for item in results):
            results.append(_range("today", today_start, tomorrow_start))

    for item in results:
        item.timezone_assumption = tz_assumption

    return results


def _normalize_single_segment(segment: str, lang: str, ref: datetime) -> list[NormalizedTemporal]:
    s = segment.strip()
    lowered = s.lower()
    today_start = _start_of_day(ref)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    day_after_tomorrow_start = today_start + timedelta(days=2)

    if lang == "ko":
        if s == "어제":
            return [_range("어제", yesterday_start, today_start)]
        if s == "오늘":
            return [_range("오늘", today_start, tomorrow_start)]
        if s == "내일":
            return [_range("내일", tomorrow_start, day_after_tomorrow_start)]
        if s == "이날":
            return [_range("이날", today_start, tomorrow_start)]
        if s == "당일":
            return [_range("당일", today_start, tomorrow_start)]
        if "어제 이후" in s or "어제 이후로" in s:
            return [_range("어제 이후로", yesterday_start, tomorrow_start)]

        recent_match = re.search(r"최근\s*(\d{1,3})\s*일", s)
        if recent_match:
            days = int(recent_match.group(1))
            if days > 0:
                start = today_start - timedelta(days=days - 1)
                return [_range(f"최근 {days}일", start, tomorrow_start)]

        date_match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
        if date_match:
            year, month, day = map(int, date_match.groups())
            start = datetime(year, month, day)
            return [_range(date_match.group(0), start, start + timedelta(days=1))]

        point_match = re.search(r"내일\s*(오전|오후)?\s*(\d{1,2})\s*시", s)
        if point_match:
            meridiem = point_match.group(1)
            hour = int(point_match.group(2))
            if meridiem == "오후" and hour < 12:
                hour += 12
            if meridiem == "오전" and hour == 12:
                hour = 0
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    if lang == "en":
        if lowered == "yesterday":
            return [_range("yesterday", yesterday_start, today_start)]
        if lowered == "today":
            return [_range("today", today_start, tomorrow_start)]
        if "since yesterday" in lowered:
            return [_range("since yesterday", yesterday_start, tomorrow_start)]

        recent_match = re.search(r"(recent|last)\s*(\d{1,3})\s*days?", lowered)
        if recent_match:
            days = int(recent_match.group(2))
            if days > 0:
                start = today_start - timedelta(days=days - 1)
                return [_range(recent_match.group(0), start, tomorrow_start)]

        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", lowered)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]

        point_match = re.search(r"tomorrow\s*(at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lowered)
        if point_match:
            hour = int(point_match.group(2))
            minute = int(point_match.group(3) or 0)
            ampm = point_match.group(4)
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            point = tomorrow_start + timedelta(hours=hour, minutes=minute)
            return [_point(point_match.group(0), point)]

    if lang == "ja":
        if "昨日以降" in s:
            return [_range("昨日以降", yesterday_start, tomorrow_start)]
        if "昨日" in s:
            return [_range("昨日", yesterday_start, today_start)]
        if "今日" in s:
            return [_range("今日", today_start, tomorrow_start)]
        recent_match = re.search(r"直近\s*(\d{1,3})\s*日", s)
        if recent_match:
            days = int(recent_match.group(1))
            start = today_start - timedelta(days=days - 1)
            return [_range(recent_match.group(0), start, tomorrow_start)]
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]
        point_match = re.search(r"明日\s*(午前|午後)?\s*(\d{1,2})時", s)
        if point_match:
            meridiem = point_match.group(1)
            hour = int(point_match.group(2))
            if meridiem == "午後" and hour < 12:
                hour += 12
            if meridiem == "午前" and hour == 12:
                hour = 0
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    if lang == "zh":
        if "昨天以后" in s or "昨天之后" in s:
            return [_range("昨天以后", yesterday_start, tomorrow_start)]
        if "昨天" in s:
            return [_range("昨天", yesterday_start, today_start)]
        if "今天" in s:
            return [_range("今天", today_start, tomorrow_start)]
        recent_match = re.search(r"最近\s*(\d{1,3})\s*天", s)
        if recent_match:
            days = int(recent_match.group(1))
            start = today_start - timedelta(days=days - 1)
            return [_range(recent_match.group(0), start, tomorrow_start)]
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]
        point_match = re.search(r"明天\s*(上午|下午)?\s*(\d{1,2})点", s)
        if point_match:
            meridiem = point_match.group(1)
            hour = int(point_match.group(2))
            if meridiem == "下午" and hour < 12:
                hour += 12
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    if lang == "fr":
        if lowered == "hier":
            return [_range("hier", yesterday_start, today_start)]
        if lowered == "aujourd'hui":
            return [_range("aujourd'hui", today_start, tomorrow_start)]
        if "depuis hier" in lowered:
            return [_range("depuis hier", yesterday_start, tomorrow_start)]
        recent_match = re.search(r"(derniers|dernier)\s*(\d{1,3})\s*jours?", lowered)
        if recent_match:
            days = int(recent_match.group(2))
            start = today_start - timedelta(days=days - 1)
            return [_range(recent_match.group(0), start, tomorrow_start)]
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", lowered)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]
        point_match = re.search(r"demain\s*(à\s*)?(\d{1,2})h", lowered)
        if point_match:
            hour = int(point_match.group(2))
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    if lang == "de":
        if lowered == "gestern":
            return [_range("gestern", yesterday_start, today_start)]
        if lowered == "heute":
            return [_range("heute", today_start, tomorrow_start)]
        if "seit gestern" in lowered:
            return [_range("seit gestern", yesterday_start, tomorrow_start)]
        recent_match = re.search(r"letzten\s*(\d{1,3})\s*tage", lowered)
        if recent_match:
            days = int(recent_match.group(1))
            start = today_start - timedelta(days=days - 1)
            return [_range(recent_match.group(0), start, tomorrow_start)]
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", lowered)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]
        point_match = re.search(r"morgen\s*(um\s*)?(\d{1,2})\s*uhr", lowered)
        if point_match:
            hour = int(point_match.group(2))
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    if lang == "ar":
        if "منذ أمس" in s:
            return [_range("منذ أمس", yesterday_start, tomorrow_start)]
        if "أمس" in s:
            return [_range("أمس", yesterday_start, today_start)]
        if "اليوم" in s:
            return [_range("اليوم", today_start, tomorrow_start)]
        recent_match = re.search(r"آخر\s*(\d{1,3})\s*أيام", s)
        if recent_match:
            days = int(recent_match.group(1))
            start = today_start - timedelta(days=days - 1)
            return [_range(recent_match.group(0), start, tomorrow_start)]
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if iso_date:
            year, month, day = map(int, iso_date.groups())
            start = datetime(year, month, day)
            return [_range(iso_date.group(0), start, start + timedelta(days=1))]
        point_match = re.search(r"غدًا\s*(الساعة\s*)?(\d{1,2})", s)
        if point_match:
            hour = int(point_match.group(2))
            point = tomorrow_start + timedelta(hours=hour)
            return [_point(point_match.group(0), point)]

    return []