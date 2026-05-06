#!/usr/bin/env python3
"""
Multi-agent coding system powered by Gemini.

Architecture:
    Orchestrator
    ├── TechLeadAgent  — reads task, implements changes, spawns helpers
    │   ├── test_writer      (spawned on demand)
    │   ├── debugger         (spawned on demand)
    │   ├── security_auditor (spawned on demand)
    │   └── researcher       (spawned on demand)
    └── CodeReviewAgent — reviews the diff, iterates with tech lead until approved

Usage:
    export GOOGLE_API_KEY=...
    python agent.py "Fix the failing tests"
    python agent.py --max-rounds 5 "Add retry logic to updateAzaanTimers"
    python agent.py --model gemini-2.0-flash "Refactor gui_clock.py"
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────
REPO_PATH = Path(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
MAX_REVIEW_ROUNDS = 3
MAX_FILE_CHARS = 12_000   # ~3 k tokens — truncate large file reads
MAX_TOOL_OUTPUT = 4_000   # cap shell/test output sent back to the model
MAX_LOOP_TURNS = 25       # hard ceiling on tool-call iterations per agent

# ── ANSI ──────────────────────────────────────────────────────────────────────
_R = "\033[0m"; _B = "\033[1m"; _D = "\033[2m"
_CY = "\033[96m"; _GR = "\033[92m"; _YL = "\033[93m"
_RD = "\033[91m"; _MG = "\033[95m"


def _log(name: str, msg: str, c: str = _CY):
    print(f"\n{c}{_B}[{name}]{_R} {msg}")


def _hr(char: str = "─", w: int = 64):
    print(f"{_D}{char * w}{_R}")


def _send_with_retry(chat, message, max_retries: int = 5):
    """Send a message, sleeping and retrying on 429 rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except Exception as e:
            msg = str(e)
            if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
                raise
            # Extract retry delay from the error message if present
            match = re.search(r"retryDelay.*?(\d+)s", msg)
            delay = int(match.group(1)) + 2 if match else 30 * (attempt + 1)
            print(f"\n{_YL}[rate limit] waiting {delay}s before retry {attempt + 1}/{max_retries}...{_R}")
            time.sleep(delay)
    return chat.send_message(message)  # final attempt, let it raise


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
                text = text[:kept] + f"\n... [{len(text) - kept} chars truncated — use a narrower read or ask for a specific section]"
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
        r = subprocess.run(
            cmd, shell=True, cwd=self.repo,
            capture_output=True, text=True, timeout=90,
        )
        out = (r.stdout + r.stderr).strip() or f"(exit {r.returncode})"
        return out[:MAX_TOOL_OUTPUT] + "\n... [truncated]" if len(out) > MAX_TOOL_OUTPUT else out

    def run_tests(self) -> str:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=short", "-q"],
            cwd=self.repo, capture_output=True, text=True, timeout=120,
        )
        out = (r.stdout + r.stderr).strip() or "(no output)"
        return out[:MAX_TOOL_OUTPUT] + "\n... [truncated]" if len(out) > MAX_TOOL_OUTPUT else out

    def git_diff(self) -> str:
        r = subprocess.run(
            ["git", "diff", "HEAD"], cwd=self.repo, capture_output=True, text=True,
        )
        return r.stdout.strip() or "(no uncommitted changes)"

    def git_status(self) -> str:
        r = subprocess.run(
            ["git", "status", "--short"], cwd=self.repo, capture_output=True, text=True,
        )
        return r.stdout.strip() or "(clean)"

    def git_commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.repo)
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.repo, capture_output=True, text=True,
        )
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


# ── Tool factories ────────────────────────────────────────────────────────────

def _make_tech_tools(ex: Executor, spawner=None):
    """Return (tools_list, dispatch_dict) for the tech lead."""

    def read_file(path: str) -> str:
        """Read the full contents of a repository file."""
        return ex.read_file(path)

    def write_file(path: str, content: str) -> str:
        """Write or overwrite a file. Never include markdown fences in Python content."""
        return ex.write_file(path, content)

    def list_files(pattern: str = "**/*.py") -> str:
        """List repository files matching a glob pattern e.g. **/*.py or tests/*.py."""
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
        """Signal task completion. Only call when tests pass. summary: every file changed and why."""
        return "acknowledged"

    tools = [read_file, write_file, list_files, run_shell, run_tests, git_status, done]
    dispatch = {fn.__name__: fn for fn in [read_file, write_file, list_files, run_shell, run_tests, git_status]}

    if spawner:
        def spawn_agent(agent_type: str, task: str) -> str:
            """Delegate to a specialist agent. agent_type: test_writer, debugger, security_auditor, or researcher."""
            return spawner(agent_type, task)
        tools.append(spawn_agent)
        dispatch["spawn_agent"] = spawn_agent

    return tools, dispatch


