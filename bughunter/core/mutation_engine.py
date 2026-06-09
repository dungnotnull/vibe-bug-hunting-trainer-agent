"""Mutation Engine — generates and validates realistic code bugs.

Core pipeline:
1. Select bug pattern from knowledge base
2. Build context-aware mutation prompt
3. Generate mutation via LLM
4. Run 6-step validation
5. Retry up to max_attempts
6. Record in MutationManifest

Handles all 6 bug categories: boundary, type, async, state, security, logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from bughunter.core.validators import validate_mutation
from bughunter.schemas.models import (
    BugComplexityTier,
    InjectionCandidate,
    Language,
    MutationRecord,
    PatternCategory,
    ValidationResult,
)

MUTATION_STRATEGIES: dict[PatternCategory, list[dict]] = {
    PatternCategory.BOUNDARY: [
        {
            "id": "BP-001",
            "name": "Off-by-One in Loop Bounds",
            "description": "Change < to <= or vice versa in loop termination",
            "bct": BugComplexityTier.BCT_2,
            "template": "In this code, introduce an off-by-one error in the loop bound or slice operation. "
            "Change the boundary by exactly 1 element. Do NOT cause IndexError. Make it subtle — "
            "the code should still run and only produce wrong output at the edge case.",
        },
        {
            "id": "BP-002",
            "name": "Slice Boundary Error",
            "description": "Incorrect slice/array endpoint causing silent truncation",
            "bct": BugComplexityTier.BCT_2,
            "template": "Introduce a boundary error in the slice/array operation. "
            "Change the endpoint so exactly one element is omitted from the result. "
            "No syntax error. No crash. Just wrong output at the boundary.",
        },
        {
            "id": "BP-003",
            "name": "Zero-vs-One Based Index Confusion",
            "description": "Mixing 0-based indexing with 1-based human counting",
            "bct": BugComplexityTier.BCT_2,
            "template": "Introduce an off-by-one index error. Shift an array/list/dict access by 1 index. "
            "Make it look like a mix-up between 0-based and 1-based indexing. "
            "The code must still work for most inputs but fail at boundaries.",
        },
    ],
    PatternCategory.TYPE_COERCION: [
        {
            "id": "BP-101",
            "name": "Loose Equality Trap",
            "description": "== instead of === in security-critical comparisons",
            "bct": BugComplexityTier.BCT_3,
            "template": "Introduce a type coercion bug. In a comparison, use loose equality or "
            "implicit type conversion that causes wrong behavior for edge-case values "
            "(like 0, '', null, undefined, NaN). No syntax errors.",
        },
        {
            "id": "BP-102",
            "name": "Integer Division Surprise",
            "description": "Unintended float-to-int truncation",
            "bct": BugComplexityTier.BCT_2,
            "template": "Introduce an integer division or type truncation bug. "
            "Change a division or type conversion so it silently truncates a value. "
            "The code must compile and run without errors.",
        },
        {
            "id": "BP-103",
            "name": "Null/None Falsy Chain",
            "description": "Using falsy checks when None vs 0 vs '' matters",
            "bct": BugComplexityTier.BCT_2,
            "template": "Introduce a null/falsy handling bug. Replace a proper null check "
            "with a truthy/falsy check that fails for valid falsy values like 0 or ''. "
            "No crash — just wrong behavior for edge cases.",
        },
    ],
    PatternCategory.ASYNC_CONCURRENCY: [
        {
            "id": "BP-201",
            "name": "Missing Await",
            "description": "Forgetting await causes Promise/coroutine to not resolve",
            "bct": BugComplexityTier.BCT_3,
            "template": "Remove or comment out an 'await' keyword in an async function. "
            "The code must still run without errors but return a Promise/coroutine instead of "
            "the resolved value. The bug manifests silently downstream.",
        },
        {
            "id": "BP-202",
            "name": "Race Condition via Shared State",
            "description": "Non-atomic read-modify-write on shared counter",
            "bct": BugComplexityTier.BCT_4,
            "template": "Introduce a subtle race condition. In concurrent code, "
            "make a read-modify-write operation non-atomic by splitting it. "
            "Do NOT add any synchronization. Make it look like a developer forgot to add a lock.",
        },
    ],
    PatternCategory.STATE_MUTATION: [
        {
            "id": "BP-301",
            "name": "Mutable Default Argument",
            "description": "Using mutable object as Python default argument",
            "bct": BugComplexityTier.BCT_2,
            "template": "In a Python function, use a mutable default argument (like [] or {}). "
            "This causes the same object to be shared across all calls. "
            "The function should work correctly on first call but accumulate state on subsequent calls.",
        },
        {
            "id": "BP-302",
            "name": "Shallow Copy Bug",
            "description": "Shallow copy instead of deep copy for nested structures",
            "bct": BugComplexityTier.BCT_3,
            "template": "Replace a proper deep copy with a shallow copy. "
            "Mutating the copy should silently modify the original nested structure. "
            "This is subtle — the top level looks independent but nested objects are shared.",
        },
    ],
    PatternCategory.SECURITY: [
        {
            "id": "BP-401",
            "name": "SQL Injection Vector",
            "description": "String concatenation instead of parameterized query",
            "bct": BugComplexityTier.BCT_4,
            "template": "From a parameterized query/request building function, remove parameterization "
            "and use string concatenation or f-string. Use a harmless string like 'users' for the "
            "query target. This is for training only — use in-memory data structures.",
        },
        {
            "id": "BP-402",
            "name": "Insecure Randomness",
            "description": "Math.random() or random module for crypto tokens",
            "bct": BugComplexityTier.BCT_3,
            "template": "Replace a cryptographically secure random function with a non-secure one. "
            "For example, replace secrets.token_hex() with a weak random string generator. "
            "No crash — the output looks valid but is predictable.",
        },
        {
            "id": "BP-403",
            "name": "Path Traversal",
            "description": "Missing path sanitization allows directory escape",
            "bct": BugComplexityTier.BCT_4,
            "template": "Remove path sanitization/basename extraction from a file path operation. "
            "Use direct string concatenation or join without validation. "
            "The code must work fine for normal paths but be vulnerable to '../' escapes.",
        },
    ],
    PatternCategory.LOGIC_ALGORITHM: [
        {
            "id": "BP-501",
            "name": "Wrong Logical Operator",
            "description": "AND vs OR confusion in guard conditions",
            "bct": BugComplexityTier.BCT_2,
            "template": "Change a logical operator: AND to OR, or OR to AND, in a conditional. "
            "The code must still be syntactically correct but the logic is wrong. "
            "Make it subtle — it should still work for some inputs but fail for others.",
        },
        {
            "id": "BP-502",
            "name": "Wrong Comparison Operator",
            "description": "> vs >= in business rule thresholds",
            "bct": BugComplexityTier.BCT_2,
            "template": "Change a comparison operator: > to >=, or < to <=, or vice versa. "
            "The bug should only manifest at exact boundary values. "
            "No syntax error. No crash. Just wrong behavior at the edge.",
        },
    ],
}


class MutationEngine:
    """Generates, validates, and records bug mutations."""

    def __init__(
        self,
        llm_client=None,
        knowledge_brain_path: Optional[Path] = None,
        max_retries: int = 5,
        realism_threshold: float = 0.7,
    ):
        self._llm = llm_client
        self._knowledge_path = knowledge_brain_path
        self.max_retries = max_retries
        self.realism_threshold = realism_threshold

    def generate_mutation(
        self,
        candidate: InjectionCandidate,
        source_code: str,
        language: Language,
        context: str = "",
    ) -> tuple[str, MutationRecord, ValidationResult]:
        """Generate and validate a mutation for an injection candidate.

        Returns (mutated_code, mutation_record, validation_result).
        Raises RuntimeError if all retries exhausted.
        """
        strategies = MUTATION_STRATEGIES.get(candidate.pattern_category, [])
        if not strategies:
            strategies = MUTATION_STRATEGIES[PatternCategory.LOGIC_ALGORITHM]

        strategy = strategies[0]
        for s in strategies:
            if s["bct"] == candidate.difficulty_level:
                strategy = s
                break

        original = source_code.strip()

        for attempt in range(self.max_retries):
            try:
                if self._llm:
                    mutated = self._llm.generate_mutation(
                        category=candidate.pattern_category.value,
                        language=language.value,
                        original_code=original,
                        line_start=candidate.line_start,
                        line_end=candidate.line_end,
                        context=context,
                    )
                else:
                    mutated = self._template_based_mutation(
                        original, candidate, language
                    )

                realism_scorer = (
                    self._llm.score_realism if self._llm else None
                )
                validation = validate_mutation(
                    original, mutated, language,
                    file_path=candidate.file,
                    realism_scorer=realism_scorer,
                )

                if validation.passed:
                    record = MutationRecord(
                        mutation_id=uuid.uuid4().hex[:12],
                        file=candidate.file,
                        line_start=candidate.line_start,
                        line_end=candidate.line_end,
                        original_content=original,
                        injected_content=mutated,
                        pattern_category=candidate.pattern_category,
                        bug_pattern_id=strategy["id"],
                        difficulty=candidate.difficulty_level,
                    )
                    logger.debug(
                        f"Mutation generated: {strategy['id']} in {candidate.file}:{candidate.line_start}"
                    )
                    return mutated, record, validation

                logger.debug(
                    f"Mutation attempt {attempt + 1} failed validation: {validation.failures}"
                )

            except Exception as e:
                logger.warning(f"Mutation attempt {attempt + 1} error: {e}")

        raise RuntimeError(
            f"Failed to generate valid mutation after {self.max_retries} attempts "
            f"for {candidate.file}:{candidate.line_start}"
        )

    def _template_based_mutation(
        self,
        original: str,
        candidate: InjectionCandidate,
        language: Language,
    ) -> str:
        """Fallback: apply heuristic mutations without LLM."""
        import re

        mutated = original

        if candidate.pattern_category == PatternCategory.BOUNDARY:
            mutated = re.sub(r"(\s+<)\s+(\w+)", r"\1= \2", mutated, count=1)
            if mutated == original:
                mutated = re.sub(r"(\s+<=\s+)(\w+)", r"< \2", mutated, count=1)
            if mutated == original:
                mutated = re.sub(r"(\[)(\w*):(\w+)(\])", r"\1\2:\3-1\4", mutated, count=1)

        elif candidate.pattern_category == PatternCategory.LOGIC_ALGORITHM:
            if " and " in mutated:
                mutated = mutated.replace(" and ", " or ", 1)
            elif " or " in mutated:
                mutated = mutated.replace(" or ", " and ", 1)
            elif " && " in mutated:
                mutated = mutated.replace(" && ", " || ", 1)
            elif " || " in mutated:
                mutated = mutated.replace(" || ", " && ", 1)
            elif ">=" in mutated:
                mutated = mutated.replace(">=", ">", 1)
            elif "<=" in mutated:
                mutated = mutated.replace("<=", "<", 1)

        elif candidate.pattern_category == PatternCategory.TYPE_COERCION:
            if language == Language.PYTHON:
                mutated = mutated.replace(" is None", " is not None", 1)
                if mutated == original:
                    mutated = mutated.replace(" if ", " if not ", 1)
            else:
                mutated = mutated.replace(" === ", " == ", 1)
                if mutated == original:
                    mutated = mutated.replace(" !== ", " != ", 1)

        elif candidate.pattern_category == PatternCategory.ASYNC_CONCURRENCY:
            mutated = re.sub(r"await\s+", "", mutated, count=1)

        elif candidate.pattern_category == PatternCategory.STATE_MUTATION:
            if language == Language.PYTHON:
                mutated = mutated.replace("deepcopy(", "copy(", 1)
                if mutated == original:
                    mutated = mutated.replace("= None\n", "= []\n", 1)

        elif candidate.pattern_category == PatternCategory.SECURITY:
            mutated = mutated.replace("secrets.token_hex(", "random.choices('0123456789abcdef', k=", 1)
            mutated = mutated.replace("secrets.token_urlsafe(", "random.choices('0123456789abcdef', k=", 1)
            mutated = mutated.replace("crypto.randomBytes(", "Math.random().toString(36).substring(2, ", 1)
            if mutated == original:
                mutated = mutated.replace("parameterized", "string interpolation", 1)
            if mutated == original:
                mutated = mutated.replace("os.path.basename(", "str(", 1)

        return mutated

    def apply_mutation_to_file(
        self,
        file_path: Path,
        mutation: MutationRecord,
    ) -> None:
        """Write the mutated code back to the file."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if mutation.original_content not in content:
            raise RuntimeError(
                f"Original content not found in {file_path}. "
                f"File may have been modified since candidate extraction."
            )

        content = content.replace(
            mutation.original_content, mutation.injected_content, 1
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug(f"Applied mutation {mutation.mutation_id} to {file_path}")

    def rollback_mutation(
        self,
        file_path: Path,
        mutation: MutationRecord,
    ) -> None:
        """Restore original code from a mutation record."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if mutation.injected_content not in content:
            logger.warning(
                f"Injected content not found in {file_path} — may already be rolled back"
            )
            return

        content = content.replace(
            mutation.injected_content, mutation.original_content, 1
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        mutation.rolled_back = True
        mutation.rolled_back_at = datetime.utcnow()
        logger.debug(f"Rolled back mutation {mutation.mutation_id}")
