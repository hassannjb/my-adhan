"""
Decide what a question is asking for and build a JSON-ready reply.

  times   : "When is Asr tomorrow?", "Isha in Lahore on 3 March 2031"
            The server only works out which times, which date and where.
            The browser calculates them with adhan.js and the user's own
            settings, so the chat always agrees with the clock.
  faq     : "When does Asr end?", "Is witr wajib?"  (curated answer)
  convert : "What is 1 Ramadan 1448 in Gregorian?", "Hijri date today"
  fallback: anything else, with suggested questions.
"""
from __future__ import annotations

import re
from datetime import date

from assistant import hijri, places
from assistant.dates import DateHit, find_date
from assistant.faq import ACCEPT, FAQ, PRAYERS, SUGGEST

# Target -> regex. Order matters for display.
_TARGETS = {
    "fajr": r"fajr|fajar|fajir|fazr|subh|sobh|dawn\s+prayer",
    "sunrise": r"sunrise|shuruq|shurooq",
    "dhuhr": r"dhuhr|zuhr|zohr|zuhur|duhr|dhuhur|zohar|zuhar|dhuhar|noon\s+prayer",
    "jumuah": r"jumu'?ah|jum'?ah|jummah|jumma|juma|friday\s+prayer",
    "asr": r"asr|asar|afternoon\s+prayer",
    "maghrib": r"maghrib|magrib|maghreb|sunset",
    "isha": r"isha'?a?|esha|ishaa",
    "midnight": r"(?:islamic\s+)?midnight|middle\s+of\s+the\s+night|half\s+(?:of\s+)?the\s+night",
    "last_third": r"last\s+third(?:\s+of\s+the\s+night)?|tahajjud\s+time",
}
_TARGET_RES = {k: re.compile(rf"\b(?:{v})\b", re.IGNORECASE) for k, v in _TARGETS.items()}
_ALL_RE = re.compile(
    r"\b(?:prayer|salah|salat|namaz|namaaz)\s+(?:times?|timings?|schedule)\b|"
    r"\btimes?\s+(?:of|for)\s+(?:prayers?|salah|salat|namaz)\b|\ball\s+(?:the\s+)?prayers\b",
    re.IGNORECASE,
)
_ASKS_TIME = re.compile(
    r"\b(?:when|what\s+time|time|timing|timings|how\s+long\s+(?:until|till|to|before)|is\s+it)\b",
    re.IGNORECASE,
)
# Words that make it a question about the ruling rather than today's clock.
_ASKS_CONCEPT = re.compile(
    r"\b(?:starts?|begins?|beginning|ends?|ending|finish(?:es)?|over|expires?|enters?|"
    r"until\s+when|till\s+when|ruling|best|preferred|delay|why|how\s+many|calculated|calculate|"
    r"method|hanafi|shafi'?i|maliki|hanbali|madhh?ab|allowed|forbidden|makruh|permissible|"
    r"can\s+i|should|prayed|better|earlier|later|early|late|sunnah|wajib|fard|meaning|define|definition)\b|\bwhat\s+is\s+(?!the\s+time)",
    re.IGNORECASE,
)
_HIJRI_KW = re.compile(
    r"\b(?:hijri|hijra|islamic\s+(?:date|calendar|month|year)|lunar\s+date|in\s+gregorian|"
    r"gregorian\s+date|english\s+date|a\.?h\.?)\b",
    re.IGNORECASE,
)


def _targets(text: str) -> list[str]:
    found = [k for k, rx in _TARGET_RES.items() if rx.search(text)]
    if "jumuah" in found:
        found = [t for t in found if t != "jumuah"]
        if "dhuhr" not in found:
            found.insert(0, "dhuhr")
        found.append("jumuah_note")
    if _ALL_RE.search(text) and not [t for t in found if t != "jumuah_note"]:
        found = ["all"]
    return found


def _prayer_tags(targets: list[str]) -> set[str]:
    return {t for t in targets if t in PRAYERS}


def _strip(text: str, span: tuple[int, int] | None) -> str:
    return text if span is None else text[: span[0]] + " " + text[span[1]:]


def _times_reply(targets, d: date, label: str, place: dict | None, notes: list[str]) -> dict:
    note_list = list(notes)
    if "jumuah_note" in targets:
        targets = [t for t in targets if t != "jumuah_note"]
        note_list.append("Jumu'ah is prayed in Dhuhr's time, so this is the Dhuhr time.")
    return {
        "kind": "times",
        "targets": targets or ["all"],
        "date": d.isoformat(),
        "date_label": label,
        "place": place,
        "notes": note_list,
    }


