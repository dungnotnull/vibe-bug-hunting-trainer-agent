"""Pydantic schemas for BugHunterAgent.

Defines the core data models used throughout the system:
- InjectionCandidate: AST node identified as a potential bug injection site
- SessionResult: Outcome of a single bug hunt session
- DeveloperProfile: Persistent developer skill tracking
- BugPattern: Knowledge base entries from SECOND-KNOWLEDGE-BRAIN.md
- Hint: Socratic hint data for the 5-level hint system
- MutationRecord: Audit trail for each injected bug
- ValidationResult: Output of the mutation validation pipeline
- SessionState: State machine enum for hunt lifecycle
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────────────────────────


class PatternCategory(str, Enum):
    BOUNDARY = "boundary"
    TYPE_COERCION = "type_coercion"
    ASYNC_CONCURRENCY = "async_concurrency"
    STATE_MUTATION = "state_mutation"
    SECURITY = "security"
    LOGIC_ALGORITHM = "logic_algorithm"


class BugComplexityTier(int, Enum):
    BCT_1 = 1  # Obvious logic errors, wrong return values
    BCT_2 = 2  # Off-by-one, boundary conditions, type coercion
    BCT_3 = 3  # Race conditions, async/await pitfalls, subtle state mutation
    BCT_4 = 4  # Memory leaks, security vulnerabilities, concurrent data corruption
    BCT_5 = 5  # Heisenbug patterns, platform-specific edge cases, compiler quirks


class HintLevel(int, Enum):
    CATEGORY = 1  # "The bug is in the data transformation layer"
    FILE = 2  # "Look at src/utils/parser.js"
    FUNCTION = 3  # "Focus on the processItems() function"
    LINE_RANGE = 4  # "Lines 42-67 contain the issue"
    REVEAL = 5  # Full explanation (marks session as "assisted")


class SessionOutcome(str, Enum):
    FOUND_INDEPENDENTLY = "found_independently"
    FOUND_WITH_HINTS = "found_with_hints"
    AI_ASSISTED = "ai_assisted"
    SURRENDERED = "surrendered"
    TIMEOUT = "timeout"
    ROLLED_BACK = "rolled_back"


class SessionPhase(str, Enum):
    IDLE = "idle"
    INJECTED = "injected"
    HUNTING = "hunting"
    DISCOVERED = "discovered"
    SURRENDERED = "surrendered"


class AntiCheatSignal(str, Enum):
    INSTANT_NAVIGATION = "instant_navigation"
    ZERO_EXPLORATION = "zero_exploration"
    SUSPICIOUSLY_FAST = "suspiciously_fast"
    PERFECT_FIX = "perfect_fix"
    COMMIT_MSG_AI = "commit_msg_ai"


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    RUBY = "ruby"


# ─── Core Schemas ────────────────────────────────────────────────────────────


class InjectionCandidate(BaseModel):
    """An AST node identified as a viable bug injection site."""

    file: str
    line_start: int
    line_end: int
    ast_node_type: str  # function_def, if_statement, assignment, etc.
    pattern_category: PatternCategory
    detectability_score: float = Field(ge=0.0, le=1.0)
    realism_score: float = Field(ge=0.0, le=1.0)
    difficulty_level: BugComplexityTier
    prerequisite_patterns: list[str] = Field(default_factory=list)
    function_name: Optional[str] = None
    source_snippet: Optional[str] = None


class MutationRecord(BaseModel):
    """Records a single injected bug for rollback and auditing."""

    mutation_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    file: str
    line_start: int
    line_end: int
    original_content: str
    injected_content: str
    pattern_category: PatternCategory
    bug_pattern_id: str  # e.g., "BP-001"
    difficulty: BugComplexityTier
    injected_at: datetime = Field(default_factory=datetime.utcnow)
    time_limit: int = 14400  # 4 hours in seconds
    rolled_back: bool = False
    rolled_back_at: Optional[datetime] = None


class Hint(BaseModel):
    """A single Socratic hint delivered to the developer."""

    level: HintLevel
    content: str
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    dss_penalty: int  # Negative DSS impact, e.g., -15 to -40


class ValidationResult(BaseModel):
    """Output of the mutation validation pipeline."""

    passed: bool
    failures: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    # Individual check results:
    #   syntax_valid, linter_silent, type_checker_silent,
    #   not_identical, realism_check, scope_safe


class SessionResult(BaseModel):
    """Complete outcome of a single bug hunt session."""

    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    language: Language
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    outcome: Optional[SessionOutcome] = None
    bug_pattern_id: str = ""
    bug_pattern_name: str = ""
    time_to_discovery_seconds: Optional[int] = None
    hints_used: list[Hint] = Field(default_factory=list)
    dss_before: int = 1200
    dss_after: int = 1200
    dss_delta: int = 0
    files_explored: list[str] = Field(default_factory=list)
    anti_cheat_flags: list[AntiCheatSignal] = Field(default_factory=list)
    mutations: list[MutationRecord] = Field(default_factory=list)
    report_path: Optional[str] = None


class PatternMastery(BaseModel):
    """Tracks a developer's proficiency with a specific bug pattern."""

    pattern_id: str
    consecutive_wins: int = 0
    total_attempts: int = 0
    mastered: bool = False
    last_seen: Optional[datetime] = None
    ease_factor: float = 2.5  # SM-2 algorithm
    interval_days: int = 1  # SM-2: days until next review
    next_review: Optional[datetime] = None


class DeveloperProfile(BaseModel):
    """Persistent developer skill profile stored at ~/.bughunter/profile.json."""

    developer_id: str = ""  # sha256 of git email
    dss: int = 1200  # Developer Skill Score (ELO-style, 0-3000)
    sessions_total: int = 0
    sessions_won: int = 0
    avg_time_to_find_seconds: float = 0.0
    hint_usage_rate: float = 0.0
    ai_assist_detected_count: int = 0
    pattern_mastery: dict[str, PatternMastery] = Field(default_factory=dict)
    spaced_repetition_queue: list[str] = Field(default_factory=list)
    next_session_bct: BugComplexityTier = BugComplexityTier.BCT_1
    session_history: list[str] = Field(default_factory=list)  # session IDs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    """Runtime state of the current hunt session."""

    session_id: Optional[str] = None
    phase: SessionPhase = SessionPhase.IDLE
    project_path: Optional[Path] = None
    original_branch: Optional[str] = None
    session_branch: Optional[str] = None
    mutations: list[MutationRecord] = Field(default_factory=list)
    hints_given: int = 0
    started_at: Optional[datetime] = None
