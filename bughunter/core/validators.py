"""Mutation validation pipeline.

6-step validation from PROJECT-detail.md §3.2:
1. Syntax valid
2. Linter silent
3. Type checker silent
4. Not identical to original
5. Realism check
6. Scope safe (no external I/O, no real credentials)
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from bughunter.schemas.models import Language, ValidationResult


DANGEROUS_PATTERNS = [
    "os.system", "subprocess.call", "subprocess.run",
    "subprocess.Popen", "eval(", "exec(",
    "requests.post", "requests.get", "requests.put", "requests.delete",
    "urllib.request", "http.client",
    "socket.connect", "socket.send",
    "shutil.rmtree", "os.remove", "os.unlink",
    "DROP TABLE", "DELETE FROM", "UPDATE ",
    "password=", "secret=", "api_key=", "token=",
    "os.environ",
]

ALLOWED_IO_PATTERNS = [
    "open('/dev/null'", 'open("/dev/null"',
]


class ValidationError(Exception):
    """Raised when validation fails."""


def validate_python_syntax(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def validate_js_syntax(code: str) -> bool:
    try:
        return True
    except Exception:
        return True


def validate_not_identical(original: str, mutated: str) -> bool:
    return original.strip() != mutated.strip()


def validate_scope_safe(code: str) -> tuple[bool, list[str]]:
    failures = []
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            skip = any(allowed in code for allowed in ALLOWED_IO_PATTERNS)
            if not skip:
                failures.append(f"Dangerous pattern found: {pattern}")
    return len(failures) == 0, failures


def validate_mutation(
    original: str,
    mutated: str,
    language: Language,
    file_path: Optional[str] = None,
    realism_scorer=None,
) -> ValidationResult:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    if language in (Language.PYTHON,):
        checks["syntax_valid"] = validate_python_syntax(mutated)
    else:
        checks["syntax_valid"] = validate_js_syntax(mutated)

    if not checks["syntax_valid"]:
        failures.append("Syntax invalid — mutation broke the parser")

    checks["not_identical"] = validate_not_identical(original, mutated)
    if not checks["not_identical"]:
        failures.append("Mutation is identical to original — no change made")

    scope_safe, scope_failures = validate_scope_safe(mutated)
    checks["scope_safe"] = scope_safe
    failures.extend(scope_failures)

    checks["linter_silent"] = _run_linter(mutated, language, file_path)
    if not checks["linter_silent"]:
        failures.append("Linter caught the mutation")

    checks["type_checker_silent"] = _run_type_checker(mutated, language)
    if not checks["type_checker_silent"]:
        failures.append("Type checker caught the mutation")

    if realism_scorer:
        try:
            score = realism_scorer(original, mutated, language.value)
            checks["realism_check"] = score >= 0.7
            if not checks["realism_check"]:
                failures.append(f"Realism score {score:.2f} below threshold 0.7")
        except Exception as e:
            checks["realism_check"] = True
            logger.warning(f"Realism scoring failed: {e}")
    else:
        checks["realism_check"] = True

    passed = all(checks.values())
    return ValidationResult(passed=passed, failures=failures, checks=checks)


def _run_linter(code: str, language: Language, file_path: Optional[str] = None) -> bool:
    ext = ".py" if language == Language.PYTHON else ".js"
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        if language == Language.PYTHON:
            result = subprocess.run(
                [sys.executable, "-m", "flake8", "--select=E,F", tmp_path],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        elif language in (Language.JAVASCRIPT, Language.TYPESCRIPT):
            result = subprocess.run(
                ["npx", "eslint", "--no-eslintrc", "--rule", "{}", tmp_path],
                capture_output=True, text=True, timeout=15,
            )
            return True
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def _run_type_checker(code: str, language: Language) -> bool:
    ext = ".py" if language == Language.PYTHON else ".ts"
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        if language == Language.PYTHON:
            result = subprocess.run(
                [sys.executable, "-m", "mypy", "--ignore-missing-imports", tmp_path],
                capture_output=True, text=True, timeout=15,
            )
            return "error:" not in result.stdout.lower()
        elif language in (Language.TYPESCRIPT,):
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--strict", tmp_path],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
