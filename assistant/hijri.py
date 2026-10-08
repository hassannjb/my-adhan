"""
Hijri month names and Hijri <-> Gregorian conversion (Umm al-Qura calendar,
via hijridate). Month spellings come from rag/chat.py, without the Ollama
step that only reworded the result.
"""
from __future__ import annotations

import re
from datetime import date

from hijridate import Gregorian, Hijri

HIJRI_MONTH_NAMES = {
    1: "Muharram", 2: "Safar", 3: "Rabi' al-Awwal", 4: "Rabi' al-Thani",
    5: "Jumada al-Awwal", 6: "Jumada al-Thani", 7: "Rajab", 8: "Sha'ban",
    9: "Ramadan", 10: "Shawwal", 11: "Dhul Qa'dah", 12: "Dhul Hijjah",
}

# Spellings people type, written with spaces where a separator may appear.
# Matching ignores spaces, hyphens and apostrophes.
_SPELLINGS: dict[int, list[str]] = {
    1: ["muharram", "muharam"],
    2: ["safar"],
    3: ["rabi al awwal", "rabi ul awwal", "rabi ul awal", "rabi al awal", "rabi i", "rabi 1"],
    4: ["rabi al thani", "rabi ul thani", "rabi al akhir", "rabi ul akhir", "rabi ii", "rabi 2"],
    5: ["jumada al awwal", "jumada al ula", "jumad al awwal", "jumada ul awwal", "jumada i", "jumada 1"],
    6: ["jumada al thani", "jumada al akhirah", "jumada al ukhra", "jumad al thani", "jumada ul thani", "jumada ii", "jumada 2"],
    7: ["rajab"],
    8: ["shaban", "sha ban", "shaaban"],
    9: ["ramadan", "ramadhan", "ramzan", "ramazan"],
    10: ["shawwal", "shawal"],
    11: ["dhul qadah", "dhul qidah", "dhu al qadah", "dhu al qidah", "zul qadah", "zulqadah", "dhul qaadah", "zil qad"],
    12: ["dhul hijjah", "dhul hija", "dhu al hijjah", "zul hijjah", "zil hajj", "dhul hijja"],
}

# Calendar range hijridate supports.
MIN_HIJRI, MAX_HIJRI = 1343, 1500


def _norm(s: str) -> str:
    return re.sub(r"[\s\-'’`]", "", s.lower())


_LOOKUP = {_norm(s): n for n, names in _SPELLINGS.items() for s in names}


def hijri_month_regex() -> str:
    """Regex alternation matching any spelling, longest first."""
    parts = []
    for s in sorted({s for names in _SPELLINGS.values() for s in names}, key=len, reverse=True):
        letters = [re.escape(c) for c in s.replace(" ", "")]
        parts.append(r"[\s\-'’`]?".join(letters))
    return "|".join(parts)


def hijri_month_number(txt: str) -> int:
    return _LOOKUP[_norm(txt)]


def today_hijri(today: date | None = None) -> tuple[int, int, int]:
    t = today or date.today()
    h = Gregorian(t.year, t.month, t.day).to_hijri()
    return h.year, h.month, h.day


def hijri_to_gregorian(year: int, month: int, day: int) -> tuple[date | None, str | None]:
    if not MIN_HIJRI <= year <= MAX_HIJRI:
        return None, f"I can only convert Hijri years {MIN_HIJRI} to {MAX_HIJRI}."
    try:
        g = Hijri(year, month, day).to_gregorian()
    except (ValueError, OverflowError):
        return None, f"{day} {HIJRI_MONTH_NAMES[month]} {year} AH isn't a valid date."
    return date(g.year, g.month, g.day), None


def gregorian_to_hijri(d: date) -> tuple[tuple[int, int, int] | None, str | None]:
    try:
        h = Gregorian(d.year, d.month, d.day).to_hijri()
    except (ValueError, OverflowError):
        return None, "I can only convert dates between 1924 and 2077."
    return (h.year, h.month, h.day), None


def format_hijri(y: int, m: int, d: int) -> str:
    return f"{d} {HIJRI_MONTH_NAMES[m]} {y} AH"
