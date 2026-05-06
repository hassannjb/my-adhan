#!/usr/bin/env python3
"""
Multi-agent coding system. Supports Claude (default) and Gemini as backends.

Architecture:
    Orchestrator
    ├── TechLeadAgent  — reads task, implements changes, spawns helpers
    │   ├── test_writer      (spawned on demand)
    │   ├── debugger         (spawned on demand)
    │   ├── security_auditor (spawned on demand)
    │   └── researcher       (spawned on demand)
    └── CodeReviewAgent — reviews the diff, iterates with tech lead until approved

Usage:
    export ANTHROPIC_API_KEY=...          # Claude (default)
    export GOOGLE_API_KEY=...             # Gemini
    python agent.py "Fix the failing tests"
    python agent.py --provider gemini "Fix the failing tests"
    python agent.py --model claude-haiku-4-5 "Quick fix"
    python agent.py --max-rounds 5 "Add retry logic"
"""

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Provider SDKs ─────────────────────────────────────────────────────────────
try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None

try:
    from google import genai as _genai
    from google.genai import types as _gtypes
except ImportError:
    _genai = None
    _gtypes = None

# ── Config ────────────────────────────────────────────────────────────────────
REPO_PATH = Path(os.path.dirname(os.path.abspath(__file__)))

PROVIDER_CLAUDE = "claude"
PROVIDER_GEMINI = "gemini"
DEFAULT_PROVIDER  = PROVIDER_CLAUDE
DEFAULT_CLAUDE_MODEL = "claude-opus-4-7"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"

MAX_REVIEW_ROUNDS = 3
MAX_FILE_CHARS    = 12_000   # ~3 k tokens — truncate large file reads
MAX_TOOL_OUTPUT   = 4_000    # cap shell/test output sent back to the model
MAX_LOOP_TURNS    = 25       # hard ceiling on tool-call iterations per agent
CLAUDE_MAX_TOKENS = 16_384   # output token budget per Claude call

# ── ANSI ──────────────────────────────────────────────────────────────────────
_R = "\033[0m"; _B = "\033[1m"; _D = "\033[2m"
_CY = "\033[96m"; _GR = "\033[92m"; _YL = "\033[93m"
_RD = "\033[91m"; _MG = "\033[95m"


def _log(name: str, msg: str, c: str = _CY):
    print(f"\n{c}{_B}[{name}]{_R} {msg}")


def _hr(char: str = "─", w: int = 64):
    print(f"{_D}{char * w}{_R}")


# ── Retry helpers ─────────────────────────────────────────────────────────────

def _backoff_delay(err_msg: str, attempt: int) -> Optional[int]:
    """Return seconds to wait for retryable errors, None if not retryable."""
    msg = err_msg.lower()
    is_rate_limit = "429" in msg or "resource_exhausted" in msg or "rate_limit" in msg
    is_overload   = "503" in msg or "unavailable" in msg or "529" in msg or "overload" in msg
    if not is_rate_limit and not is_overload:
        return None
    if is_rate_limit:
        match = re.search(r"retrydelay.*?(\d+)s", msg)
        return int(match.group(1)) + 2 if match else 30 * (attempt + 1)
    return 15 * (2 ** attempt)   # 15 → 30 → 60 → 120 …


# ── Normalised types (provider-agnostic) ──────────────────────────────────────

@dataclass
class _FC:
    """A single function/tool call from the model."""
    id:   str    # tool_use_id (Claude) | function name (Gemini)
    name: str
    args: dict


@dataclass
class _Resp:
    """Normalised model response."""
    calls: list   # list[_FC]
    text:  str


# ── Provider chat wrappers ────────────────────────────────────────────────────