def _make_reviewer_tools(ex: Executor):
    """Return (tools_list, dispatch_dict) for the code reviewer."""

    def read_file(path: str) -> str:
        """Read a file for additional review context."""
        return ex.read_file(path)

    def run_tests() -> str:
        """Run the test suite to verify the implementation is correct."""
        return ex.run_tests()

    def submit_review(approved: bool, issues: list[str], suggestions: list[str], summary: str) -> str:
        """Submit the final review decision. approved: True=ready to merge. issues: blocking problems. suggestions: non-blocking improvements. summary: overall assessment."""
        return "acknowledged"

    tools = [read_file, run_tests, submit_review]
    dispatch = {fn.__name__: fn for fn in [read_file, run_tests]}
    return tools, dispatch


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    """
    A stateful Gemini conversation with a function-calling loop.
    Runs until the model calls a terminal tool (done / submit_review).
    """

    _TERMINAL = {"done", "submit_review"}

    def __init__(
        self,
        name: str,
        system: str,
        tools: list,
        dispatch: dict,
        model_name: str,
        client: genai.Client,
        color: str = _CY,
    ):
        self.name = name
        self.color = color
        self.model_name = model_name
        self.dispatch = dispatch
        self._client = client
        self._config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
        )
        self._chat = None

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

    def _loop(self, response) -> dict:
        """Drive the function-calling loop until a terminal call or MAX_LOOP_TURNS."""
        for turn in range(MAX_LOOP_TURNS):
            fn_calls = response.function_calls or []

            if not fn_calls:
                try:
                    text = response.text or ""
                except Exception:
                    text = ""
                self._log(f"{_D}(end_turn){_R}")
                return {"summary": text}

            fn_responses = []
            terminal: Optional[dict] = None

            for fc in fn_calls:
                args = dict(fc.args) if fc.args else {}
                if fc.name in self._TERMINAL:
                    terminal = {
                        k: list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else v
                        for k, v in args.items()
                    }
                    self._log(f"{_GR}✓ {fc.name}{_R}")
                    fn_responses.append(
                        types.Part.from_function_response(
                            name=fc.name, response={"result": "acknowledged"}
                        )
                    )
                else:
                    result = self._call(fc.name, args)
                    fn_responses.append(
                        types.Part.from_function_response(
                            name=fc.name, response={"result": result}
                        )
                    )

            response = _send_with_retry(self._chat, fn_responses)

            if terminal is not None:
                return terminal

        self._log(f"{_YL}(max turns {MAX_LOOP_TURNS} reached — stopping){_R}")
        return {"summary": "max turns reached without terminal call"}

    def run(self, prompt: str) -> dict:
        """Start a fresh task."""
        self._chat = self._client.chats.create(
            model=self.model_name,
            config=self._config,
        )
        self._log("Starting...")
        response = _send_with_retry(self._chat, prompt)
        return self._loop(response)

    def send(self, message: str) -> dict:
        """Continue the existing session with a follow-up message."""
        response = _send_with_retry(self._chat, message)
        return self._loop(response)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Drives the full tech-lead → code-review loop.

    1. Tech Lead implements the task (may spawn sub-agents).
    2. Code Reviewer reviews the diff — approves or requests changes.
    3. If rejected, the tech lead's existing session is continued with the
       review feedback (it retains full context of what it already did).
    4. Loop until approved or max_rounds hit, then commit.
    """

    def __init__(
        self,
        repo: Path,
        client: genai.Client,
        model_name: str = DEFAULT_MODEL,
        max_rounds: int = MAX_REVIEW_ROUNDS,
    ):
        self.repo = repo
        self.model = model_name
        self.max_rounds = max_rounds
        self.client = client
        self.ex = Executor(repo)
        self._lead: Optional[Agent] = None

    def _spawn(self, agent_type: str, task: str) -> str:
        system = _SUB_SYS.get(agent_type)
        if not system:
            return f"ERROR: unknown agent_type '{agent_type}'. Valid: {sorted(_SUB_SYS)}"

        _log("Orchestrator", f"Spawning {agent_type}...", _MG)
        tools, dispatch = _make_tech_tools(self.ex, spawner=None)
        agent = Agent(
            name=agent_type.replace("_", " ").title(),
            system=system,
            tools=tools,
            dispatch=dispatch,
            model_name=self.model,
            client=self.client,
            color=_MG,
        )
        result = agent.run(task)
        return result.get("summary", str(result))

    def run(self, prompt: str):
        _log("Orchestrator", f"Task: {prompt}", _YL)
        _hr("═")

        # ── Phase 1: implementation ───────────────────────────────────────────
        tools, dispatch = _make_tech_tools(self.ex, spawner=self._spawn)
        self._lead = Agent(
            name="Tech Lead",
            system=_TECH_LEAD_SYS,
            tools=tools,
            dispatch=dispatch,
            model_name=self.model,
            client=self.client,
            color=_CY,
        )

        impl = self._lead.run(
            f"Repository files:\n{self.ex.list_files()}\n\n"
            f"Task: {prompt}\n\n"
            "Read relevant files first, then implement."
        )
        _log("Tech Lead", f"Done. {impl.get('summary', '')[:200]}", _CY)

        # ── Phase 2: review loop ──────────────────────────────────────────────
        for rnd in range(1, self.max_rounds + 1):
            _hr()
            _log("Orchestrator", f"Review round {rnd}/{self.max_rounds}", _YL)

            r_tools, r_dispatch = _make_reviewer_tools(self.ex)
            reviewer = Agent(
                name="Code Reviewer",
                system=_REVIEWER_SYS,
                tools=r_tools,
                dispatch=r_dispatch,
                model_name=self.model,
                client=self.client,
                color=_GR,
            )

            verdict = reviewer.run(
                f"Task the tech lead was given:\n{prompt}\n\n"
                f"Git diff:\n{self.ex.git_diff()}\n\n"
                "Review the changes thoroughly. Read files for context if needed. "
                "Run the tests. Then call submit_review() with your verdict."
            )

            approved: bool = verdict.get("approved", False)
            issues: list = list(verdict.get("issues", []))
            suggestions: list = list(verdict.get("suggestions", []))
            summary: str = verdict.get("summary", "")

            status = f"{_GR}✅ APPROVED{_R}" if approved else f"{_RD}❌ CHANGES REQUESTED{_R}"
            _log("Code Reviewer", status)
            if summary:
                print(f"  {summary}")
            if issues:
                print(f"\n{_RD}  Blocking issues:{_R}")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
            if suggestions:
                print(f"\n{_YL}  Suggestions:{_R}")
                for s in suggestions:
                    print(f"  • {s}")

            if approved:
                _log("Orchestrator", "Committing approved changes...", _GR)
                msg = (
                    f"ai/agent: {prompt[:70]}\n\n"
                    f"Implemented by TechLead, approved by CodeReviewer in {rnd} round(s)."
                )
                print(f"  {self.ex.git_commit(msg)}")
                _log("Orchestrator", "✅ Done.", _GR)
                return

            if rnd < self.max_rounds:
                _log("Tech Lead", "Addressing review feedback...", _CY)
                feedback = (
                    "The code reviewer rejected your changes. Fix the following blocking issues:\n\n"
                    + "\n".join(f"{i + 1}. {iss}" for i, iss in enumerate(issues))
                    + f"\n\nReviewer summary: {summary}\n\n"
                    "Read the relevant files, fix each issue, run_tests() to verify, "
                    "then call done() again."
                )
                impl = self._lead.send(feedback)

        _log("Orchestrator", "Max review rounds reached — committing with pending issues.", _YL)
        self.ex.git_commit(f"ai/agent: {prompt[:70]} (pending review)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Multi-agent coding assistant (TechLead + CodeReview loop)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python agent.py 'Fix the failing tests'\n"
            "  python agent.py --max-rounds 5 'Add retry logic to updateAzaanTimers'\n"
            "  python agent.py --model gemini-2.0-flash 'Refactor gui_clock.py'\n"
        ),
    )
    ap.add_argument("prompt", help="Task for the agents to work on")
    ap.add_argument(
        "--repo", default=str(REPO_PATH),
        help="Repository root (default: directory of this script)",
    )
    ap.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Gemini model ID (default: {DEFAULT_MODEL})",
    )
    ap.add_argument(
        "--max-rounds", type=int, default=MAX_REVIEW_ROUNDS,
        help=f"Max code-review rounds before force-committing (default: {MAX_REVIEW_ROUNDS})",
    )
    args = ap.parse_args()

    if "GOOGLE_API_KEY" not in os.environ:
        print(f"{_RD}ERROR: GOOGLE_API_KEY environment variable is not set.{_R}")
        sys.exit(1)

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    Orchestrator(
        repo=Path(args.repo),
        client=client,
        model_name=args.model,
        max_rounds=args.max_rounds,
    ).run(args.prompt)


if __name__ == "__main__":
    main()
