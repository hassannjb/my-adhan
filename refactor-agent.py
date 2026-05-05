#!/usr/bin/env python
import os
import subprocess
import sys
import time
from pathlib import Path

import google.generativeai as genai

# CONFIG
REPO_PATH = "/Users/hassan.najeeb/PycharmProjects/my-adhan"
BRANCH_NAME = "ai/agent-refactor"
MAX_ITERS = 3
TEST_DIR = "tests"
MODEL_NAME = "models/gemini-2.5-flash-lite"


# Tools
def run(cmd, cwd, check=True):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def git(cmd, cwd):
    """Helper: run git command in a repo."""
    return run(["git"] + cmd, cwd)[0]


def setup_branch(repo_path, branch_name):
    """Create or reuse branch."""
    git(["fetch"], repo_path)
    try:
        git(["checkout", branch_name], repo_path)
    except RuntimeError:
        git(["checkout", "-b", branch_name], repo_path)


def stage_commit_push(repo_path, branch_name, msg="Auto‑fix via agent"):
    """Add all, commit, push the branch."""
    git(["add", "."], repo_path)
    git(["commit", "-m", msg], repo_path)
    git(["push", "-u", "origin", branch_name], repo_path)


def ensure_tests_dir(repo_path):
    """Create tests/ if missing and add __init__.py."""
    tests_path = Path(repo_path) / TEST_DIR
    tests_path.mkdir(exist_ok=True)
    (tests_path / "__init__.py").touch()


def build_repo_context(repo_path, files):
    """Gather core files for the model."""
    chunks = []
    for rel_path in files:
        p = Path(repo_path) / rel_path
        if p.exists():
            content = p.read_text()
            chunks.append(f"--- FILE: {rel_path} ---\n{content}\n")
    return "\n".join(chunks)


def collect_test_files(repo_path, ext=".py"):
    """Return all test files in tests/."""
    tests_path = Path(repo_path) / TEST_DIR
    if not tests_path.exists():
        return []
    return [f for f in tests_path.rglob(f"test_*.py") if f.is_file()]


def run_tests(repo_path: str) -> tuple[bool, str]:
    """Run pytest and return (passed, output)."""
    passed, output, code = run(
        ["pytest", f"--rootdir={repo_path}", "--tb=short", "-q"],
        cwd=repo_path,
        check=False,
    )
    return code == 0, output


def ask_model(prompt: str, model_name: str) -> str:
    """Ask Gemini a question."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text


def generate_tests_prompt(repo_path: str, files: list[str], failures: str):
    """Generate prompt asking model to write tests or fix."""
    context = build_repo_context(repo_path, files)

    return f"""
You are an expert Python engineer and a senior test engineer.

Repo goal:
- This is a simple Adhan Clock app on macOS 2014+.
- Two main files: main.py (GUI) and updateAzaanTimers.py (CLI).
- You must preserve existing behavior.

Task:
Write code that improves maintainability and testability, but:
- First, add or fix tests so all current behavior is covered.
- Prefer pytest with clear, small test functions.
- Assume tests will live in {TEST_DIR}/ (e.g., test_main.py, test_updateAzaanTimers.py).
- If tests already exist, you may:
  - Fix failing tests so they pass without changing app behavior,
  - OR add missing tests for uncovered paths.
- Only change app logic if the model is explicitly asked to refactor.

Current repo context:
{context}

Recent test run output:
{failures}

Instructions:
1. Return only the file contents you want to add or overwrite.
2. Format each file like:

--- FILE: path/to/file.py ---
<content>
---

3. If you need to add or change app code, do so in the smallest way possible.
4. If you are only adding tests, do not change app code.
Instructions:
5. RETURN ONLY RAW FILE CONTENTS. Do NOT wrap any code in markdown code blocks like:
   ```python or ```

5. Do not add extra commentary outside the --- FILE: ... --- blocks.
"""


def parse_patches(response_text: str) -> dict[str, str]:
    """Parse blocks like "--- FILE: name ---\n<content>\n" into a dict."""
    patches = {}
    lines = response_text.splitlines()
    current_file = None
    current_body = []

    for line in lines:
        if line.startswith("--- FILE: ") and line.endswith(" ---"):
            if current_file:
                patches[current_file] = "\n".join(current_body)
            current_file = line[len("--- FILE: "): -len(" ---")].strip()
            current_body = []
        elif current_file:
            current_body.append(line)
        # else: ignore header lines

    if current_file and current_body:
        patches[current_file] = "\n".join(current_body)

    return patches


def apply_patches(repo_path: str, patches: dict[str, str]) -> None:
    """Write each patch to its file."""
    for rel_path, content in patches.items():
        path = Path(repo_path) / rel_path
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def main():
    repo_path = REPO_PATH
    repo_path = os.path.abspath(repo_path)

    if not os.path.exists(repo_path):
        print(f"Repo path does not exist: {repo_path}")
        sys.exit(1)

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

    setup_branch(repo_path, BRANCH_NAME)
    ensure_tests_dir(repo_path)

    target_files = [
        "main.py",
        "updateAzaanTimers.py",
        "requirements.txt",
    ]

    for i in range(MAX_ITERS):
        print(f"\n--- ITERATION {i + 1} ---\n")

        # 1. Check if tests exist
        test_files = collect_test_files(repo_path)
        has_tests = len(test_files) > 0

        # 2. Run existing tests
        passed, test_output = run_tests(repo_path)
        if passed and has_tests:
            print("✅ All tests pass. No changes needed.")
            break

        # 3. Ask model to fix or add tests
        prompt = generate_tests_prompt(
            repo_path=repo_path,
            files=target_files,
            failures=test_output,
        )

        suggestion = ask_model(prompt, MODEL_NAME)

        # 4. Parse and apply patches
        patches = parse_patches(suggestion)
        if not patches:
            print("⚠ No file patches found. Stopping.")
            print("Raw model response:")
            print(suggestion)
            break

        print(f"Applying {len(patches)} files...")
        for fname in patches:
            print(f"  - {fname}")
        apply_patches(repo_path, patches)

        # 5. Retry tests
        passed, test_output = run_tests(repo_path)

        status = "✅ All tests pass." if passed else "❌ Tests still failing."
        print(f"\nTest status: {status}")
        print(f"\nTest output:\n{test_output}\n")

        if not passed:
            print("Model will retry next iteration with updated test output.")
        else:
            print("✅ Test suite is green. Committing changes.")

        # 6. Commit (optional, controlled)
        reason = "Passing tests" if passed else "WIP: fix in progress"
        stage_commit_push(repo_path, BRANCH_NAME, msg=f"ai/agent: {reason}")

        if passed:
            break

        # Wait a bit so you can Ctrl‑C if you want
        time.sleep(1)

        if not passed:
            print(
                f"\n❌ After {MAX_ITERS} iterations, tests still fail."
                "\nPlease review generated files and run pytest manually."
            )


if __name__ == "__main__":
    main()
