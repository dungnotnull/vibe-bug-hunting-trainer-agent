"""Skill Profiler — ELO scoring, DSS calculation, developer profile management.

Implements the ELO-based Developer Skill Score (DSS) system from CLAUDE.md §3.3:
- Starting score: 1200
- K-factor: 32
- Outcome-based rating adjustments
- Pattern mastery tracking
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from bughunter.schemas.models import (
    AntiCheatSignal,
    BugComplexityTier,
    DeveloperProfile,
    HintLevel,
    PatternMastery,
    SessionOutcome,
    SessionResult,
)


BCT_ELO_MAP = {
    BugComplexityTier.BCT_1: 800,
    BugComplexityTier.BCT_2: 1300,
    BugComplexityTier.BCT_3: 1700,
    BugComplexityTier.BCT_4: 2100,
    BugComplexityTier.BCT_5: 2500,
}

HINT_PENALTIES = {
    HintLevel.CATEGORY: 15,
    HintLevel.FILE: 20,
    HintLevel.FUNCTION: 25,
    HintLevel.LINE_RANGE: 30,
    HintLevel.REVEAL: 40,
}

OUTCOME_SCORES = {
    SessionOutcome.FOUND_INDEPENDENTLY: 1.0,
    SessionOutcome.FOUND_WITH_HINTS: 0.5,
    SessionOutcome.SURRENDERED: 0.2,
    SessionOutcome.TIMEOUT: 0.1,
    SessionOutcome.AI_ASSISTED: 0.0,
}

FIRST_TIME_BONUS = 1.5
SECURITY_BONUS = 1.3


class SkillProfiler:
    """Manages developer skill scoring and profile persistence."""

    def __init__(self, profile_path: Optional[Path] = None):
        self._profile_path = profile_path or Path.home() / ".bughunter" / "profile.json"
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profile = self._load_profile()

    @property
    def profile(self) -> DeveloperProfile:
        return self._profile

    def get_dss(self) -> int:
        return self._profile.dss

    def get_next_bct(self) -> BugComplexityTier:
        return self._profile.next_session_bct

    def _load_profile(self) -> DeveloperProfile:
        if self._profile_path.exists():
            try:
                with open(self._profile_path, "r") as f:
                    data = json.load(f)
                data["pattern_mastery"] = {
                    k: PatternMastery(**v) if isinstance(v, dict) else v
                    for k, v in data.get("pattern_mastery", {}).items()
                }
                return DeveloperProfile(**data)
            except Exception as e:
                logger.warning(f"Failed to load profile, creating new: {e}")
        return DeveloperProfile()

    def save_profile(self) -> None:
        self._profile.updated_at = datetime.utcnow()
        data = self._profile.model_dump(mode="json")
        with open(self._profile_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def update_dss(self, result: SessionResult) -> int:
        """Calculate and apply ELO-based DSS update."""
        bug_elo = BCT_ELO_MAP.get(
            BugComplexityTier(result.dss_before // 400 + 1),
            BCT_ELO_MAP[BugComplexityTier.BCT_2],
        )

        expected = 1.0 / (1.0 + 10.0 ** ((bug_elo - self._profile.dss) / 400.0))

        outcome = result.outcome or SessionOutcome.TIMEOUT
        actual = OUTCOME_SCORES.get(outcome, 0.2)

        if outcome == SessionOutcome.FOUND_INDEPENDENTLY:
            multiplier = 1.0
            if result.bug_pattern_id not in self._profile.pattern_mastery:
                multiplier = FIRST_TIME_BONUS
            if "security" in result.bug_pattern_name.lower():
                multiplier *= SECURITY_BONUS
            actual *= multiplier

        if result.hints_used:
            for hint in result.hints_used:
                actual -= HINT_PENALTIES.get(hint.level, 15) / 500.0
            actual = max(0.0, actual)

        delta = int(32.0 * (actual - expected))
        new_dss = max(0, min(3000, self._profile.dss + delta))

        result.dss_before = self._profile.dss
        result.dss_after = new_dss
        result.dss_delta = delta

        self._profile.dss = new_dss
        self._profile.sessions_total += 1
        if outcome in (SessionOutcome.FOUND_INDEPENDENTLY, SessionOutcome.FOUND_WITH_HINTS):
            self._profile.sessions_won += 1
        if result.anti_cheat_flags:
            self._profile.ai_assist_detected_count += 1

        # Update pattern mastery
        mastery = self._profile.pattern_mastery.get(
            result.bug_pattern_id,
            PatternMastery(pattern_id=result.bug_pattern_id),
        )
        mastery.total_attempts += 1
        if outcome == SessionOutcome.FOUND_INDEPENDENTLY:
            mastery.consecutive_wins += 1
            if mastery.consecutive_wins >= 3:
                mastery.mastered = True
        else:
            mastery.consecutive_wins = 0
            mastery.mastered = False
        mastery.last_seen = datetime.utcnow()
        self._profile.pattern_mastery[result.bug_pattern_id] = mastery

        self._adjust_difficulty()
        self.save_profile()
        return new_dss

    def _adjust_difficulty(self) -> None:
        """Auto-adjust BCT based on recent performance."""
        wins = self._profile.sessions_won
        total = self._profile.sessions_total
        if total < 3:
            return

        win_rate = wins / total if total > 0 else 0.0

        if win_rate > 0.85 and self._profile.next_session_bct < BugComplexityTier.BCT_5:
            self._profile.next_session_bct = BugComplexityTier(
                self._profile.next_session_bct.value + 1
            )
            logger.info(f"BCT increased to {self._profile.next_session_bct.name}")
        elif win_rate < 0.3 and self._profile.next_session_bct > BugComplexityTier.BCT_1:
            self._profile.next_session_bct = BugComplexityTier(
                self._profile.next_session_bct.value - 1
            )
            logger.info(f"BCT decreased to {self._profile.next_session_bct.name}")

    def get_hint_penalty(self, level: HintLevel) -> int:
        return HINT_PENALTIES.get(level, 15)

    def set_developer_id(self, git_email: str) -> None:
        import hashlib
        self._profile.developer_id = hashlib.sha256(git_email.encode()).hexdigest()[:16]
        self.save_profile()