class _GeminiChat:
    """Stateful Gemini chat session."""

    def __init__(self, client, model: str, system: str, tools: list):
        config = _gtypes.GenerateContentConfig(system_instruction=system, tools=tools)
        self._chat = client.chats.create(model=model, config=config)

    def send_text(self, text: str) -> _Resp:
        return self._wrap(self._retry(text))

    def send_results(self, results: list) -> _Resp:
        """results: list of (tool_name, call_id, result_str)"""
        parts = [
            _gtypes.Part.from_function_response(name=name, response={"result": result})
            for name, _, result in results
        ]
        return self._wrap(self._retry(parts))

    def _retry(self, message, max_retries: int = 7):
        for attempt in range(max_retries):
            try:
                return self._chat.send_message(message)
            except Exception as e:
                delay = _backoff_delay(str(e), attempt)
                if delay is None:
                    raise
                label = "rate limit" if "429" in str(e) or "resource_exhausted" in str(e).lower() else "server overload"
                print(f"\n{_YL}[gemini/{label}] waiting {delay}s (attempt {attempt + 1}/{max_retries})...{_R}")
                time.sleep(delay)
        return self._chat.send_message(message)

    @staticmethod
    def _wrap(raw) -> _Resp:
        calls = [
            _FC(id=fc.name, name=fc.name, args=dict(fc.args) if fc.args else {})
            for fc in (raw.function_calls or [])
        ]
        try:
            text = raw.text or ""
        except Exception:
            text = ""
        return _Resp(calls=calls, text=text)


class _ClaudeChat:
    """Stateful Claude session (manual message history)."""

    def __init__(self, client, model: str, system: str, tools: list):
        self._client   = client
        self._model    = model
        self._system   = system
        self._tools    = tools
        self._messages = []

    def send_text(self, text: str) -> _Resp:
        self._messages.append({"role": "user", "content": text})
        return self._call()

    def send_results(self, results: list) -> _Resp:
        """results: list of (tool_name, call_id, result_str)"""
        self._messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": cid, "content": result}
                for _, cid, result in results
            ],
        })
        return self._call()

    def _call(self, max_retries: int = 7) -> _Resp:
        for attempt in range(max_retries):
            try:
                raw = self._client.messages.create(
                    model=self._model,
                    system=self._system,
                    tools=self._tools,
                    messages=self._messages,
                    max_tokens=CLAUDE_MAX_TOKENS,
                )
                break
            except Exception as e:
                delay = _backoff_delay(str(e), attempt)
                if delay is None:
                    raise
                label = "rate limit" if "429" in str(e) or "rate_limit" in str(e).lower() else "server overload"
                print(f"\n{_YL}[claude/{label}] waiting {delay}s (attempt {attempt + 1}/{max_retries})...{_R}")
                time.sleep(delay)
        else:
            raw = self._client.messages.create(
                model=self._model, system=self._system,
                tools=self._tools, messages=self._messages,
                max_tokens=CLAUDE_MAX_TOKENS,
            )

        self._messages.append({"role": "assistant", "content": raw.content})

        calls, text = [], ""
        for block in raw.content:
            if block.type == "tool_use":
                calls.append(_FC(id=block.id, name=block.name, args=block.input or {}))
            elif block.type == "text":
                text += block.text
        return _Resp(calls=calls, text=text)


# ── Executor ──────────────────────────────────────────────────────────────────

class Executor:
    """All filesystem, shell, and git operations."""

    def __init__(self, repo: Path):
        self.repo = repo

    def read_file(self, path: str) -> str:
        p = self.repo / path
        if not p.exists():
            return f"ERROR: file not found: {path}"
        try:
            text = p.read_text()
            if len(text) > MAX_FILE_CHARS:
                kept = MAX_FILE_CHARS
                text = text[:kept] + f"\n... [{len(text) - kept} chars truncated]"
            return text
        except Exception as e:
            return f"ERROR reading {path}: {e}"

    def write_file(self, path: str, content: str) -> str:
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {path} ({len(content.splitlines())} lines)"

    def list_files(self, pattern: str = "**/*.py") -> str:
        files = sorted(
            str(f.relative_to(self.repo))
            for f in self.repo.glob(pattern)
            if f.is_file() and ".git" not in str(f)
        )
        return "\n".join(files) if files else "(none)"

    def run_shell(self, cmd: str) -> str:
        r = subprocess.run(cmd, shell=True, cwd=self.repo,
                           capture_output=True, text=True, timeout=90)
        out = (r.stdout + r.stderr).strip() or f"(exit {r.returncode})"
        return out[:MAX_TOOL_OUTPUT] + "\n... [truncated]" if len(out) > MAX_TOOL_OUTPUT else out

    def run_tests(self) -> str:
        r = subprocess.run([sys.executable, "-m", "pytest", "--tb=short", "-q"],
                           cwd=self.repo, capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip() or "(no output)"
        return out[:MAX_TOOL_OUTPUT] + "\n... [truncated]" if len(out) > MAX_TOOL_OUTPUT else out

    def git_diff(self) -> str:
        r = subprocess.run(["git", "diff", "HEAD"], cwd=self.repo,
                           capture_output=True, text=True)
        return r.stdout.strip() or "(no uncommitted changes)"

    def git_status(self) -> str:
        r = subprocess.run(["git", "status", "--short"], cwd=self.repo,
                           capture_output=True, text=True)
        return r.stdout.strip() or "(clean)"

    def git_commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.repo)
        r = subprocess.run(["git", "commit", "-m", message],
                           cwd=self.repo, capture_output=True, text=True)
        return (r.stdout + r.stderr).strip()


