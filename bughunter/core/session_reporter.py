"""Session Reporter — generates educational post-hunt debriefs.

Produces rich Markdown reports with:
- Bug anatomy (what was injected, why, how realistic)
- Debug journey replay (timeline)
- Skill analysis (DSS impact, strengths/gaps)
- Pattern lesson (educational content)
- Next session preview (spaced repetition queue)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from bughunter.schemas.models import (
    BugComplexityTier,
    HintLevel,
    MutationRecord,
    SessionOutcome,
    SessionResult,
)


OUTCOME_ICONS = {
    SessionOutcome.FOUND_INDEPENDENTLY: "🎯",
    SessionOutcome.FOUND_WITH_HINTS: "🔵",
    SessionOutcome.AI_ASSISTED: "🤖",
    SessionOutcome.SURRENDERED: "🏳️",
    SessionOutcome.TIMEOUT: "⏰",
    SessionOutcome.ROLLED_BACK: "↩️",
}

OUTCOME_LABELS = {
    SessionOutcome.FOUND_INDEPENDENTLY: "Found Independently",
    SessionOutcome.FOUND_WITH_HINTS: "Found with Hints",
    SessionOutcome.AI_ASSISTED: "AI-Assisted Detected",
    SessionOutcome.SURRENDERED: "Surrendered",
    SessionOutcome.TIMEOUT: "Timeout",
    SessionOutcome.ROLLED_BACK: "Rolled Back",
}

BCT_LABELS = {
    BugComplexityTier.BCT_1: "BCT-1 (Beginner)",
    BugComplexityTier.BCT_2: "BCT-2 (Intermediate)",
    BugComplexityTier.BCT_3: "BCT-3 (Advanced)",
    BugComplexityTier.BCT_4: "BCT-4 (Expert)",
    BugComplexityTier.BCT_5: "BCT-5 (Master)",
}

PATTERN_LESSONS: dict[str, str] = {
    "BP-001": (
        "**Root cause**: Fence-post errors ('off-by-one') are the most common class of "
        "boundary bugs in any language. They're especially dangerous because they often "
        "fail silently rather than throwing exceptions.\n\n"
        "**How to prevent it**:\n"
        "1. Write boundary test cases first (TDD): test with empty collection, 1 element, n elements, n+1 elements\n"
        "2. Name variables clearly: `limit` vs `count` vs `index`\n"
        "3. Use language idioms: Python's `range()` and slice semantics are exclusive-end by design"
    ),
    "BP-002": (
        "**Root cause**: Slice boundary errors are silent data corruption — you lose exactly "
        "one element at the edge with no error message.\n\n"
        "**How to prevent it**: Always test pagination with: empty list, exactly N items, N+1 items. "
        "Use named constants for slice boundaries."
    ),
    "BP-101": (
        "**Root cause**: JavaScript's loose equality (`==`) performs type coercion that can produce "
        "surprising results: `'0' == 0` is `true`, `null == undefined` is `true`.\n\n"
        "**How to prevent it**: Always use `===` for comparisons unless you explicitly want coercion. "
        "Configure ESLint `eqeqeq` rule to 'always'."
    ),
    "BP-201": (
        "**Root cause**: Missing `await` is one of the most insidious async bugs — no error is thrown; "
        "the function simply returns a Promise/coroutine object instead of the resolved value. "
        "The bug only manifests when the returned value is used downstream.\n\n"
        "**How to prevent it**: Use TypeScript with `no-floating-promises` enabled; "
        "in Python, use `asyncio` debug mode during development."
    ),
    "BP-301": (
        "**Root cause**: Python evaluates default arguments once at function definition time, "
        "not at call time. A mutable default (list, dict, set) is shared across all calls.\n\n"
        "**How to prevent it**: Use `None` as default and initialize inside the function body. "
        "Linters like pylint and flake8-bugbear catch this automatically."
    ),
    "BP-401": (
        "**Root cause**: String concatenation in SQL queries is the #3 most critical web "
        "application vulnerability (OWASP A03:2021). Even in internal tools, it's a vector for "
        "accidental data corruption.\n\n"
        "**How to prevent it**: Always use parameterized queries. Never trust user input. "
        "Use ORM abstractions when possible."
    ),
    "BP-501": (
        "**Root cause**: AND vs OR confusion in conditionals is a classic logic bug. It often "
        "passes code review because the difference is a single character change that looks correct.\n\n"
        "**How to prevent it**: Write boolean expressions as named helper functions with descriptive names. "
        "Test each branch of compound conditionals independently."
    ),
}


class SessionReporter:
    """Generates rich educational session reports."""

    def __init__(self, output_dir: Optional[Path] = None):
        self._output_dir = output_dir or Path.home() / ".bughunter" / "sessions"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(self, result: SessionResult) -> str:
        """Generate a full Markdown session report."""
        outcome = result.outcome or SessionOutcome.TIMEOUT
        icon = OUTCOME_ICONS.get(outcome, "❓")
        label = OUTCOME_LABELS.get(outcome, "Unknown")

        parts = [self._header(result, icon, label)]
        parts.append(self._bug_anatomy(result))
        parts.append(self._lesson_section(result))
        parts.append(self._debug_journey(result))
        parts.append(self._skill_analysis(result))
        parts.append(self._next_session(result))
        parts.append(self._footer(result))

        report = "\n\n".join(parts)
        self._save_report(result, report)
        return report

    def _header(self, result: SessionResult, icon: str, label: str) -> str:
        lines = [
            f"# {icon} Bug Hunt Complete — Session Report",
            "",
            f"| | |",
            f"|---|---|",
            f"| **Session ID** | `{result.session_id}` |",
            f"| **Result** | {icon} {label} |",
        ]
        if result.time_to_discovery_seconds is not None:
            minutes = result.time_to_discovery_seconds // 60
            seconds = result.time_to_discovery_seconds % 60
            lines.append(f"| **Time to Discovery** | {minutes}m {seconds}s |")
        if result.hints_used:
            lines.append(f"| **Hints Used** | {len(result.hints_used)} |")

        lines.extend([
            f"| **DSS** | {result.dss_before} → {result.dss_after} ({result.dss_delta:+d}) |",
            f"| **Date** | {result.started_at.strftime('%Y-%m-%d %H:%M UTC')} |",
            "",
            "---",
        ])
        return "\n".join(lines)

    def _bug_anatomy(self, result: SessionResult) -> str:
        lines = ["## The Bug You Found", ""]
        if result.mutations:
            m = result.mutations[0]
            difficulty = BCT_LABELS.get(m.difficulty, str(m.difficulty))
            lines.extend([
                f"**File**: `{m.file}`",
                f"**Lines**: {m.line_start}–{m.line_end}",
                f"**Pattern**: {m.bug_pattern_id} | {m.pattern_category.value}",
                f"**Difficulty**: {difficulty}",
                "",
                "### What was injected:",
                "```",
                "// ORIGINAL (correct):",
                m.original_content[:300],
                "",
                "// INJECTED (buggy):",
                m.injected_content[:300],
                "```",
            ])
        return "\n".join(lines)

    def _lesson_section(self, result: SessionResult) -> str:
        lines = ["## The Lesson", ""]
        if result.mutations:
            m = result.mutations[0]
            lesson = PATTERN_LESSONS.get(m.bug_pattern_id, "")
            if lesson:
                lines.append(lesson)
            else:
                lines.append(
                    "This bug demonstrates a common {m.pattern_category.value} pattern. "
                    "Review the original and mutated code above to understand the difference."
                )
        return "\n".join(lines)

    def _debug_journey(self, result: SessionResult) -> str:
        lines = ["## Your Debug Journey", "", "```"]
        lines.append("Files explored:")
        for f in result.files_explored[:20]:
            lines.append(f"  📄 {f}")
        if not result.files_explored:
            lines.append("  (no file tracking data)")
        if result.hints_used:
            lines.append("")
            lines.append("Hints used:")
            for hint in result.hints_used:
                lines.append(f"  Level {hint.level.value}: {hint.content[:80]}")
        lines.append("```")
        return "\n".join(lines)

    def _skill_analysis(self, result: SessionResult) -> str:
        lines = ["## Skill Analysis", ""]
        delta = result.dss_delta
        if delta > 0:
            lines.append(f"**DSS Impact**: +{delta} points — well done! 🎉")
        elif delta < 0:
            lines.append(f"**DSS Impact**: {delta} points — keep practicing.")
        else:
            lines.append("**DSS Impact**: No change.")

        outcome = result.outcome
        if outcome == SessionOutcome.FOUND_INDEPENDENTLY:
            lines.append("\n**What you did well**: Found the bug entirely on your own — this builds deep debugging intuition.")
        elif outcome == SessionOutcome.FOUND_WITH_HINTS:
            lines.append("\n**To improve**: Try to reduce hint usage next time. The first instinct is usually right — trust it more.")
        elif outcome == SessionOutcome.SURRENDERED:
            lines.append("\n**Takeaway**: Every 'I give up' is a learning opportunity. Review the lesson section carefully — this pattern will return.")
        return "\n".join(lines)

    def _next_session(self, result: SessionResult) -> str:
        lines = ["## Next Session", ""]
        lines.append("Your next session will be scheduled based on your spaced repetition queue.")
        lines.append("Keep practicing — debugging intuition compounds over time.")
        return "\n".join(lines)

    def _footer(self, result: SessionResult) -> str:
        return f"\n\n---\n*Report generated by BugHunterAgent v0.1.0 | {datetime.utcnow().isoformat()}*"

    def _save_report(self, result: SessionResult, report: str):
        path = self._output_dir / f"{result.session_id}_report.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        result.report_path = str(path)
        logger.debug(f"Report saved: {path}")
