"""
Code patcher — generates and applies targeted function-level patches.

Safety design:
  1. Scope is limited to PATCHABLE_FILES only
  2. Patches replace exactly one named function
  3. Three gates before acceptance: syntax check, AST scope check, test suite
  4. Backup created before every patch; rollback on any gate failure
"""
from __future__ import annotations

import ast
import importlib
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import List, Optional

from config import PATCHABLE_FILES, ROOT_DIR
from llm.base import LLMMessage, with_retry
from llm.router import get_provider
from refinement.evaluator import CriterionScore

_PATCHER_SYSTEM = """\
You are an expert Python engineer fixing a specific bug in an airline API service.

Rules:
1. You will receive the CURRENT source code of a single Python function
2. You will receive a description of what it does wrong and what it should do
3. Output ONLY the replacement function — complete, syntactically valid Python
4. Keep the same function signature (name, parameters, return type)
5. Do not add imports that don't already exist in the file
6. Do not output anything outside the function definition (no explanation, no markdown)
7. The function must start with 'def ' or 'async def '
"""


class PatchRequest:
    def __init__(
        self,
        file_path: str,
        function_name: str,
        failure_description: str,
        expected_behavior: str,
    ):
        self.file_path = file_path
        self.function_name = function_name
        self.failure_description = failure_description
        self.expected_behavior = expected_behavior


class PatchResult:
    def __init__(self, success: bool, file_path: str, function_name: str, reason: str = ""):
        self.success = success
        self.file_path = file_path
        self.function_name = function_name
        self.reason = reason


def _extract_function_source(file_path: Path, function_name: str) -> Optional[str]:
    """Extract the source code of a named function from a Python file."""
    source = file_path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                lines = source.splitlines()
                # Get the function with its decorators
                start = node.decorator_list[0].lineno - 1 if node.decorator_list else node.lineno - 1
                end = node.end_lineno
                return "\n".join(lines[start:end])
    return None


def _replace_function_in_source(
    original_source: str,
    function_name: str,
    new_function_code: str,
) -> Optional[str]:
    """Replace a named function in a source file, preserving everything else."""
    try:
        tree = ast.parse(original_source)
    except SyntaxError:
        return None

    lines = original_source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                start = node.decorator_list[0].lineno - 1 if node.decorator_list else node.lineno - 1
                end = node.end_lineno

                new_lines = (
                    lines[:start]
                    + new_function_code.splitlines()
                    + lines[end:]
                )
                return "\n".join(new_lines)

    return None


def _syntax_valid(code: str) -> bool:
    try:
        compile(code, "<patch>", "exec")
        return True
    except SyntaxError:
        return False


def _only_touches_target_function(new_function_code: str, function_name: str) -> bool:
    """Verify the patch contains exactly one function definition with the right name."""
    try:
        tree = ast.parse(new_function_code)
    except SyntaxError:
        return False

    top_level_fns = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.col_offset == 0  # top-level only
    ]

    if len(top_level_fns) != 1:
        return False

    return top_level_fns[0].name == function_name