# ── System prompts ────────────────────────────────────────────────────────────

_TECH_LEAD_SYS = """
You are a senior tech lead implementing tasks in a Python codebase.

Workflow:
1. list_files() to orient yourself
2. read_file() relevant files before changing anything
3. write_file() to implement — no markdown fences in .py files, ever
4. run_tests() after every change — fix failures before continuing
5. spawn_agent() for specialist help: test_writer, debugger, security_auditor, researcher
6. done() with a one-line summary per file changed

Rules: minimal changes only · no TODO stubs · tests must be green before done()
""".strip()

_REVIEWER_SYS = """
You are a strict senior code reviewer. Your only exit is submit_review().

Steps: read_file() for context → run_tests() → submit_review()

Approve only when: task is complete · code is readable and minimal · new behaviour is tested · no regressions · no markdown fences in .py files · no hardcoded secrets.

On rejection list precise, actionable blocking issues.
""".strip()

_SUB_SYS: dict[str, str] = {
    "test_writer": """
Pytest specialist. Write comprehensive, passing tests.
1. read_file() the target module
2. write_file() to tests/test_<module>.py — no markdown fences
3. run_tests() — fix until green
4. done() listing what is now covered
""".strip(),

    "debugger": """
Debugging specialist. Fix failures surgically.
1. read_file() failing file and imports
2. run_tests() to see the exact error
3. write_file() the minimal fix — never suppress errors or weaken assertions
4. run_tests() to confirm green
5. done() with root cause and fix
""".strip(),

    "security_auditor": """
Security engineer. Audit for vulnerabilities.
1. read_file() the specified files
2. Check: injection, path traversal, insecure I/O, hardcoded secrets, unsafe eval/exec
3. done() — one finding per line: file · HIGH/MED/LOW · description · remediation
""".strip(),

    "researcher": """
Research agent. Answer one focused question about the codebase.
1. read_file() relevant files
2. done() with a factual answer citing file paths
""".strip(),
}


# ── Claude tool schemas ───────────────────────────────────────────────────────

def _cs(name: str, desc: str, props: dict, required: list = None) -> dict:
    return {
        "name": name,
        "description": desc,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required if required is not None else list(props.keys()),
        },
    }


_CLAUDE_TECH_SCHEMAS = [
    _cs("read_file",  "Read a repository file.",
        {"path": {"type": "string"}}),
    _cs("write_file", "Write or overwrite a file. No markdown fences in .py content.",
        {"path": {"type": "string"}, "content": {"type": "string"}}),
    _cs("list_files", "List files matching a glob pattern.",
        {"pattern": {"type": "string"}}, required=[]),
    _cs("run_shell",  "Run a shell command (not for tests).",
        {"cmd": {"type": "string"}}),
    _cs("run_tests",  "Run the full pytest suite.", {}, required=[]),
    _cs("git_status", "Show modified or untracked files.", {}, required=[]),
    _cs("done",       "Signal task completion. Only call when tests pass.",
        {"summary": {"type": "string"}}),
    _cs("spawn_agent",
        "Delegate to a specialist: test_writer, debugger, security_auditor, researcher.",
        {"agent_type": {"type": "string"}, "task": {"type": "string"}}),
]

