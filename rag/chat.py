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


_CLASSIFIER_SYSTEM = (
    "Classify the user's question. Reply with exactly one word.\n"
    "Reply TOOL if they are asking for actual prayer times for a specific city, "
    "place, or date (e.g. 'when is Fajr in Toronto', 'prayer times tomorrow').\n"
    "Reply RAG for everything else (concepts, methods, app usage, how-to)."
)

_TOOL_SYSTEM = (
    "You are a prayer times assistant. "
    "The user wants to know prayer times for a specific location or date. "
    "Call get_prayer_times with the city and date extracted from their question. "
    "If no city is mentioned, omit it (the tool will use the local location). "
    "After receiving the tool result, present the times clearly."
)

_RAG_SYSTEM = (
    "You are a helpful assistant for the Adhan Clock app — an Islamic prayer times application. "
    "Answer using ONLY the context provided. "
    "If the context does not contain enough information, say so clearly. "
    "Be concise and accurate."
)


def _classify(question: str, claude) -> str:
    """Returns 'TOOL' or 'RAG'. Costs ~10 output tokens."""
    from query import CLAUDE_MODEL
    resp = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=5,
        system=_CLASSIFIER_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    return "TOOL" if "TOOL" in resp.content[0].text.upper() else "RAG"


def _answer_via_tool(question: str, claude) -> str:
    """Force-call the prayer tool and return a formatted answer."""
    from query import CLAUDE_MODEL

    # Step 1: force Claude to fill in the tool arguments from the question
    resp = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        system=_TOOL_SYSTEM,
        tools=[PRAYER_TOOL],
        tool_choice={"type": "tool", "name": "get_prayer_times"},
        messages=[{"role": "user", "content": question}],
    )

    tool_call = next(b for b in resp.content if b.type == "tool_use")
    city = tool_call.input.get("city")
    date_str = tool_call.input.get("date", "today")
    tool_result = _run_prayer_tool(city, date_str)

    # Step 2: ask Claude to present the result naturally
    final = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=_TOOL_SYSTEM,
        tools=[PRAYER_TOOL],
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": resp.content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": tool_result,
                    }
                ],
            },
        ],
    )
    return final.content[0].text


def _answer_via_rag(question: str, records, matrix, voyage, claude) -> str:
    """Standard RAG: retrieve chunks → answer with context."""
    from query import CLAUDE_MODEL, build_context, retrieve
    chunks = retrieve(question, records, matrix, voyage)
    context = build_context(chunks)
    resp = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=_RAG_SYSTEM,
        messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}],
    )
    return resp.content[0].text


def answer_with_tools(
    question: str,
    records: list[dict],
    matrix,
    voyage,
    claude,
) -> tuple[str, str]:
    """
    Route question to the right backend then return (answer, source).

    WHY CLASSIFY FIRST?
      Mixing RAG context with a tool instruction confuses the model: it reads
      the docs (which explain HOW times are calculated), concludes it has
      enough conceptual information, and never calls the tool.  Routing
      BEFORE loading context keeps each path clean and unambiguous.
    """
    route = _classify(question, claude)
    if route == "TOOL":
        return _answer_via_tool(question, claude), "tool"
    return _answer_via_rag(question, records, matrix, voyage, claude), "rag"


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