def _run_tests() -> bool:
    """Run the test suite. Returns True if all tests pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=no"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0


def _backup_file(file_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    backup_path = ROOT_DIR / "data" / "patches" / "backup" / f"{file_path.name}_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def _restore_backup(backup_path: Path, file_path: Path) -> None:
    shutil.copy2(backup_path, file_path)


def generate_and_apply_patch(request: PatchRequest) -> PatchResult:
    """
    Generate a code patch for the given request and apply it if it passes all gates.

    Gates (in order):
      1. File is in PATCHABLE_FILES
      2. Function exists in file
      3. LLM generates replacement function
      4. Syntax check
      5. Scope check (only touches target function)
      6. Test suite passes
    """
    file_path = ROOT_DIR / request.file_path

    # Gate 1: patchable scope
    if request.file_path not in PATCHABLE_FILES:
        return PatchResult(False, request.file_path, request.function_name,
                           f"File '{request.file_path}' is not in PATCHABLE_FILES")

    if not file_path.exists():
        return PatchResult(False, request.file_path, request.function_name,
                           f"File not found: {file_path}")

    # Gate 2: function exists
    current_fn_source = _extract_function_source(file_path, request.function_name)
    if current_fn_source is None:
        return PatchResult(False, request.file_path, request.function_name,
                           f"Function '{request.function_name}' not found in {request.file_path}")

    # Generate patch
    patcher_llm = get_provider("code_patcher")
    messages = [
        LLMMessage.system(_PATCHER_SYSTEM),
        LLMMessage.user(
            f"FILE: {request.file_path}\n\n"
            f"CURRENT FUNCTION:\n{current_fn_source}\n\n"
            f"WHAT IS WRONG: {request.failure_description}\n\n"
            f"WHAT IT SHOULD DO: {request.expected_behavior}\n\n"
            f"Output ONLY the replacement function code:"
        ),
    ]

    try:
        new_fn_code = with_retry(patcher_llm.complete, messages, temperature=0.2, max_attempts=3)
    except Exception as exc:
        return PatchResult(False, request.file_path, request.function_name,
                           f"LLM patch generation failed: {exc}")

    new_fn_code = new_fn_code.strip()

    # Strip markdown if model wrapped it
    if new_fn_code.startswith("```"):
        lines = new_fn_code.splitlines()
        new_fn_code = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    # Gate 3: syntax check
    if not _syntax_valid(new_fn_code):
        return PatchResult(False, request.file_path, request.function_name,
                           "Patch failed syntax check")

    # Gate 4: scope check
    if not _only_touches_target_function(new_fn_code, request.function_name):
        return PatchResult(False, request.file_path, request.function_name,
                           "Patch scope check failed — output contained unexpected function definitions")

    # Backup before writing
    backup_path = _backup_file(file_path)

    # Apply patch
    original_source = file_path.read_text()
    patched_source = _replace_function_in_source(original_source, request.function_name, new_fn_code)

    if patched_source is None:
        return PatchResult(False, request.file_path, request.function_name,
                           "Failed to replace function in source file")

    file_path.write_text(patched_source)

    # Gate 5: run tests
    if not _run_tests():
        _restore_backup(backup_path, file_path)
        return PatchResult(False, request.file_path, request.function_name,
                           "Tests failed after patch — rolled back to backup")

    # Reload the module
    _reload_module(request.file_path)

    return PatchResult(True, request.file_path, request.function_name,
                       f"Patch applied and verified. Backup at {backup_path.name}")


def _reload_module(file_path: str) -> None:
    """Attempt to reload the patched module in the running process."""
    module_path = file_path.replace("/", ".").removesuffix(".py")
    if module_path in sys.modules:
        try:
            importlib.reload(sys.modules[module_path])
        except Exception:
            pass  # Reload is best-effort; uvicorn --reload handles the rest


def build_patch_requests_from_failures(
    failures: List[CriterionScore],
) -> List[PatchRequest]:
    """
    Convert code-classified failures into PatchRequest objects.

    The evaluator is asked to identify the specific file and function.
    For failures where this info is in root_cause_detail, we parse it.
    Otherwise we default to the most likely webhook handler.
    """
    requests = []
    for failure in failures:
        if failure.root_cause != "code":
            continue

        detail = failure.root_cause_detail
        file_path, function_name = _parse_file_function(detail)

        requests.append(PatchRequest(
            file_path=file_path,
            function_name=function_name,
            failure_description=detail,
            expected_behavior=f"Fix the issue: {detail}",
        ))

    return requests


def _parse_file_function(detail: str) -> tuple:
    """
    Parse file and function from detail string.
    Looks for patterns like 'api/routes/webhooks.py::function_name'.
    Falls back to webhook handler if not parseable.
    """
    import re
    match = re.search(r"([\w/]+\.py)::(\w+)", detail)
    if match:
        return match.group(1), match.group(2)

    # Default: webhook layer is the most common code failure point
    return "api/routes/webhooks.py", "webhook_search_flights"