class Assistant:
    def __init__(self, faq: FAQ | None = None) -> None:
        self.faq = faq or FAQ()

    def answer(self, question: str, prev: dict | None = None, today: date | None = None) -> dict:
        today = today or date.today()
        q = re.sub(r"\s+", " ", question).strip()
        if not q:
            return self._fallback("Ask me about prayer times or the basics of salah.")

        hit: DateHit | None = find_date(q, today)
        if hit and hit.error:
            return {"kind": "error", "text": hit.error}
        targets = _targets(q)
        rest = _strip(q, hit.span if hit else None)
        for rx in _TARGET_RES.values():
            rest = rx.sub(" ", rest)
        place_name = places.extract_place(rest)

        real_targets = [t for t in targets if t != "jumuah_note"]
        concept = bool(_ASKS_CONCEPT.search(q))
        short_followup = prev is not None and len(q.split()) <= 5 and not concept

        # 1. Prayer times for a date / place / right now.
        wants_times = bool(real_targets) and (
            hit is not None or place_name is not None
            or (_ASKS_TIME.search(q) and not concept) or short_followup
            or (len(q.split()) <= 2)
        )
        # A follow-up that only changes the date or place ("and tomorrow?").
        if not real_targets and prev and prev.get("targets") and (hit or place_name) and not concept \
                and not _HIJRI_KW.search(q):
            targets, real_targets, wants_times = list(prev["targets"]), list(prev["targets"]), True

        if wants_times:
            place = None
            if place_name:
                try:
                    place = places.geocode(place_name)
                except LookupError as e:
                    return {"kind": "error", "text": str(e)}
                if place is None:
                    return {"kind": "error", "text": f"I couldn't find a place called \"{place_name}\"."}
            elif short_followup and prev and not hit:
                place = prev.get("place")
            if hit:
                d, label = hit.date, hit.label
            elif short_followup and prev and prev.get("date"):
                d, label = date.fromisoformat(prev["date"]), prev.get("date_label", "")
            else:
                d, label = today, "today"
            notes = []
            if hit and hit.kind == "hijri":
                notes.append(f"{hit.label} is {d.strftime('%A, %-d %B %Y')} on the Umm al-Qura calendar. "
                             "Where you are, the month may start a day earlier or later depending on moon sighting.")
            return _times_reply(targets, d, label, place, notes)

        # 2. Hijri <-> Gregorian.
        if not real_targets and (_HIJRI_KW.search(q) or (hit and hit.kind == "hijri")):
            return self._convert(hit, today)

        # 3. Curated answer.
        ranked = self.faq.rank(q, _prayer_tags(real_targets))
        best_score, best = ranked[0]
        if best_score >= ACCEPT:
            reply = {
                "kind": "faq",
                "id": best.id,
                "title": best.title,
                "answer": best.answer,
                "sources": best.sources,
                "score": round(best_score, 3),
            }
            # Attach today's times only when the answer is about that prayer.
            today_targets = [t for t in real_targets if t in best.prayers]
            if best.id in ("islamic-midnight", "tahajjud"):
                today_targets = ["midnight", "last_third"]
            if today_targets:
                reply["times"] = _times_reply(today_targets, today, "today", None, [])
            return reply
        if best_score >= SUGGEST:
            close = [e.title for s, e in ranked[:3] if s >= SUGGEST]
            return {"kind": "fallback", "text": "I'm not sure I understood. Did you mean one of these?",
                    "suggestions": close}
        return self._fallback()

    def _convert(self, hit: DateHit | None, today: date) -> dict:
        if hit and hit.kind == "hijri":
            if hit.error:
                return {"kind": "error", "text": hit.error}
            text = f"{hit.label} is {hit.date.strftime('%A, %-d %B %Y')}."
        else:
            d = hit.date if hit else today
            h, err = hijri.gregorian_to_hijri(d)
            if err:
                return {"kind": "error", "text": err}
            when = {"today": "Today", "tomorrow": "Tomorrow", "yesterday": "Yesterday"}.get(
                hit.label if hit else "today")
            prefix = f"{when} ({d.strftime('%A, %-d %B %Y')})" if when else d.strftime('%A, %-d %B %Y')
            text = f"{prefix} is {hijri.format_hijri(*h)}."
        return {"kind": "convert",
                "text": text + " This uses the Umm al-Qura calendar. Where you are, the month may "
                               "start a day earlier or later depending on moon sighting."}

    def _fallback(self, text: str | None = None) -> dict:
        return {
            "kind": "fallback",
            "text": text or ("I can answer basic questions about salah (how many prayers there are, "
                             "when each prayer's time starts and ends, witr, tahajjud, duha and so on) "
                             "and give prayer times for any date and city."),
            "suggestions": self.faq.suggestions(3) + ["When is Isha tomorrow?"],
        }