_CLAUDE_REVIEWER_SCHEMAS = [
    _cs("read_file",  "Read a file for review context.",
        {"path": {"type": "string"}}),
    _cs("run_tests",  "Run the test suite.", {}, required=[]),
    _cs("submit_review", "Submit the final review. Your only exit.",
        {
            "approved":    {"type": "boolean"},
            "issues":      {"type": "array", "items": {"type": "string"}},
            "suggestions": {"type": "array", "items": {"type": "string"}},
            "summary":     {"type": "string"},
        }),
]


# ── Tool factories ────────────────────────────────────────────────────────────

def _make_tech_tools(ex: Executor, provider: str, spawner=None):
    """Return (provider_tools, dispatch_dict) for the tech lead."""

    def read_file(path: str) -> str:
        """Read the full contents of a repository file."""
        return ex.read_file(path)

    def write_file(path: str, content: str) -> str:
        """Write or overwrite a file. Never include markdown fences in Python content."""
        return ex.write_file(path, content)

    def list_files(pattern: str = "**/*.py") -> str:
        """List repository files matching a glob pattern."""
        return ex.list_files(pattern)

    def run_shell(cmd: str) -> str:
        """Run a shell command such as pip install. Not for running tests."""
        return ex.run_shell(cmd)

    def run_tests() -> str:
        """Run the full pytest test suite. Call after every code change."""
        return ex.run_tests()

    def git_status() -> str:
        """Show which files have been modified or are untracked."""
        return ex.git_status()

    def done(summary: str) -> str:
        """Signal task completion. Only call when tests pass."""
        return "acknowledged"

    non_terminal = [read_file, write_file, list_files, run_shell, run_tests, git_status]
    dispatch = {fn.__name__: fn for fn in non_terminal}

    if spawner:
        def spawn_agent(agent_type: str, task: str) -> str:
            """Delegate to a specialist agent."""
            return spawner(agent_type, task)
        dispatch["spawn_agent"] = spawn_agent

    if provider == PROVIDER_GEMINI:
        tools = non_terminal + [done]
        if spawner:
            tools.append(dispatch["spawn_agent"])
        return tools, dispatch
    else:
        schemas = [s for s in _CLAUDE_TECH_SCHEMAS if s["name"] != "spawn_agent" or spawner]
        return schemas, dispatch


