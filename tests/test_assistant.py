"""Tests for the LLM-free chat assistant (assistant/)."""
from __future__ import annotations

from datetime import date

import pytest

from assistant import places
from assistant.dates import find_date
from assistant.faq import FAQ, FAQ_PATH, parse_faq
from assistant.places import extract_place
from assistant.router import Assistant

TODAY = date(2026, 10, 8)  # a Thursday


# ── dates ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("when is asr tomorrow", date(2026, 10, 9)),
    ("fajr the day after tomorrow", date(2026, 10, 10)),
    ("isha yesterday", date(2026, 10, 7)),
    ("maghrib tonight", TODAY),
    ("isha on 3 March 2031", date(2031, 3, 3)),
    ("isha on the 3rd of march 2031", date(2031, 3, 3)),
    ("isha on March 3, 2031", date(2031, 3, 3)),
    ("isha on march 3rd", date(2026, 3, 3)),
    ("fajr 2031-03-03", date(2031, 3, 3)),
    ("fajr on 25/12/2030", date(2030, 12, 25)),
    ("fajr on 12/25/2030", date(2030, 12, 25)),
    ("dhuhr in 3 days", date(2026, 10, 11)),
    ("dhuhr in a week", date(2026, 10, 15)),
    ("asr 2 weeks ago", date(2026, 9, 24)),
    ("asr on friday", date(2026, 10, 9)),
    ("asr next thursday", date(2026, 10, 15)),
    ("asr last friday", date(2026, 10, 2)),
    ("asr on sunday", date(2026, 10, 11)),
    ("fajr on 1 ramadan 1448", date(2027, 2, 8)),
    ("fajr on 1st of Ramadan 1448 AH", date(2027, 2, 8)),
    ("isha on 10 dhul-hijjah 1447", date(2026, 5, 27)),
])
def test_find_date(text, expected):
    hit = find_date(text, TODAY)
    assert hit is not None and hit.error is None
    assert hit.date == expected


def test_find_date_none_and_invalid():
    assert find_date("when does asr start", TODAY) is None
    assert find_date("isha on 30/02/2031", TODAY).error
    assert find_date("isha on 31 april 2031", TODAY).error


# ── places ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("When is Isha in Toronto ", "Toronto"),
    ("prayer times for Makkah", "Makkah"),
    ("what is the time for   in toronto", "toronto"),
    ("fajr in New York City please", "New York City"),
    ("asr in the morning", None),
    ("isha in my city", None),
    ("asr according to hanafi", None),
    ("can i pray in congregation", None),
    ("when is asr", None),
])
def test_extract_place(text, expected):
    assert extract_place(text) == expected


# ── routing ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def bot():
    return Assistant(FAQ())


@pytest.fixture(autouse=True)
def fake_geocode(monkeypatch):
    def geo(name):
        if name.lower() == "atlantisville":
            return None
        return {"name": name.title(), "lat": 21.4, "lng": 39.8, "tz": "Asia/Riyadh"}
    monkeypatch.setattr(places, "geocode", geo)


def ask(bot, q, prev=None):
    return bot.answer(q, prev=prev, today=TODAY)


@pytest.mark.parametrize("q, targets, day", [
    ("When is Asr tomorrow?", ["asr"], "2026-10-09"),
    ("when is zuhr going to be tomorrow", ["dhuhr"], "2026-10-09"),
    ("When is Isha on 3 March 2031?", ["isha"], "2031-03-03"),
    ("what time is maghrib", ["maghrib"], "2026-10-08"),
    ("fajr time", ["fajr"], "2026-10-08"),
    ("how long until maghrib", ["maghrib"], "2026-10-08"),
    ("prayer times next friday", ["all"], "2026-10-09"),
    ("sunrise tomorrow", ["sunrise"], "2026-10-09"),
    ("when is midnight tonight", ["midnight"], "2026-10-08"),
    ("what time does isha end tomorrow", ["isha"], "2026-10-09"),
])
def test_times_questions(bot, q, targets, day):
    r = ask(bot, q)
    assert r["kind"] == "times", r
    assert r["targets"] == targets
    assert r["date"] == day
    assert r["place"] is None


def test_times_with_place_and_hijri_date(bot):
    r = ask(bot, "Fajr in Makkah on 1 Ramadan 1448")
    assert r["kind"] == "times" and r["targets"] == ["fajr"]
    assert r["date"] == "2027-02-08"
    assert r["place"]["tz"] == "Asia/Riyadh"
    assert any("moon sighting" in n for n in r["notes"])


