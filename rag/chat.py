"""
RAG Chat — with live prayer-time tool use and Quran MCP
========================================================

Answers three kinds of questions:
  1. Knowledge questions ("What is the ISNA method?")
     → standard RAG: retrieve chunks → Ollama generates answer

  2. Live calculation questions ("When is Fajr in Toronto tomorrow?")
     → tool use: Ollama calls get_prayer_times(city, date) → PrayerService
       calculates using adhanpy → Ollama formulates the answer

  3. Quran questions ("What does 2:255 say?", "verses about patience")
     → Quran MCP: JSON-RPC call to mcp.quran.ai → Ollama formats the answer

No API keys required — all inference runs locally via Ollama.

Usage:
    python rag/ingest.py          # build index first
    python rag/chat.py            # interactive
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

import ollama
import requests
from rag.query import (  # noqa: E402
    INDEX_PATH, OLLAMA_MODEL, answer, answer_stream, load_clients, load_index,
)

# ── Quran MCP ────────────────────────────────────────────────────────────────

QURAN_MCP_URL = "https://mcp.quran.ai/"
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


_SSE_FIELD_NAMES = {"event:", "data:", "id:", "retry:"}
_CTRL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _repair_json(s: str) -> str:
    """Escape unescaped control characters inside JSON string values.

    The Quran MCP server sends Arabic verse text with literal newlines embedded
    inside JSON string values, which is invalid JSON.  Walk character-by-character
    and replace bare control chars inside strings with their JSON escape sequences.
    """
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in s:
        if escaped:
            result.append(ch)
            escaped = False
        elif in_string and ch == "\\":
            result.append(ch)
            escaped = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch in _CTRL_ESCAPES:
            result.append(_CTRL_ESCAPES[ch])
        else:
            result.append(ch)
    return "".join(result)


def _parse_sse(text: str) -> dict:
    """Parse an SSE response, reassembling multi-line data fields."""
    for event_block in text.split("\n\n"):
        fragments: list[str] = []
        in_data = False
        for line in event_block.splitlines():
            if line.startswith("data: "):
                in_data = True
                fragments.append(line[6:])
            elif in_data and not any(line.startswith(f) for f in _SSE_FIELD_NAMES):
                fragments.append(line)
        if fragments:
            try:
                return json.loads(_repair_json("\n".join(fragments)))
            except json.JSONDecodeError:
                pass
    return {}


def _quran_session() -> dict:
    """Initialize a Quran MCP session and return headers with the session ID."""
    resp = requests.post(
        QURAN_MCP_URL,
        json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "my-adhan", "version": "1.0"},
            },
        },
        headers=_MCP_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id", "")
    return {**_MCP_HEADERS, "mcp-session-id": session_id}


def _call_quran_tool(tool_name: str, arguments: dict, headers: dict) -> str:
    """Call a Quran MCP tool with an established session. Returns the JSON data text only."""
    args = {**arguments, "grounding_nonce": str(uuid.uuid4())}
    resp = requests.post(
        QURAN_MCP_URL,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": tool_name, "arguments": args}},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = _parse_sse(resp.text)
    if "error" in data:
        raise RuntimeError(data["error"])
    content = data.get("result", {}).get("content", [])
    # The first text item is the JSON payload; remaining items are server instructions
    for item in content:
        if item.get("type") == "text":
            return item.get("text", "")
    return ""


_QURAN_SYSTEM = (
    "You are an Islamic assistant. You have been given Quran data retrieved from the "
    "quran.ai database. Use ONLY the provided data to answer — do not add information "
    "from memory or training data. Present the verses clearly and respectfully. "
    "If the data doesn't contain a specific answer (e.g. an exact count), say so honestly "
    "and present what was found. Do not make up numbers, verse references, or translations."
)

_VERSE_RE = re.compile(r'\b(\d+):(\d+(?:-\d+)?)\b')
# "chapter 2 verse 255" / "surah 2 ayah 255"
_NATURAL_VERSE_RE = re.compile(
    r'(?:chapter|surah|sura)\s+(\d+)\s+(?:verse|ayah|ayat)\s+(\d+(?:-\d+)?)',
    re.IGNORECASE,
)
# "verse 255 of chapter 2" / "ayah 255 of surah 2"
_VERSE_OF_CHAPTER_RE = re.compile(
    r'(?:verse|ayah|ayat)\s+(\d+(?:-\d+)?)\s+of\s+(?:chapter|surah|sura)\s+(\d+)',
    re.IGNORECASE,
)

# Surah number → verse count for all 114 surahs
_SURAH_VERSE_COUNTS = [
    0,   # padding so index == surah number
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109,   # 1-10
    123, 111, 43, 52, 99, 128, 111, 110, 98, 135,    # 11-20
    112, 78, 118, 64, 77, 227, 93, 88, 69, 60,       # 21-30
    34, 30, 73, 54, 45, 83, 182, 88, 75, 85,         # 31-40
    54, 53, 89, 59, 37, 35, 38, 29, 18, 45,          # 41-50
    60, 49, 62, 55, 78, 96, 29, 22, 24, 13,          # 51-60
    14, 11, 11, 18, 12, 12, 30, 52, 52, 44,          # 61-70
    28, 28, 20, 56, 40, 31, 50, 40, 46, 42,          # 71-80
    29, 19, 36, 25, 22, 17, 19, 26, 30, 20,          # 81-90
    15, 21, 11, 8, 8, 19, 5, 8, 8, 11,              # 91-100
    11, 8, 3, 9, 5, 4, 7, 3, 6, 3,                  # 101-110
    5, 4, 5, 6,                                       # 111-114
]

# Normalized name → surah number  (key = lowercase, no spaces, no "al/an/ar/as/at/az/ad" prefix)
_SURAH_BY_NAME: dict[str, int] = {}

def _idx(*pairs: tuple[int, str]) -> None:
    for num, name in pairs:
        key = name.lower().replace(" ", "").replace("-", "").replace("'", "")
        _SURAH_BY_NAME[key] = num
        # also index without common Arabic article prefix
        for art in ("al", "an", "ar", "as", "at", "az", "ad"):
            if key.startswith(art):
                _SURAH_BY_NAME[key[len(art):]] = num
                break

_idx(
    (1, "Al-Fatihah"), (1, "Al-Fatiha"), (1, "Fatiha"), (1, "Opening"),
    (2, "Al-Baqarah"), (2, "Baqara"), (2, "Cow"),
    (3, "Ali-Imran"), (3, "Al-Imran"), (3, "Imran"),
    (4, "An-Nisa"), (4, "Nisa"), (4, "Women"),
    (5, "Al-Maidah"), (5, "Al-Ma'idah"), (5, "Maidah"), (5, "Table"),
    (6, "Al-Anam"), (6, "Al-An'am"), (6, "Anam"), (6, "Cattle"),
    (7, "Al-Araf"), (7, "Al-A'raf"), (7, "Araf"),
    (8, "Al-Anfal"), (8, "Anfal"), (8, "Spoils"),
    (9, "At-Tawbah"), (9, "Tawbah"), (9, "Repentance"), (9, "Bara'ah"),
    (10, "Yunus"), (10, "Jonah"),
    (11, "Hud"),
    (12, "Yusuf"), (12, "Joseph"),
    (13, "Ar-Ra'd"), (13, "Ra'd"), (13, "Thunder"),
    (14, "Ibrahim"), (14, "Abraham"),
    (15, "Al-Hijr"), (15, "Hijr"),
    (16, "An-Nahl"), (16, "Nahl"), (16, "Bee"),
    (17, "Al-Isra"), (17, "Al-Isra'"), (17, "Isra"), (17, "Bani-Israil"), (17, "Night Journey"),
    (18, "Al-Kahf"), (18, "Kahf"), (18, "Cave"),
    (19, "Maryam"), (19, "Mary"),
    (20, "Ta-Ha"), (20, "Taha"),
    (21, "Al-Anbiya"), (21, "Al-Anbiya'"), (21, "Anbiya"), (21, "Prophets"),
    (22, "Al-Hajj"), (22, "Hajj"), (22, "Pilgrimage"),
    (23, "Al-Mu'minun"), (23, "Al-Muminun"), (23, "Muminun"), (23, "Believers"),
    (24, "An-Nur"), (24, "Nur"), (24, "Light"),
    (25, "Al-Furqan"), (25, "Furqan"), (25, "Criterion"),
    (26, "Ash-Shu'ara"), (26, "Shuara"), (26, "Poets"),
    (27, "An-Naml"), (27, "Naml"), (27, "Ant"),
    (28, "Al-Qasas"), (28, "Qasas"), (28, "Stories"),
    (29, "Al-Ankabut"), (29, "Al-'Ankabut"), (29, "Ankabut"), (29, "Spider"),
    (30, "Ar-Rum"), (30, "Rum"), (30, "Romans"),
    (31, "Luqman"),
    (32, "As-Sajdah"), (32, "Sajdah"), (32, "Prostration"),
    (33, "Al-Ahzab"), (33, "Ahzab"), (33, "Confederates"),
    (34, "Saba"), (34, "Sheba"),
    (35, "Fatir"), (35, "Al-Mala'ikah"), (35, "Creator"), (35, "Originator"),
    (36, "Ya-Sin"), (36, "Yasin"), (36, "Ya Sin"),
    (37, "As-Saffat"), (37, "Saffat"), (37, "Those Ranged"),
    (38, "Sad"), (38, "Saad"),
    (39, "Az-Zumar"), (39, "Zumar"), (39, "Groups"),
    (40, "Ghafir"), (40, "Al-Mu'min"), (40, "Mumin"), (40, "Forgiving"),
    (41, "Fussilat"), (41, "Ha-Mim Sajdah"),
    (42, "Ash-Shura"), (42, "Shura"), (42, "Consultation"),
    (43, "Az-Zukhruf"), (43, "Zukhruf"), (43, "Ornaments"),
    (44, "Ad-Dukhan"), (44, "Dukhan"), (44, "Smoke"),
    (45, "Al-Jathiyah"), (45, "Jathiyah"), (45, "Crouching"),
    (46, "Al-Ahqaf"), (46, "Ahqaf"),
    (47, "Muhammad"), (47, "Al-Qital"),
    (48, "Al-Fath"), (48, "Fath"), (48, "Victory"),
    (49, "Al-Hujurat"), (49, "Hujurat"), (49, "Rooms"),
    (50, "Qaf"),
    (51, "Adh-Dhariyat"), (51, "Dhariyat"), (51, "Winds"),
    (52, "At-Tur"), (52, "Tur"), (52, "Mount"),
    (53, "An-Najm"), (53, "Najm"), (53, "Star"),
    (54, "Al-Qamar"), (54, "Qamar"), (54, "Moon"),
    (55, "Ar-Rahman"), (55, "Rahman"), (55, "Beneficent"),
    (56, "Al-Waqi'ah"), (56, "Al-Waqiah"), (56, "Waqiah"), (56, "Event"),
    (57, "Al-Hadid"), (57, "Hadid"), (57, "Iron"),
    (58, "Al-Mujadilah"), (58, "Mujadilah"), (58, "Pleading"),
    (59, "Al-Hashr"), (59, "Hashr"), (59, "Exile"),
    (60, "Al-Mumtahanah"), (60, "Mumtahanah"), (60, "She That Is Tested"),
    (61, "As-Saf"), (61, "Saff"), (61, "Ranks"),
    (62, "Al-Jumu'ah"), (62, "Al-Juma"), (62, "Juma"), (62, "Friday"),
    (63, "Al-Munafiqun"), (63, "Munafiqun"), (63, "Hypocrites"),
    (64, "At-Taghabun"), (64, "Taghabun"), (64, "Mutual Disillusion"),
    (65, "At-Talaq"), (65, "Talaq"), (65, "Divorce"),
    (66, "At-Tahrim"), (66, "Tahrim"), (66, "Prohibition"),
    (67, "Al-Mulk"), (67, "Mulk"), (67, "Sovereignty"),
    (68, "Al-Qalam"), (68, "Qalam"), (68, "Pen"),
    (69, "Al-Haqqah"), (69, "Haqqah"), (69, "Reality"),
    (70, "Al-Ma'arij"), (70, "Maarij"), (70, "Ascending Stairways"),
    (71, "Nuh"), (71, "Noah"),
    (72, "Al-Jinn"), (72, "Jinn"),
    (73, "Al-Muzzammil"), (73, "Muzzammil"), (73, "Enshrouded"),
    (74, "Al-Muddaththir"), (74, "Muddaththir"), (74, "Wrapped"),
    (75, "Al-Qiyamah"), (75, "Qiyamah"), (75, "Resurrection"),
    (76, "Al-Insan"), (76, "Insan"), (76, "Al-Dahr"), (76, "Dahr"), (76, "Human"),
    (77, "Al-Mursalat"), (77, "Mursalat"), (77, "Emissaries"),
    (78, "An-Naba"), (78, "Naba"), (78, "Tidings"),
    (79, "An-Nazi'at"), (79, "Naziat"), (79, "Those Who Drag Forth"),
    (80, "Abasa"), (80, "He Frowned"),
    (81, "At-Takwir"), (81, "Takwir"), (81, "Overthrowing"),
    (82, "Al-Infitar"), (82, "Infitar"), (82, "Cleaving"),
    (83, "Al-Mutaffifin"), (83, "Mutaffifin"), (83, "Defrauding"),
    (84, "Al-Inshiqaq"), (84, "Inshiqaq"), (84, "Splitting Open"),
    (85, "Al-Buruj"), (85, "Buruj"), (85, "Constellations"),
    (86, "At-Tariq"), (86, "Tariq"), (86, "Night Star"),
    (87, "Al-A'la"), (87, "Al-Ala"), (87, "Ala"), (87, "Most High"),
    (88, "Al-Ghashiyah"), (88, "Ghashiyah"), (88, "Overwhelming"),
    (89, "Al-Fajr"), (89, "Fajr"), (89, "Dawn"),
    (90, "Al-Balad"), (90, "Balad"), (90, "City"),
    (91, "Ash-Shams"), (91, "Shams"), (91, "Sun"),
    (92, "Al-Layl"), (92, "Layl"), (92, "Night"),
    (93, "Ad-Duha"), (93, "Duha"), (93, "Morning Hours"),
    (94, "Ash-Sharh"), (94, "Al-Inshirah"), (94, "Inshirah"), (94, "Sharh"), (94, "Relief"),
    (95, "At-Tin"), (95, "Tin"), (95, "Fig"),
    (96, "Al-Alaq"), (96, "Alaq"), (96, "Clot"),
    (97, "Al-Qadr"), (97, "Qadr"), (97, "Power"), (97, "Night of Power"),
    (98, "Al-Bayyinah"), (98, "Bayyinah"), (98, "Clear Proof"),
    (99, "Az-Zalzalah"), (99, "Zalzalah"), (99, "Earthquake"),
    (100, "Al-Adiyat"), (100, "Al-'Adiyat"), (100, "Adiyat"), (100, "Chargers"),
    (101, "Al-Qari'ah"), (101, "Al-Qariah"), (101, "Qariah"), (101, "Calamity"),
    (102, "At-Takathur"), (102, "Takathur"), (102, "Rivalry"),
    (103, "Al-Asr"), (103, "Al-'Asr"), (103, "Asr"), (103, "Time"), (103, "Declining Day"),
    (104, "Al-Humazah"), (104, "Humazah"), (104, "Traducer"),
    (105, "Al-Fil"), (105, "Fil"), (105, "Elephant"),
    (106, "Quraysh"), (106, "Quraish"),
    (107, "Al-Ma'un"), (107, "Al-Maun"), (107, "Maun"), (107, "Assistance"),
    (108, "Al-Kawthar"), (108, "Kawthar"), (108, "Abundance"),
    (109, "Al-Kafirun"), (109, "Al-Kafiroon"), (109, "Kafirun"), (109, "Disbelievers"),
    (110, "An-Nasr"), (110, "Nasr"), (110, "Victory"),
    (111, "Al-Masad"), (111, "Al-Lahab"), (111, "Lahab"), (111, "Masad"), (111, "Palm Fiber"),
    (112, "Al-Ikhlas"), (112, "Ikhlas"), (112, "Sincerity"),
    (113, "Al-Falaq"), (113, "Falaq"), (113, "Daybreak"),
    (114, "An-Nas"), (114, "Nas"), (114, "Mankind"),
)
del _idx

_SURAH_NAME_DETECT_RE = re.compile(
    r'(?:surah|sura)\s+(\S+(?:\s+\S+){0,3})',
    re.IGNORECASE,
)


def _extract_verse_ref(question: str) -> str | None:
    """Return a surah:ayah string if the question names a specific verse."""
    m = _VERSE_RE.search(question)
    if m:
        return m.group(0)
    m = _NATURAL_VERSE_RE.search(question)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = _VERSE_OF_CHAPTER_RE.search(question)
    if m:
        return f"{m.group(2)}:{m.group(1)}"
    return None


def _lookup_surah(name: str) -> int | None:
    """Normalize a surah name string and return its surah number."""
    raw = name.strip().lower().replace(" ", "").replace("-", "").replace("'", "")
    num = _SURAH_BY_NAME.get(raw)
    if num is None:
        for art in ("al", "an", "ar", "as", "at", "az", "ad"):
            if raw.startswith(art):
                num = _SURAH_BY_NAME.get(raw[len(art):])
                break
    return num


def _extract_surah_ref(question: str) -> str | None:
    """Return a surah:1-N string when the question names a surah by name."""
    m = _SURAH_NAME_DETECT_RE.search(question)
    if not m:
        return None
    words = m.group(1).split()
    # Try progressively shorter name fragments (handles trailing words like "please")
    for end in range(len(words), 0, -1):
        num = _lookup_surah(" ".join(words[:end]))
        if num is not None:
            return f"{num}:1-{_SURAH_VERSE_COUNTS[num]}"
    return None


def _format_search_results(raw_json: str) -> str:
    """Parse search_quran JSON and return a clean human-readable summary for Ollama."""
    try:
        repaired = _repair_json(raw_json)
        # Strip trailing non-JSON content (server grounding instructions)
        end = repaired.rfind("}")
        if end != -1:
            repaired = repaired[: end + 1]
        data = json.loads(repaired)
        results = data.get("results", [])
        total = data.get("total_found") or len(results)
        if not results:
            return "No relevant verses found."
        lines = [f"Total found in database: {total} verse(s). Top results:\n"]
        for r in results[:10]:
            key = r.get("ayah_key", "?")
            translations = r.get("translations", [])
            if translations:
                trans_text = translations[0].get("text", "")
                lines.append(f"- {key}: {trans_text}")
            else:
                lines.append(f"- {key}")
        return "\n".join(lines)
    except Exception:
        return raw_json[:2000]  # truncated fallback


def _answer_via_quran(question: str, model: str) -> str:
    """Query Quran MCP and format the result with Ollama."""
    try:
        hdrs = _quran_session()
        ayah_ref = _extract_verse_ref(question) or _extract_surah_ref(question)
        if ayah_ref:
            translation = _call_quran_tool("fetch_translation", {"ayahs": ayah_ref}, hdrs)
            quran_data = f"Translation of {ayah_ref}:\n{translation}"
        else:
            raw = _call_quran_tool(
                "search_quran",
                {"query": question, "translations": "en-sahih-international"},
                hdrs,
            )
            quran_data = _format_search_results(raw)
    except Exception as exc:
        return f"Could not reach the Quran service: {exc}"

    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": _QURAN_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nQuran data from quran.ai:\n{quran_data}"},
        ],
    )
    return resp["message"]["content"]

# ── Prayer-time tool definition (OpenAI / Ollama format) ─────────────────────

PRAYER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_prayer_times",
        "description": (
            "Calculate prayer times for a city on a specific date. "
            "Use this whenever the user asks about prayer times for a named city "
            "or a relative date like 'today', 'tomorrow', or 'yesterday'. "
            "Do NOT use this for general questions about how prayer times work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'Toronto', 'London', 'Karachi'. "
                                   "Omit to use the local machine's location.",
                },
                "date": {
                    "type": "string",
                    "description": "One of: 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD.",
                },
            },
            "required": ["date"],
        },
    },
}


def _run_prayer_tool(city: str | None, date_str: str) -> str:
    from services.prayer_service import PrayerService
    svc = PrayerService()
    return svc.format_answer(city=city, date_str=date_str)


_CLASSIFIER_SYSTEM = (
    "Classify the user's question. Reply with exactly one word.\n"
    "Reply TOOL if they are asking for actual prayer times for a specific city, "
    "place, or date (e.g. 'when is Fajr in Toronto', 'prayer times tomorrow').\n"
    "Reply QURAN if they are asking about the Quran: verse references like '2:255', "
    "surah content, searching for Quranic topics, or wanting to read specific ayahs.\n"
    "Reply RAG for everything else (prayer concepts, calculation methods, app usage, "
    "general Islamic practices, how-to questions)."
)

_TOOL_SYSTEM = (
    "You are a prayer times assistant. "
    "The user wants to know prayer times for a specific location or date. "
    "Call get_prayer_times with the city and date from their question. "
    "If no city is mentioned, omit it (the tool will use the local location). "
    "After receiving the tool result, present the times clearly."
)


_QURAN_KEYWORDS = re.compile(
    r'\b(quran|quranic|surah|ayah|ayat|verse|verses|sura|جزء|آية|سورة)\b',
    re.IGNORECASE,
)

_DATE_KEYWORDS = re.compile(
    r'\b(hijri|islamic\s+date|islamic\s+calendar|hijra|'
    r'muharram|safar|rabi|jumada|rajab|sha.?ban|ramadan|shawwal|'
    r'dhul?\s*qi.?dah|dhul?\s*qa.?dah|dhul?\s*hijjah|zul\s*qa.?dah|'
    r'1[34]\d{2}\s*ah)\b',
    re.IGNORECASE,
)

# ── Hijri ↔ Gregorian date conversion ────────────────────────────────────────

_HIJRI_MONTH_NAMES = {
    1: "Muharram", 2: "Safar", 3: "Rabi' al-Awwal", 4: "Rabi' al-Thani",
    5: "Jumada al-Awwal", 6: "Jumada al-Thani", 7: "Rajab", 8: "Sha'ban",
    9: "Ramadan", 10: "Shawwal", 11: "Dhul Qa'dah", 12: "Dhul Hijjah",
}

_HIJRI_MONTH_NUMS: dict[str, int] = {}

def _hm(*pairs: tuple[int, str]) -> None:
    for n, name in pairs:
        k = name.lower().replace(" ", "").replace("-", "").replace("'", "")
        _HIJRI_MONTH_NUMS[k] = n

_hm(
    (1,  "muharram"),  (1,  "muharam"),  (1,  "muharrum"),
    (2,  "safar"),
    (3,  "rabi al awwal"), (3, "rabi al-awwal"), (3, "rabialawwal"),
    (3,  "rabi ul awwal"), (3, "rabiulawal"), (3, "rabiawal"),
    (3,  "rabi i"),    (3, "rabii"),
    (4,  "rabi al thani"), (4, "rabi al-thani"), (4, "rabialthani"),
    (4,  "rabi al akhir"), (4, "rabi ii"),  (4, "rabiii"),
    (5,  "jumada al awwal"), (5, "jumad al awwal"), (5, "jumadaalawwal"),
    (5,  "jumada i"),  (5, "jumadai"),
    (6,  "jumada al thani"), (6, "jumad al thani"), (6, "jumadaakhirah"),
    (6,  "jumada ii"), (6, "jumadaii"),
    (7,  "rajab"),
    (8,  "shaban"),    (8,  "sha ban"),   (8,  "shaaban"),
    (9,  "ramadan"),   (9,  "ramzan"),    (9,  "ramazan"),
    (10, "shawwal"),
    (11, "dhul qadah"),  (11, "dhul qidah"),  (11, "dhulqadah"),
    (11, "dhulqidah"),   (11, "dhul qi dah"), (11, "zul qadah"),
    (11, "zulqadah"),    (11, "dhulqaadah"),  (11, "dhiqadah"),
    (12, "dhul hijjah"), (12, "dhul hija"),   (12, "dhulhijjah"),
    (12, "zul hijjah"),  (12, "zulhijjah"),   (12, "dhihijjah"),
)
del _hm

_GREGORIAN_MONTH_NUMS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

DATE_CONVERSION_TOOL = {
    "type": "function",
    "function": {
        "name": "convert_date",
        "description": (
            "Convert between Gregorian and Islamic (Hijri) calendar dates. "
            "Use hijri_to_gregorian when the user gives an Islamic date and wants the Gregorian date. "
            "Use gregorian_to_hijri when the user gives a Gregorian date and wants the Islamic date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["hijri_to_gregorian", "gregorian_to_hijri"],
                },
                "day": {"type": "integer", "description": "Day of the month"},
                "month": {
                    "type": "string",
                    "description": (
                        "For hijri_to_gregorian: Hijri month name (e.g. 'Dhul Qidah', 'Ramadan'). "
                        "For gregorian_to_hijri: Gregorian month name or number."
                    ),
                },
                "year": {
                    "type": "integer",
                    "description": "Year. Hijri year for H→G; Gregorian year for G→H. "
                                   "Omit to use the current year.",
                },
            },
            "required": ["direction", "day", "month"],
        },
    },
}

def _detect_date_direction(question: str) -> str:
    """Return 'hijri_to_gregorian' if the question contains a Hijri month name,
    otherwise 'gregorian_to_hijri'."""
    q_norm = question.lower().replace(" ", "").replace("-", "").replace("'", "")
    for key in _HIJRI_MONTH_NUMS:
        if key in q_norm:
            return "hijri_to_gregorian"
    return "gregorian_to_hijri"


def _run_date_conversion(direction: str, day: int, month: str, year: int | None) -> str:
    from hijridate import Hijri, Gregorian
    import datetime

    today = datetime.date.today()

    if direction == "hijri_to_gregorian":
        if year is None:
            h_today = Gregorian(today.year, today.month, today.day).to_hijri()
            year = h_today.year
        key = str(month).lower().replace(" ", "").replace("-", "").replace("'", "")
        month_num = _HIJRI_MONTH_NUMS.get(key)
        if month_num is None:
            return f"Unknown Hijri month: '{month}'"
        try:
            g = Hijri(year, month_num, day).to_gregorian()
            month_name = _HIJRI_MONTH_NAMES[month_num]
            return (f"{day} {month_name} {year} AH  →  "
                    f"{g.strftime('%A, %d %B %Y')}")
        except Exception as e:
            return f"Conversion error: {e}"

    elif direction == "gregorian_to_hijri":
        if year is None:
            year = today.year
        key = str(month).lower().strip()
        month_num = (
            _GREGORIAN_MONTH_NUMS.get(key)
            or _GREGORIAN_MONTH_NUMS.get(key[:3])
            or (int(key) if key.isdigit() else None)
        )
        if month_num is None:
            return f"Unknown Gregorian month: '{month}'"
        try:
            h = Gregorian(year, month_num, day).to_hijri()
            import calendar
            g_month_name = calendar.month_name[month_num]
            h_month_name = _HIJRI_MONTH_NAMES[h.month]
            return (f"{day} {g_month_name} {year}  →  "
                    f"{h.day} {h_month_name} {h.year} AH")
        except Exception as e:
            return f"Conversion error: {e}"

    return "Unknown conversion direction."


_GREG_DATE_RE = re.compile(
    r'\b(\d+)(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|'
    r'august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
    r'\s*,?\s*(\d{4})\b',
    re.IGNORECASE,
)


def _extract_hijri_date(question: str) -> tuple[int, str, int | None] | None:
    """Return (day, month_key, year|None) from a question with a Hijri date."""
    q_norm = question.lower().replace("-", "").replace("'", "").replace(" ", "")
    found_key = found_num = None
    for key, num in sorted(_HIJRI_MONTH_NUMS.items(), key=lambda x: -len(x[0])):
        if key in q_norm:
            found_key, found_num = key, num
            break
    if found_key is None:
        return None
    numbers = [int(n) for n in re.findall(r'\d+', question)]
    day = next((n for n in numbers if 1 <= n <= 31), None)
    year = next((n for n in numbers if 1300 <= n <= 1600), None)
    if day is None:
        return None
    return day, found_key, year


def _extract_gregorian_date(question: str) -> tuple[int, str, int] | None:
    """Return (day, month_str, year) from a question with a Gregorian date."""
    m = _GREG_DATE_RE.search(question)
    if m:
        return int(m.group(1)), m.group(2), int(m.group(3))
    # Try "YYYY-MM-DD" or "DD/MM/YYYY"
    m2 = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', question)
    if m2:
        return int(m2.group(3)), str(int(m2.group(2))), int(m2.group(1))
    m3 = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', question)
    if m3:
        return int(m3.group(1)), str(int(m3.group(2))), int(m3.group(3))
    return None


def _answer_via_date(question: str, model: str) -> str:
    """Extract date via regex, convert, format result with Ollama."""
    direction = _detect_date_direction(question)

    if direction == "hijri_to_gregorian":
        parsed = _extract_hijri_date(question)
        if parsed:
            day, month_key, year = parsed
            result = _run_date_conversion("hijri_to_gregorian", day, month_key, year)
        else:
            result = None
    else:
        parsed = _extract_gregorian_date(question)
        if parsed:
            day, month_str, year = parsed
            result = _run_date_conversion("gregorian_to_hijri", day, month_str, year)
        else:
            result = None

    if result is None:
        return "Sorry, I couldn't extract a date from that question. Try something like '29th Dhul Qidah 1447' or '13 May 2026'."

    # Use Ollama to turn the raw conversion line into a natural response
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Present the date conversion result naturally and briefly."},
            {"role": "user", "content": f"Question: {question}\nConversion result: {result}"},
        ],
    )
    return resp["message"]["content"]


def _classify(question: str, model: str, history: list[dict] | None = None) -> str:
    """Returns 'TOOL', 'QURAN', 'DATE', or 'RAG'."""
    # Fast keyword pre-checks (bypass LLM for unambiguous signals)
    if _QURAN_KEYWORDS.search(question) or _VERSE_RE.search(question):
        return "QURAN"
    if _DATE_KEYWORDS.search(question):
        return "DATE"

    messages = [{"role": "system", "content": _CLASSIFIER_SYSTEM}]
    if history:
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": question})
    resp = ollama.chat(model=model, messages=messages)
    text = resp["message"]["content"].upper()
    if "TOOL" in text:
        return "TOOL"
    if "QURAN" in text:
        return "QURAN"
    return "RAG"


def _answer_via_tool(question: str, model: str, history: list[dict] | None = None) -> str:
    """Call the prayer tool and return a formatted answer."""
    messages = [{"role": "system", "content": _TOOL_SYSTEM}]
    if history:
        messages.extend(history[-4:])  # include prior turns so city can be inferred
    messages.append({"role": "user", "content": question})
    resp = ollama.chat(
        model=model,
        messages=messages,
        tools=[PRAYER_TOOL],
    )

    tool_calls = resp["message"].get("tool_calls") or []
    if not tool_calls:
        # Model didn't call the tool — fall back to plain answer
        return resp["message"]["content"]

    tool_call = tool_calls[0]
    args = tool_call["function"]["arguments"]
    if isinstance(args, str):
        import json
        args = json.loads(args)

    city = args.get("city")
    date_str = args.get("date", "today")
    tool_result = _run_prayer_tool(city, date_str)

    # Ask the model to present the result naturally
    final = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": _TOOL_SYSTEM},
            {"role": "user", "content": question},
            {"role": "assistant", "content": "", "tool_calls": [tool_call]},
            {"role": "tool", "content": tool_result},
        ],
    )
    return final["message"]["content"]


_LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "English": "",
    "Urdu":    "اردو میں جواب دیں۔",
    "Hindi":   "हिन्दी में उत्तर दें।",
    "Turkish": "Türkçe yanıt verin.",
    "Arabic":  "أجب باللغة العربية.",
}


def answer_stream_with_tools(
    question: str,
    records: list[dict],
    matrix,
    embedder,
    model: str,
    language: str = "English",
    history: list[dict] | None = None,
):
    """
    Main entry point for the web API and GUI.
    Routes TOOL questions to prayer service, RAG questions to Ollama + retrieval.
    Returns (token_generator, chunks).
    """
    if history is None:
        history = []

    lang_instr = _LANGUAGE_INSTRUCTIONS.get(language, "")
    q = f"{lang_instr}\n\n{question}".strip() if lang_instr else question

    route = _classify(q, model, history=history)
    if route == "TOOL":
        text = _answer_via_tool(q, model, history=history)
        return iter([text]), []
    if route == "QURAN":
        text = _answer_via_quran(q, model)
        return iter([text]), []
    if route == "DATE":
        text = _answer_via_date(q, model)
        return iter([text]), []

    return _answer_stream_with_history(q, records, matrix, embedder, model, history)


def _answer_stream_with_history(
    question: str,
    records: list[dict],
    matrix,
    embedder,
    model: str,
    history: list[dict],
):
    """RAG pipeline that includes conversation history in the Ollama prompt."""
    from rag.query import SYSTEM_PROMPT, build_context, retrieve

    chunks = retrieve(question, records, matrix, embedder)
    context = build_context(chunks)

    # System + prior turns + current question (with fresh context)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    def _tokens():
        stream = ollama.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text

    return _tokens(), chunks


# ── Interactive loop ──────────────────────────────────────────────────────────

def main():
    if not INDEX_PATH.exists():
        sys.exit(f"Index not found at {INDEX_PATH}.\nRun `python rag/ingest.py` first.")

    print("Loading index...")
    records, matrix = load_index(INDEX_PATH)
    print(f"Index loaded: {len(records)} chunks\n")

    embedder, model = load_clients()
    print(f"Model: {model}\nType 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        stream, _ = answer_stream_with_tools(user_input, records, matrix, embedder, model)
        print("\nAssistant: ", end="", flush=True)
        for token in stream:
            print(token, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
