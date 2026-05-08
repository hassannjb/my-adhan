"""
LLM-as-Judge Eval
=================
Compares two approaches to evaluating a RAG system:

  KEYWORD EVAL (chat.py --eval)
    Fast, free, deterministic.  Checks that specific strings appear in the
    answer.  Breaks if the model paraphrases correctly but uses different words.
    Example failure: "18 degrees" passes but "eighteen degrees" fails.

  LLM-AS-JUDGE (this file)
    Claude grades Claude on a 0–3 rubric per dimension.  Understands meaning,
    detects hallucinations, handles paraphrase.  Slower and costs tokens, but
    much more reliable for measuring real quality changes.

KEY TECHNIQUE — STRUCTURED OUTPUTS VIA TOOL USE:
  We need a parseable score, not a prose paragraph.  The trick: define a
  "score_answer" tool with the exact JSON schema we want, then force Claude to
  call it with tool_choice={"type": "tool", "name": "score_answer"}.  Claude
  MUST fill in the schema — it can't respond with text.  This is how production
  eval pipelines extract structured judgements from LLMs without regex hacks.

HOW TO RUN:
  python rag/eval.py                 # run evals, print report
  python rag/eval.py --verbose       # also print each answer

  Compare with keyword evals:
  python rag/chat.py --eval
"""

import argparse
import sys
from pathlib import Path

import anthropic

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))
from rag.query import INDEX_PATH, answer, load_clients, load_index

CLAUDE_JUDGE_MODEL = "claude-haiku-4-5"

# ── Eval dataset ──────────────────────────────────────────────────────────────
# Each entry: question the user might ask + the ideal reference answer.
# The reference doesn't have to be perfect prose — it just captures the key
# facts the judge checks the candidate against.

EVAL_DATASET = [
    {
        "question": "What time does Fajr prayer start?",
        "reference": (
            "Fajr starts at true astronomical dawn — when the twilight angle below "
            "the horizon is reached (typically 15–18 degrees depending on the method). "
            "It ends at sunrise."
        ),
    },
    {
        "question": "What is the difference between the ISNA and Umm al-Qura calculation methods?",
        "reference": (
            "ISNA uses a 15° angle for both Fajr and Isha. Umm al-Qura uses 18.5° for "
            "Fajr but calculates Isha as 90 minutes after Maghrib (not angle-based). "
            "Umm al-Qura is used in Saudi Arabia."
        ),
    },
    {
        "question": "How do I change the prayer calculation method in the app?",
        "reference": (
            "Click Edit Settings, select a Method from the dropdown, then click Save "
            "Settings. The app recalculates prayer times immediately."
        ),
    },
    {
        "question": "How many rakats does the Dhuhr prayer have?",
        "reference": "Dhuhr has 4 obligatory rakats. On Fridays it is replaced by Jumu'ah.",
    },
    {
        "question": "What happens to prayer times at high latitudes in summer?",
        "reference": (
            "At high latitudes the twilight may never fully disappear in summer, making "
            "angle-based Fajr and Isha calculations impossible. Several rules exist: "
            "Middle of Night, Seventh of Night, and Angle-Based capping."
        ),
    },
    {
        "question": "What does the Hanafi school say about Asr time?",
        "reference": (
            "The Hanafi school starts Asr when the shadow of an object equals twice its "
            "own length, while the standard (Shafi'i/Maliki/Hanbali) position starts "
            "Asr when the shadow equals the object's length."
        ),
    },
    {
        "question": "What API key do I need to run the AI agent?",
        "reference": (
            "The agent uses Claude by default, requiring ANTHROPIC_API_KEY. It can also "
            "use Gemini with GOOGLE_API_KEY via the --provider gemini flag."
        ),
    },
]

# ── Judge tool schema ─────────────────────────────────────────────────────────
# This is the structured output schema.  By passing it as a tool and setting
# tool_choice to force its use, Claude MUST return exactly this shape.