def test_unknown_place(bot):
    r = ask(bot, "when is isha in Atlantisville")
    assert r["kind"] == "error" and "Atlantisville" in r["text"]


def test_jumuah_is_dhuhr(bot):
    r = ask(bot, "when is jummah tomorrow")
    assert r["kind"] == "times" and r["targets"] == ["dhuhr"]
    assert any("Jumu'ah" in n for n in r["notes"])


def test_followups(bot):
    first = ask(bot, "when is asr in Makkah tomorrow")
    prev = {k: first[k] for k in ("targets", "date", "date_label", "place")}
    r = ask(bot, "and on friday?", prev=prev)
    assert r["kind"] == "times" and r["targets"] == ["asr"] and r["date"] == "2026-10-09"
    r = ask(bot, "what about isha?", prev=prev)
    assert r["kind"] == "times" and r["targets"] == ["isha"]
    assert r["date"] == "2026-10-09" and r["place"]["name"] == "Makkah"


@pytest.mark.parametrize("q, entry", [
    ("How many prayers are there?", "five-daily"),
    ("how many rakats in isha", "five-daily"),
    ("what makes a salah start", "times-overview"),
    ("what makes a salah end", "times-overview"),
    ("what other prayers are there", "voluntary-overview"),
    ("how many sunnah before dhuhr", "sunnah-rawatib"),
    ("is witr wajib", "witr"),
    ("what is qiyamul layl", "tahajjud"),
    ("when is tahajjud", "tahajjud"),
    ("duha time", "duha"),
    ("awabin prayer", "awwabin"),
    ("tarawih 8 or 20", "tarawih"),
    ("is it better to pray fajr early", "fajr-time"),
    ("when does fajr end", "fajr-time"),
    ("when does zuhr start", "dhuhr-time"),
    ("When does Asr start?", "asr-time"),
    ("when is asr according to hanafi", "asr-time"),
    ("when does maghrib time end", "maghrib-time"),
    ("can i pray isha after midnight", "isha-time"),
    ("can i pray after asr", "forbidden-times"),
    ("when is jumuah prayed", "jumuah-time"),
    ("when is eid prayer", "eid"),
    ("why does fajr differ between apps", "calc-methods"),
    ("what is the last third of the night", "islamic-midnight"),
])
def test_faq_matching(bot, q, entry):
    r = ask(bot, q)
    assert r["kind"] == "faq", r
    assert r["id"] == entry


def test_faq_attaches_todays_times_only_when_relevant(bot):
    assert ask(bot, "when does asr end")["times"]["targets"] == ["asr"]
    assert "times" not in ask(bot, "how many rakats in isha")
    assert ask(bot, "when is tahajjud")["times"]["targets"] == ["midnight", "last_third"]


@pytest.mark.parametrize("q", ["what is the capital of france", "how to make wudu", "tell me a joke"])
def test_out_of_scope_falls_back(bot, q):
    r = ask(bot, q)
    assert r["kind"] == "fallback" and r["suggestions"]


def test_hijri_conversion(bot):
    r = ask(bot, "what is the hijri date today")
    assert r["kind"] == "convert" and "1448 AH" in r["text"]
    r = ask(bot, "what is 1 ramadan 1448 in gregorian")
    assert r["kind"] == "convert" and "8 February 2027" in r["text"]


def test_invalid_date(bot):
    assert ask(bot, "when is isha 30/02/2031")["kind"] == "error"


# ── content ──────────────────────────────────────────────────────────────────

def test_faq_file_is_well_formed():
    entries = parse_faq(FAQ_PATH.read_text(encoding="utf-8"))
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for e in entries:
        assert e.title.endswith("?"), e.id
        assert e.answer, e.id
        assert e.sources, f"{e.id} has no sources"
        assert e.asks, f"{e.id} has no example phrasings"
        assert e.prayers <= {"fajr", "dhuhr", "asr", "maghrib", "isha"}, e.id


def test_no_em_or_en_dashes_in_content():
    text = FAQ_PATH.read_text(encoding="utf-8")
    assert "—" not in text and "–" not in text


def test_keyword_fallback_still_answers():
    faq = FAQ(use_model=False)
    assert faq.mode == "keywords"
    assert faq.rank("is witr wajib")[0][1].id == "witr"
