"""
RAG Chat — with live prayer-time tool use
==========================================

Answers two kinds of questions:
  1. Knowledge questions ("What is the ISNA method?")
     → standard RAG: retrieve chunks → Ollama generates answer

  2. Live calculation questions ("When is Fajr in Toronto tomorrow?")
     → tool use: Ollama calls get_prayer_times(city, date) → PrayerService
       calculates using adhanpy → Ollama formulates the answer

No API keys required — all inference runs locally via Ollama.

Usage:
    python rag/ingest.py          # build index first
    python rag/chat.py            # interactive
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

import ollama
from rag.query import (  # noqa: E402
    INDEX_PATH, OLLAMA_MODEL, answer, answer_stream, load_clients, load_index,
)

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
    "Reply RAG for everything else (concepts, methods, app usage, how-to)."
)

_TOOL_SYSTEM = (
    "You are a prayer times assistant. "
    "The user wants to know prayer times for a specific location or date. "
    "Call get_prayer_times with the city and date from their question. "
    "If no city is mentioned, omit it (the tool will use the local location). "
    "After receiving the tool result, present the times clearly."
)


def _classify(question: str, model: str) -> str:
    """Returns 'TOOL' or 'RAG'."""
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {"role": "user", "content": question},
        ],
    )
    return "TOOL" if "TOOL" in resp["message"]["content"].upper() else "RAG"


def _answer_via_tool(question: str, model: str) -> str:
    """Call the prayer tool and return a formatted answer."""
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": _TOOL_SYSTEM},
            {"role": "user", "content": question},
        ],
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

    route = _classify(q, model)
    if route == "TOOL":
        text = _answer_via_tool(q, model)
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
