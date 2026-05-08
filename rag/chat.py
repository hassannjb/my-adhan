"""
RAG Chat CLI — with live prayer-time tool use
=============================================

Answers two kinds of questions:
  1. Knowledge questions ("What is the ISNA method?")
     → standard RAG: retrieve chunks → Claude generates answer

  2. Live calculation questions ("When is Fajr in Toronto tomorrow?")
     → tool use: Claude calls get_prayer_times(city, date) → PrayerService
       calculates using adhanpy → Claude formulates the answer

The two flows are combined in one loop.  Claude decides which to use.

WHY TOOL USE HERE?
  RAG retrieves facts that were written down.  Tool use executes functions.
  Prayer times for a specific city on a future date can't be in any document
  — they must be calculated at query time.  This is the classic pattern:
  use RAG for "what" knowledge, use tools for "compute on demand".

Usage:
    python rag/ingest.py          # build index first
    python rag/chat.py            # interactive
    python rag/chat.py --eval     # keyword evals
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

from query import INDEX_PATH, answer, answer_stream, load_clients, load_index  # noqa: E402

# ── Prayer-time tool definition ───────────────────────────────────────────────

PRAYER_TOOL = {
    "name": "get_prayer_times",
    "description": (
        "Calculate prayer times for a city on a specific date. "
        "Use this whenever the user asks about prayer times for a named city "
        "or a relative date like 'today', 'tomorrow', or 'yesterday'. "
        "Do NOT use this for general questions about how prayer times work."
    ),
    "input_schema": {
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
}


def _run_prayer_tool(city: str | None, date_str: str) -> str:
    from services.prayer_service import PrayerService
    svc = PrayerService()
    return svc.format_answer(city=city, date_str=date_str)


def answer_with_tools(
    question: str,
    records: list[dict],
    matrix,
    voyage,
    claude,
) -> tuple[str, str]:
    """
    Single-turn answer that uses either RAG or the prayer-time tool.

    Returns (answer_text, source) where source is "rag" or "tool".
    """
    import anthropic
    import numpy as np
    from query import CLAUDE_MODEL, SYSTEM_PROMPT, build_context, retrieve

    chunks = retrieve(question, records, matrix, voyage)
    context = build_context(chunks)

    system = (
        f"{SYSTEM_PROMPT}\n\n"
        "You also have access to a get_prayer_times tool for calculating actual prayer "
        "times for any city. Use it whenever the user asks for specific prayer times."
    )

    messages = [
        {
            "role": "user",
            "content": f"Context from knowledge base:\n{context}\n\nQuestion: {question}",
        }
    ]

    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=system,
        tools=[PRAYER_TOOL],
        messages=messages,
    )

    # If Claude decided to call the prayer tool, execute it and continue
    if response.stop_reason == "tool_use":
        tool_call = next(b for b in response.content if b.type == "tool_use")
        city = tool_call.input.get("city")
        date_str = tool_call.input.get("date", "today")
        tool_result = _run_prayer_tool(city, date_str)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": tool_result,
                }
            ],
        })

        final = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system,
            tools=[PRAYER_TOOL],
            messages=messages,
        )
        return final.content[0].text, "tool"

    return response.content[0].text, "rag"


# ── Built-in keyword evals ────────────────────────────────────────────────────

EVALS = [
    ("What time does Fajr prayer start?", ["dawn", "twilight", "sunrise", "angle"]),
    ("What is the difference between ISNA and Umm al-Qura methods?",
     ["15", "18.5", "90 minutes", "saudi"]),
    ("How do I change the calculation method in the app?",
     ["edit settings", "dropdown", "save settings"]),
    ("How many rakats does Dhuhr have?", ["4"]),
    ("What happens at high latitudes?", ["latitude", "twilight", "midnight", "summer"]),
]


def run_evals(records, matrix, voyage, claude):
    print("=" * 60)
    print("RUNNING KEYWORD EVALS")
    print("=" * 60)
    passed = 0
    for question, keywords in EVALS:
        resp, chunks = answer(question, records, matrix, voyage, claude)
        resp_lower = resp.lower()
        missing = [kw for kw in keywords if kw.lower() not in resp_lower]
        ok = len(missing) == 0
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] {question}")
        if not ok:
            print(f"  Missing keywords: {missing}")
            print(f"  Answer: {resp[:200]}...")
        else:
            passed += 1
    print(f"\n{passed}/{len(EVALS)} evals passed.")
    return passed == len(EVALS)


# ── Interactive loop ──────────────────────────────────────────────────────────

def interactive_loop(records, matrix, voyage, claude):
    print("Adhan Clock Assistant")
    print("Answers general prayer questions (RAG) and calculates prayer times")
    print("for any city (tool use).  Try: 'When is Fajr in Toronto tomorrow?'")
    print("Prefix with 'debug:' to see retrieved chunks.  'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        debug = user_input.lower().startswith("debug:")
        question = user_input[6:].strip() if debug else user_input

        if debug:
            # Debug mode: bypass tool use, show retrieved chunks
            stream, chunks = answer_stream(question, records, matrix, voyage, claude)
            print("\nAssistant: ", end="", flush=True)
            for token in stream:
                print(token, end="", flush=True)
            print("\n")
            print("── Retrieved chunks ──")
            for c in chunks:
                print(f"  [{c['score']:.3f}] {c['source']} chunk {c['chunk_id']}: "
                      f"{c['text'][:80].replace(chr(10), ' ')}...")
            print()
        else:
            resp, source = answer_with_tools(question, records, matrix, voyage, claude)
            tag = "[tool]" if source == "tool" else "[rag]"
            print(f"\nAssistant {tag}: {resp}\n")


def main():
    parser = argparse.ArgumentParser(description="Adhan Clock assistant")
    parser.add_argument("--eval", action="store_true", help="Run keyword evals and exit")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        sys.exit(f"Index not found at {INDEX_PATH}.\nRun `python rag/ingest.py` first.")

    print("Loading index...")
    records, matrix = load_index(INDEX_PATH)
    print(f"Index loaded: {len(records)} chunks, "
          f"{len(set(r['source'] for r in records))} document(s).\n")

    voyage, claude = load_clients()

    if args.eval:
        ok = run_evals(records, matrix, voyage, claude)
        sys.exit(0 if ok else 1)
    else:
        interactive_loop(records, matrix, voyage, claude)


if __name__ == "__main__":
    main()
