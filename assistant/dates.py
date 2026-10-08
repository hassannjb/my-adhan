"""
Find a date in a question: "tomorrow", "next Friday", "in 3 days",
"3 March 2031", "March 3rd", "2031-03-03", "03/04/2031", "1 Ramadan 1448".

Deterministic regexes only. Returns the date plus the span it was found at,
so the caller can strip it before looking for a city name.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from assistant.hijri import HIJRI_MONTH_NAMES, hijri_month_regex, hijri_to_gregorian, today_hijri

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ORD = r"(?:st|nd|rd|th)?"

_HIJRI_RE = re.compile(
    rf"\b(\d{{1,2}}){_ORD}\s+(?:of\s+)?({hijri_month_regex()})\b(?:\s*,?\s*(\d{{4}}))?(?:\s*(?:a\.?h\.?|h)\b)?",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MONTH_RE})\b\.?(?:\s*,?\s*(\d{{4}}))?",
    re.IGNORECASE,
)
_MONTH_DAY_RE = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}}){_ORD}\b(?:\s*,?\s*(\d{{4}}))?",
    re.IGNORECASE,
)
_RELATIVE_RE = re.compile(
    r"\b(?:the\s+)?(day\s+after\s+tomorrow|day\s+before\s+yesterday|tomorrow|tmrw|tmr|"
    r"yesterday|today|tonight|this\s+(?:morning|afternoon|evening)|now)\b",
    re.IGNORECASE,
)
_OFFSET_RE = re.compile(
    r"\b(?:in\s+(\d{1,4}|a|one|two|three)\s+(day|week|month|year)s?(?:\s+time)?|"
    r"(\d{1,4}|a|one|two|three)\s+(day|week|month|year)s?\s+(ago|from\s+(?:now|today)))\b",
    re.IGNORECASE,
)
_WEEKDAY_RE = re.compile(
    rf"\b(?:(next|this|coming|last|on)\s+)?({'|'.join(_WEEKDAYS)})\b",
    re.IGNORECASE,
)
_WORD_NUM = {"a": 1, "one": 1, "two": 2, "three": 3}


@dataclass
class DateHit:
    date: date | None
    kind: str            # "relative" | "gregorian" | "hijri"
    span: tuple[int, int]
    label: str = ""      # how to echo it back, e.g. "tomorrow"
    error: str | None = None
    hijri: tuple[int, int, int] | None = None   # (year, month, day) when kind == "hijri"


def _make(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _bad(span, what: str) -> DateHit:
    return DateHit(None, "gregorian", span, error=f"{what} isn't a real date.")


def find_date(text: str, today: date | None = None) -> DateHit | None:
    """Return the first date mentioned in `text`, or None."""
    today = today or date.today()

    m = _HIJRI_RE.search(text)
    if m:
        day, month_txt, year = int(m.group(1)), m.group(2), m.group(3)
        month = _hijri_month_num(month_txt)
        hy = int(year) if year else today_hijri(today)[0]
        g, err = hijri_to_gregorian(hy, month, day)
        label = f"{day} {HIJRI_MONTH_NAMES[month]} {hy} AH"
        return DateHit(g, "hijri", m.span(), label, err, (hy, month, day))

    m = _ISO_RE.search(text)
    if m:
        y, mo, d = map(int, m.groups())
        g = _make(y, mo, d)
        return DateHit(g, "gregorian", m.span()) if g else _bad(m.span(), m.group(0))

    m = _NUMERIC_RE.search(text)
    if m:
        a, b, y = map(int, m.groups())
        # Day-first unless that's impossible; ambiguous ones read month-first
        # (North American). The answer always shows the full date it used.
        if a > 12:
            g = _make(y, b, a)
        else:
            g = _make(y, a, b)
        return DateHit(g, "gregorian", m.span()) if g else _bad(m.span(), m.group(0))

    for rx, day_idx, mon_idx in ((_DAY_MONTH_RE, 1, 2), (_MONTH_DAY_RE, 2, 1)):
        m = rx.search(text)
        if m:
            d = int(m.group(day_idx))
            mo = _MONTHS[m.group(mon_idx).lower()]
            y = int(m.group(3)) if m.group(3) else today.year
            g = _make(y, mo, d)
            return DateHit(g, "gregorian", m.span()) if g else _bad(m.span(), m.group(0).strip())

    m = _RELATIVE_RE.search(text)
    if m:
        w = re.sub(r"\s+", " ", m.group(1).lower())
        offset = {
            "day after tomorrow": 2, "day before yesterday": -2,
            "tomorrow": 1, "tmrw": 1, "tmr": 1, "yesterday": -1,
        }.get(w, 0)
        label = {"tmrw": "tomorrow", "tmr": "tomorrow", "now": "today"}.get(w, w)
        return DateHit(today + timedelta(days=offset), "relative", m.span(), label)

    m = _OFFSET_RE.search(text)
    if m:
        if m.group(1):
            n, unit, sign = m.group(1), m.group(2), 1
        else:
            n, unit, sign = m.group(3), m.group(4), (-1 if m.group(5).lower() == "ago" else 1)
        n = sign * (int(n) if n.isdigit() else _WORD_NUM[n.lower()])
        unit = unit.lower()
        if unit == "day":
            g = today + timedelta(days=n)
        elif unit == "week":
            g = today + timedelta(weeks=n)
        elif unit == "month":
            g = _add_months(today, n)
        else:
            g = _add_months(today, 12 * n)
        return DateHit(g, "relative", m.span(), m.group(0).lower())

    m = _WEEKDAY_RE.search(text)
    if m:
        which = (m.group(1) or "").lower()
        target = _WEEKDAYS.index(m.group(2).lower())
        delta = (target - today.weekday()) % 7
        if which == "last":
            delta = delta - 7 if delta else -7
        elif which == "next" and delta == 0:
            delta = 7
        label = f"{which} {m.group(2).capitalize()}".strip() if which in ("next", "last", "this") else m.group(2).capitalize()
        return DateHit(today + timedelta(days=delta), "relative", m.span(), label)

    return None


def _hijri_month_num(txt: str) -> int:
    from assistant.hijri import hijri_month_number
    return hijri_month_number(txt)
