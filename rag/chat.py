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
        verse_match = _VERSE_RE.search(question)
        if verse_match:
            ayah_ref = verse_match.group(0)
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


def _classify(question: str, model: str, history: list[dict] | None = None) -> str:
    """Returns 'TOOL', 'QURAN', or 'RAG'. Includes recent history for follow-up routing."""
    # Fast keyword pre-check for unambiguous Quran signals
    if _QURAN_KEYWORDS.search(question) or _VERSE_RE.search(question):
        return "QURAN"

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
