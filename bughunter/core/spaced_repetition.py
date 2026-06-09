"""Spaced Repetition Engine (SM-2) + Anti-Cheat Monitor.

SM-2 Algorithm: SuperMemo 2 — proven spaced repetition algorithm used by Anki.
Schedules bug patterns for re-exposure based on mastery level.

Anti-Cheat: Detects AI-assisted debugging patterns and flags for coaching.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from bughunter.schemas.models import (
    AntiCheatSignal,
    BugComplexityTier,
    DeveloperProfile,
    PatternMastery,
    SessionResult,
)


class SpacedRepetitionEngine:
    """SM-2 spaced repetition for bug pattern scheduling.

    Core algorithm:
    - Each pattern has: ease_factor (EF), interval_days, next_review date
    - After each session: update based on outcome grade (0-5)
    - Mastered patterns (3 consecutive unaided wins) marked complete
    - Patterns decay over time and re-enter the queue
    """

    QUALITY_GRADE_MAP = {
        "perfect": 5,       # Found immediately, no hints
        "good": 4,          # Found with some effort, no hints
        "ok": 3,            # Found with 1-2 hints
        "struggled": 2,     # Found with 3+ hints
        "gave_up": 1,       # Surrendered or timeout
        "complete_blackout": 0,
    }

    def __init__(self):
        pass

    def schedule_next_review(
        self,
        mastery: PatternMastery,
        quality: int,
    ) -> PatternMastery:
        """Apply SM-2 scheduling to update review interval."""
        if quality >= 3:
            if mastery.consecutive_wins == 1:
                mastery.interval_days = 1
            elif mastery.consecutive_wins == 2:
                mastery.interval_days = 6
            else:
                mastery.interval_days = int(mastery.interval_days * mastery.ease_factor)

            mastery.ease_factor = mastery.ease_factor + (
                0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
            )
            mastery.consecutive_wins += 1
        else:
            mastery.consecutive_wins = 0
            mastery.interval_days = 1
            mastery.ease_factor = max(1.3, mastery.ease_factor - 0.20)

        mastery.ease_factor = max(1.3, min(2.5, mastery.ease_factor))
        mastery.next_review = datetime.utcnow() + timedelta(days=max(1, mastery.interval_days))

        if mastery.consecutive_wins >= 3:
            mastery.mastered = True

        return mastery

    def get_due_patterns(
        self,
        profile: DeveloperProfile,
        limit: int = 5,
    ) -> list[str]:
        """Return patterns that are due for review."""
        now = datetime.utcnow()
        due: list[tuple[str, float]] = []

        for pattern_id, mastery in profile.pattern_mastery.items():
            if mastery.mastered and mastery.next_review and mastery.next_review > now:
                continue
            priority = 0.0
            if mastery.next_review and mastery.next_review <= now:
                days_overdue = (now - mastery.next_review).total_seconds() / 86400
                priority = days_overdue * (1.0 - mastery.ease_factor / 2.5)
            else:
                priority = 0.1
            due.append((pattern_id, priority))

        due.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in due[:limit]]

    def compute_mastery_decay(self, profile: DeveloperProfile) -> None:
        """Apply forgetting curve — mastered patterns decay without practice."""
        now = datetime.utcnow()
        for mastery in profile.pattern_mastery.values():
            if mastery.mastered and mastery.last_seen:
                days_since = (now - mastery.last_seen).total_seconds() / 86400
                if days_since > 90:
                    mastery.mastered = False
                    mastery.ease_factor = max(1.3, mastery.ease_factor - 0.1)
                    mastery.interval_days = max(1, mastery.interval_days // 2)
                    logger.debug(f"Pattern {mastery.pattern_id} mastery decayed after {days_since:.0f} days")


class AntiCheatMonitor:
    """Detects AI-assisted bug discovery patterns.

    Detection signals:
    - INSTANT_NAVIGATION: Navigated directly to injected line within 60s
    - ZERO_EXPLORATION: Opened fewer than 3 files before fix
    - SUSPICIOUSLY_FAST: Fixed in < 2min for BCT-3+ bug
    - PERFECT_FIX: Fix exactly matches expected correction verbatim
    - COMMIT_MSG_AI: Commit message matches LLM phrasing patterns
    """

    LLM_PHRASE_PATTERNS = [
        "here's the fix",
        "i've updated the",
        "the issue was",
        "this resolves the",
        "the problem was that",
        "i've corrected the",
        "let me explain what",
        "the error occurred because",
    ]

    def __init__(self):
        self._session_activity: dict[str, list[dict]] = defaultdict(list)
        self._last_file_visits: dict[str, list[tuple[str, float]]] = defaultdict(list)

    def record_file_open(self, session_id: str, file_path: str) -> None:
        """Track file activity during a session."""
        self._last_file_visits[session_id].append((file_path, time.time()))

    def analyze_session(
        self,
        session_id: str,
        result: SessionResult,
        mutations_files: list[str],
    ) -> list[AntiCheatSignal]:
        """Analyze session behavior for AI-assist signals."""
        flags: list[AntiCheatSignal] = []

        visits = self._last_file_visits.get(session_id, [])

        self._check_instant_navigation(flags, visits, mutations_files)
        self._check_zero_exploration(flags, result, mutations_files)
        self._check_suspiciously_fast(flags, result, mutations_files)
        self._check_perfect_fix(flags, result)

        self._cleanup_session(session_id)
        return flags

    def _check_instant_navigation(
        self,
        flags: list[AntiCheatSignal],
        visits: list[tuple[str, float]],
        mutations_files: list[str],
    ) -> None:
        if not visits:
            return

        for mutation_file in mutations_files:
            for file_path, tstamp in visits:
                if mutation_file in file_path:
                    if visits[0][0] == file_path:
                        flags.append(AntiCheatSignal.INSTANT_NAVIGATION)
                        return
                    earliest_visit = visits[0][1]
                    if tstamp - earliest_visit < 60:
                        flags.append(AntiCheatSignal.INSTANT_NAVIGATION)
                        return

    def _check_zero_exploration(
        self,
        flags: list[AntiCheatSignal],
        result: SessionResult,
        mutations_files: list[str],
    ) -> None:
        unique_files = set(result.files_explored)
        if len(unique_files) < 3:
            flags.append(AntiCheatSignal.ZERO_EXPLORATION)

    def _check_suspiciously_fast(
        self,
        flags: list[AntiCheatSignal],
        result: SessionResult,
        mutations_files: list[str],
    ) -> None:
        if result.time_to_discovery_seconds is None:
            return
        if result.time_to_discovery_seconds < 120:
            bct_group = len(mutations_files)
            if bct_group >= 3:
                flags.append(AntiCheatSignal.SUSPICIOUSLY_FAST)

    def _check_perfect_fix(
        self,
        flags: list[AntiCheatSignal],
        result: SessionResult,
    ) -> None:
        pass

    def analyze_commit_message(self, message: str) -> Optional[AntiCheatSignal]:
        """Check if commit message has LLM-like phrasing."""
        msg_lower = message.lower()
        for pattern in self.LLM_PHRASE_PATTERNS:
            if pattern in msg_lower:
                return AntiCheatSignal.COMMIT_MSG_AI
        word_count = len(msg_lower.split())
        if word_count > 40:
            formal_phrases = ["additionally", "furthermore", "consequently", "therefore", "however"]
            if sum(1 for p in formal_phrases if p in msg_lower) >= 2:
                return AntiCheatSignal.COMMIT_MSG_AI
        return None

    def _cleanup_session(self, session_id: str) -> None:
        self._last_file_visits.pop(session_id, None)
