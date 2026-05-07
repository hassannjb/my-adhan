"""
RAG Chat CLI
============
Interactive Q&A over the Adhan Clock docs using Voyage AI + Claude.

Usage:
    # First, build the index:
    python rag/ingest.py

    # Then chat:
    python rag/chat.py

    # Or run the built-in evals:
    python rag/chat.py --eval

WHY EVALS?
  An eval is the most underrated AI engineering skill.  Before you ship any RAG
  change (different chunk size, different top_k, different model), you need a
  way to measure whether it got better or worse.  The simplest eval is just a
  set of (question, expected_keywords) pairs: check that keywords you expect
  actually appear in the answer.  Real evals use LLM-as-judge or exact match
  depending on the task.
"""

import argparse
import sys
from pathlib import Path

from query import INDEX_PATH, answer, load_clients, load_index

# ── Built-in evals ────────────────────────────────────────────────────────────
# Format: (question, list_of_keywords_that_must_appear_in_answer)
# Keywords are case-insensitive substring matches.  Simple but fast.
EVALS = [
    (
        "What time does Fajr prayer start?",
        ["dawn", "twilight", "sunrise", "angle"],
    ),
    (
        "What is the difference between ISNA and Umm al-Qura methods?",
        ["15", "18.5", "90 minutes", "saudi"],
    ),
    (
        "How do I change the calculation method in the app?",
        ["edit settings", "dropdown", "save settings"],
    ),
    (
        "How many rakats does Dhuhr have?",
        ["4"],
    ),
    (
        "What happens at high latitudes?",
        ["latitude", "twilight", "midnight", "summer"],
    ),
]


def run_evals(records, matrix, voyage, claude):
    print("=" * 60)
    print("RUNNING EVALS")
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


def interactive_loop(records, matrix, voyage, claude):
    print("Adhan Clock Assistant (RAG)")
    print("Type your question and press Enter.  Ctrl+C or 'quit' to exit.")
    print("Prefix with 'debug:' to see which chunks were retrieved.\n")
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

        resp, chunks = answer(question, records, matrix, voyage, claude)
        print(f"\nAssistant: {resp}\n")

        if debug:
            print("── Retrieved chunks ──")
            for c in chunks:
                print(f"  [{c['score']:.3f}] {c['source']} chunk {c['chunk_id']}: "
                      f"{c['text'][:80].replace(chr(10), ' ')}...")
            print()


def main():
    parser = argparse.ArgumentParser(description="Adhan Clock RAG assistant")
    parser.add_argument("--eval", action="store_true", help="Run built-in evals and exit")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        sys.exit(f"Index not found at {INDEX_PATH}.\nRun `python rag/ingest.py` first.")

    print("Loading index...")
    records, matrix = load_index(INDEX_PATH)
    print(f"Index loaded: {len(records)} chunks from "
          f"{len(set(r['source'] for r in records))} document(s).\n")

    voyage, claude = load_clients()

    if args.eval:
        ok = run_evals(records, matrix, voyage, claude)
        sys.exit(0 if ok else 1)
    else:
        interactive_loop(records, matrix, voyage, claude)


if __name__ == "__main__":
    main()