def _make_reviewer_tools(ex: Executor, provider: str):
    """Return (provider_tools, dispatch_dict) for the code reviewer."""

    def read_file(path: str) -> str:
        """Read a file for additional review context."""
        return ex.read_file(path)

    def run_tests() -> str:
        """Run the test suite to verify the implementation is correct."""
        return ex.run_tests()

    def submit_review(approved: bool, issues: list, suggestions: list, summary: str) -> str:
        """Submit the final review decision."""
        return "acknowledged"

    dispatch = {"read_file": read_file, "run_tests": run_tests}

    if provider == PROVIDER_GEMINI:
        return [read_file, run_tests, submit_review], dispatch
    else:
        return _CLAUDE_REVIEWER_SCHEMAS, dispatch


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    """Provider-agnostic agentic loop. Runs until a terminal tool is called."""

    _TERMINAL = {"done", "submit_review"}

    def __init__(
        self,
        name:     str,
        system:   str,
        tools,            # list of Python fns (Gemini) or list of schema dicts (Claude)
        dispatch: dict,
        model:    str,
        provider: str,
        client,
        color:    str = _CY,
    ):
        self.name     = name
        self.color    = color
        self.dispatch = dispatch
        self._system  = system
        self._tools   = tools
        self._model   = model
        self._provider = provider
        self._client  = client
        self._chat: Optional[object] = None   # _GeminiChat | _ClaudeChat

    def _new_chat(self):
        if self._provider == PROVIDER_GEMINI:
            return _GeminiChat(self._client, self._model, self._system, self._tools)
        return _ClaudeChat(self._client, self._model, self._system, self._tools)

    def _log(self, msg: str):
        _log(self.name, msg, self.color)

    def _call(self, name: str, args: dict) -> str:
        preview = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
        self._log(f"{_D}→ {name}({preview}){_R}")
        fn = self.dispatch.get(name)
        if fn is None:
            return f"ERROR: unknown tool '{name}'"
        try:
            result = fn(**args)
            out = str(result) if result is not None else ""
            if name == "run_tests" and out:
                print(f"  {_D}{out[:500]}{_R}")
            return out
        except Exception as e:
            return f"ERROR executing {name}: {e}"

    def _loop(self, resp: _Resp) -> dict:
        """Drive the tool-calling loop until a terminal call or MAX_LOOP_TURNS."""
        for _ in range(MAX_LOOP_TURNS):
            if not resp.calls:
                self._log(f"{_D}(end_turn){_R}")
                return {"summary": resp.text}

            results  = []   # (name, call_id, result_str)
            terminal = None

            for fc in resp.calls:
                if fc.name in self._TERMINAL:
                    terminal = fc.args
                    self._log(f"{_GR}✓ {fc.name}{_R}")
                    results.append((fc.name, fc.id, "acknowledged"))
                else:
                    result = self._call(fc.name, fc.args)
                    results.append((fc.name, fc.id, result))

            resp = self._chat.send_results(results)

            if terminal is not None:
                return terminal

        self._log(f"{_YL}(max turns {MAX_LOOP_TURNS} reached — stopping){_R}")
        return {"summary": "max turns reached without terminal call"}

    def run(self, prompt: str) -> dict:
        """Start a fresh session."""
        self._chat = self._new_chat()
        self._log("Starting...")
        resp = self._chat.send_text(prompt)
        return self._loop(resp)

    def send(self, message: str) -> dict:
        """Continue the existing session (tech lead feedback loop)."""
        resp = self._chat.send_text(message)
        return self._loop(resp)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """Drives the full tech-lead → code-review loop."""

    def __init__(
        self,
        repo:       Path,
        client,
        provider:   str = DEFAULT_PROVIDER,
        model_name: str = None,
        max_rounds: int = MAX_REVIEW_ROUNDS,
    ):
        self.repo      = repo
        self.client    = client
        self.provider  = provider
        self.model     = model_name or (
            DEFAULT_CLAUDE_MODEL if provider == PROVIDER_CLAUDE else DEFAULT_GEMINI_MODEL
        )
        self.max_rounds = max_rounds
        self.ex         = Executor(repo)
        self._lead: Optional[Agent] = None

    def _spawn(self, agent_type: str, task: str) -> str:
        system = _SUB_SYS.get(agent_type)
        if not system:
            return f"ERROR: unknown agent_type '{agent_type}'. Valid: {sorted(_SUB_SYS)}"

        _log("Orchestrator", f"Spawning {agent_type}...", _MG)
        tools, dispatch = _make_tech_tools(self.ex, provider=self.provider, spawner=None)
        agent = Agent(
            name=agent_type.replace("_", " ").title(),
            system=system, tools=tools, dispatch=dispatch,
            model=self.model, provider=self.provider, client=self.client, color=_MG,
        )
        result = agent.run(task)
        return result.get("summary", str(result))

    def run(self, prompt: str):
        _log("Orchestrator", f"Task: {prompt}  [{self.provider} / {self.model}]", _YL)
        _hr("═")

        # ── Phase 1: implementation ───────────────────────────────────────────
        tools, dispatch = _make_tech_tools(self.ex, provider=self.provider, spawner=self._spawn)
        self._lead = Agent(
            name="Tech Lead", system=_TECH_LEAD_SYS,
            tools=tools, dispatch=dispatch,
            model=self.model, provider=self.provider, client=self.client, color=_CY,
        )
        impl = self._lead.run(
            f"Repository files:\n{self.ex.list_files()}\n\n"
            f"Task: {prompt}\n\nRead relevant files first, then implement."
        )
        _log("Tech Lead", f"Done. {impl.get('summary', '')[:200]}", _CY)

        # ── Phase 2: review loop ──────────────────────────────────────────────
        for rnd in range(1, self.max_rounds + 1):
            _hr()
            _log("Orchestrator", f"Review round {rnd}/{self.max_rounds}", _YL)

            r_tools, r_dispatch = _make_reviewer_tools(self.ex, provider=self.provider)
            reviewer = Agent(
                name="Code Reviewer", system=_REVIEWER_SYS,
                tools=r_tools, dispatch=r_dispatch,
                model=self.model, provider=self.provider, client=self.client, color=_GR,
            )
            verdict = reviewer.run(
                f"Task:\n{prompt}\n\nGit diff:\n{self.ex.git_diff()}\n\n"
                "Review thoroughly. Read files for context if needed. "
                "Run the tests. Then call submit_review() with your verdict."
            )

            approved    = verdict.get("approved", False)
            issues      = list(verdict.get("issues", []))
            suggestions = list(verdict.get("suggestions", []))
            summary     = verdict.get("summary", "")

            _log("Code Reviewer",
                 f"{_GR}✅ APPROVED{_R}" if approved else f"{_RD}❌ CHANGES REQUESTED{_R}")
            if summary:
                print(f"  {summary}")
            if issues:
                print(f"\n{_RD}  Blocking issues:{_R}")
                for i, iss in enumerate(issues, 1):
                    print(f"  {i}. {iss}")
            if suggestions:
                print(f"\n{_YL}  Suggestions:{_R}")
                for s in suggestions:
                    print(f"  • {s}")

            if approved:
                _log("Orchestrator", "Committing approved changes...", _GR)
                msg = (f"ai/agent: {prompt[:70]}\n\n"
                       f"Implemented by TechLead, approved by CodeReviewer in {rnd} round(s).")
                print(f"  {self.ex.git_commit(msg)}")
                _log("Orchestrator", "✅ Done.", _GR)
                return

            if rnd < self.max_rounds:
                _log("Tech Lead", "Addressing review feedback...", _CY)
                feedback = (
                    "Reviewer rejected. Fix these blocking issues:\n\n"
                    + "\n".join(f"{i + 1}. {iss}" for i, iss in enumerate(issues))
                    + f"\n\nSummary: {summary}\n\n"
                    "Fix each issue, run_tests() to verify, then call done() again."
                )
                impl = self._lead.send(feedback)

        _log("Orchestrator", "Max review rounds reached — committing.", _YL)
        self.ex.git_commit(f"ai/agent: {prompt[:70]} (pending review)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Multi-agent coding assistant (TechLead + CodeReview loop)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python agent.py 'Fix the failing tests'\n"
            "  python agent.py --provider gemini 'Refactor gui_clock.py'\n"
            "  python agent.py --model claude-haiku-4-5 'Quick fix'\n"
            "  python agent.py --max-rounds 5 'Add retry logic'\n"
        ),
    )
    ap.add_argument("prompt", help="Task for the agents to work on")
    ap.add_argument(
        "--provider", choices=[PROVIDER_CLAUDE, PROVIDER_GEMINI],
        default=DEFAULT_PROVIDER,
        help=f"LLM provider (default: {DEFAULT_PROVIDER})",
    )
    ap.add_argument(
        "--model", default=None,
        help=(f"Model ID override. Defaults: Claude={DEFAULT_CLAUDE_MODEL}, "
              f"Gemini={DEFAULT_GEMINI_MODEL}"),
    )
    ap.add_argument("--repo", default=str(REPO_PATH),
                    help="Repository root (default: directory of this script)")
    ap.add_argument("--max-rounds", type=int, default=MAX_REVIEW_ROUNDS,
                    help=f"Max review rounds before force-committing (default: {MAX_REVIEW_ROUNDS})")
    args = ap.parse_args()

    if args.provider == PROVIDER_CLAUDE:
        if _anthropic is None:
            print(f"{_RD}ERROR: anthropic package not installed.  Run: pip install anthropic{_R}")
            sys.exit(1)
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print(f"{_RD}ERROR: ANTHROPIC_API_KEY is not set.{_R}")
            sys.exit(1)
        client = _anthropic.Anthropic(api_key=key)
    else:
        if _genai is None:
            print(f"{_RD}ERROR: google-genai package not installed.  Run: pip install google-genai{_R}")
            sys.exit(1)
        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            print(f"{_RD}ERROR: GOOGLE_API_KEY is not set.{_R}")
            sys.exit(1)
        client = _genai.Client(api_key=key)

    Orchestrator(
        repo=Path(args.repo),
        client=client,
        provider=args.provider,
        model_name=args.model,
        max_rounds=args.max_rounds,
    ).run(args.prompt)


if __name__ == "__main__":
    main()
