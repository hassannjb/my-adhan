"""Tests for the LLM-as-judge eval pipeline (no API keys needed)."""
from unittest.mock import MagicMock, patch

from rag.eval import judge_answer, EVAL_DATASET, JUDGE_TOOL


def _make_judge_response(accuracy, grounding, completeness, reasoning="ok"):
    """Build a mock Anthropic response that looks like a forced tool_use block."""
    tool_use_block = MagicMock()
    tool_use_block.input = {
        "accuracy": accuracy,
        "grounding": grounding,
        "completeness": completeness,
        "reasoning": reasoning,
    }
    response = MagicMock()
    response.content = [tool_use_block]
    return response


def test_judge_answer_returns_all_four_keys():
    claude = MagicMock()
    claude.messages.create.return_value = _make_judge_response(3, 3, 3)
    result = judge_answer("What is Fajr?", "reference text", "candidate text", claude)
    assert set(result.keys()) == {"accuracy", "grounding", "completeness", "reasoning"}


def test_judge_answer_passes_correct_tool_schema():
    claude = MagicMock()
    claude.messages.create.return_value = _make_judge_response(2, 2, 2)
    judge_answer("q", "ref", "cand", claude)
    call_kwargs = claude.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "score_answer"}
    assert call_kwargs["tools"][0]["name"] == "score_answer"


def test_judge_answer_scores_are_returned_as_given():
    claude = MagicMock()
    claude.messages.create.return_value = _make_judge_response(1, 2, 0, "partial answer")
    result = judge_answer("q", "ref", "cand", claude)
    assert result["accuracy"] == 1
    assert result["grounding"] == 2
    assert result["completeness"] == 0
    assert result["reasoning"] == "partial answer"


def test_eval_dataset_has_required_keys():
    for case in EVAL_DATASET:
        assert "question" in case, f"Missing 'question' in: {case}"
        assert "reference" in case, f"Missing 'reference' in: {case}"


def test_judge_tool_schema_has_required_fields():
    props = JUDGE_TOOL["input_schema"]["properties"]
    required = JUDGE_TOOL["input_schema"]["required"]
    assert set(required) == {"accuracy", "grounding", "completeness", "reasoning"}
    for field in required:
        assert field in props