JUDGE_TOOL = {
    "name": "score_answer",
    "description": "Score a RAG system's answer against a reference answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "accuracy": {
                "type": "integer",
                "description": (
                    "0 = factually wrong or contradicts the reference. "
                    "1 = partially correct but missing key facts. "
                    "2 = mostly correct with minor gaps. "
                    "3 = fully accurate."
                ),
            },
            "grounding": {
                "type": "integer",
                "description": (
                    "Does the candidate invent facts that could not appear in any "
                    "reasonable Islamic prayer times knowledge base? "
                    "0 = clear hallucinations (made-up angles, invented rules, wrong numbers). "
                    "1 = plausible but unverifiable claims mixed in. "
                    "2 = nearly all claims are standard prayer knowledge. "
                    "3 = every claim is either in the reference or well-established prayer knowledge."
                ),
            },
            "completeness": {
                "type": "integer",
                "description": (
                    "0 = misses most key information from the reference. "
                    "1 = covers some points but important ones are absent. "
                    "2 = covers most points with minor omissions. "
                    "3 = covers all key points from the reference."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": "One sentence explaining the scores.",
            },
        },
        "required": ["accuracy", "grounding", "completeness", "reasoning"],
    },
}

JUDGE_SYSTEM = (
    "You are an impartial evaluator of a RAG (retrieval-augmented generation) system "
    "for Islamic prayer times. "
    "You will be given a question, a reference answer, and a candidate answer. "
    "Score using the provided tool. Rules: "
    "(1) Accuracy and completeness are measured against the reference answer. "
    "(2) Grounding measures whether the candidate invents implausible facts — "
    "do NOT penalise the candidate for adding extra correct Islamic knowledge "
    "beyond what the reference mentions, only penalise clear hallucinations or "
    "numerically wrong claims."
)


# ── Core functions ─────────────────────────────────────────────────────────────

def judge_answer(question: str, reference: str, candidate: str,
                 claude: anthropic.Anthropic) -> dict:
    """
    Ask Claude to score a candidate answer against a reference.

    Returns a dict with keys: accuracy, grounding, completeness (int 0–3), reasoning (str).

    The force-tool pattern:
      tool_choice={"type": "tool", "name": "score_answer"} means Claude MUST
      call score_answer — it has no choice.  The response.content[0] is always
      a tool_use block, so we can safely call .input on it.
    """
    response = claude.messages.create(
        model=CLAUDE_JUDGE_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM,
        tools=[JUDGE_TOOL],
        tool_choice={"type": "tool", "name": "score_answer"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Reference answer: {reference}\n\n"
                    f"Candidate answer: {candidate}"
                ),
            }
        ],
    )
    return response.content[0].input   # always a tool_use block when tool_choice is forced


def run_evals(records, matrix, voyage, claude, verbose: bool = False) -> dict:
    """Run all eval cases and return a summary dict."""
    results = []
    max_score = len(EVAL_DATASET) * 9   # 3 dimensions × 3 max × N questions

    print(f"\n{'='*62}")
    print(f"  LLM-AS-JUDGE EVAL  ({len(EVAL_DATASET)} questions, max {max_score} pts)")
    print(f"{'='*62}")

    for i, case in enumerate(EVAL_DATASET, 1):
        q = case["question"]
        ref = case["reference"]

        candidate, _ = answer(q, records, matrix, voyage, claude)
        scores = judge_answer(q, ref, candidate, claude)

        acc = scores["accuracy"]
        gnd = scores["grounding"]
        cmp = scores["completeness"]
        total = acc + gnd + cmp
        results.append(total)

        status = "✓" if total >= 7 else ("~" if total >= 4 else "✗")
        print(f"\n[{status}] Q{i}: {q}")
        print(f"     Accuracy: {acc}/3  Grounding: {gnd}/3  Completeness: {cmp}/3  → {total}/9")
        print(f"     {scores['reasoning']}")
        if verbose:
            print(f"     Answer: {candidate[:120]}{'...' if len(candidate) > 120 else ''}")

    overall = sum(results)
    pct = overall / max_score * 100
    print(f"\n{'='*62}")
    print(f"  TOTAL: {overall}/{max_score}  ({pct:.0f}%)")
    grade = "EXCELLENT" if pct >= 85 else ("GOOD" if pct >= 70 else ("NEEDS WORK" if pct >= 50 else "POOR"))
    print(f"  GRADE: {grade}")
    print(f"{'='*62}\n")

    return {"total": overall, "max": max_score, "pct": pct, "per_question": results}


def main():
    parser = argparse.ArgumentParser(description="LLM-as-judge evals for the Adhan RAG system")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each candidate answer alongside scores")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        sys.exit(f"Index not found at {INDEX_PATH}.\nRun `python rag/ingest.py` first.")

    print("Loading index...")
    records, matrix = load_index(INDEX_PATH)
    voyage, claude = load_clients()

    summary = run_evals(records, matrix, voyage, claude, verbose=args.verbose)
    sys.exit(0 if summary["pct"] >= 70 else 1)


if __name__ == "__main__":
    main()
