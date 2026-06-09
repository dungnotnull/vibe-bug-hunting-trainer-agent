"""Configuration management — loads from .env and defaults.

Sources (highest to lowest priority):
1. Environment variables (already set)
2. .env file in project root
3. Hard-coded defaults (sandbox-safe)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """Central configuration for BugHunterAgent.

    Loads from environment variables with sandbox-safe defaults.
    """

    # Environment & safety
    bughunter_env: str = "sandbox"
    project_name: str = "vibe-bug-hunting-trainer-agent"

    # Paths
    data_dir: Path = field(default_factory=lambda: Path.home() / ".bughunter")
    sessions_dir: Path = field(default_factory=lambda: Path.home() / ".bughunter" / "sessions")
    logs_dir: Path = field(default_factory=lambda: Path.home() / ".bughunter" / "logs")
    knowledge_brain_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "SECOND-KNOWLEDGE-BRAIN.md"
    )

    # Session settings
    session_timeout_minutes: int = 240  # 4 hours
    max_concurrent_bugs: int = 3
    max_mutation_retries: int = 5
    mutation_realism_threshold: float = 0.7

    # ELO / DSS settings
    dss_starting_score: int = 1200
    dss_k_factor: float = 32.0
    dss_max_score: int = 3000

    # Hint system
    hint_dss_penalty_level_1: int = 15
    hint_dss_penalty_level_2: int = 20
    hint_dss_penalty_level_3: int = 25
    hint_dss_penalty_level_4: int = 30
    hint_dss_penalty_level_5: int = 40

    # LLM settings (for future use — not pulled/run now)
    local_model: str = "qwen2.5-coder:7b"
    local_model_provider: str = "ollama"
    external_llm_provider: str = ""
    external_llm_model: str = ""
    external_llm_api_key: str = ""

    # Anti-cheat thresholds
    anti_cheat_min_time_seconds: int = 30
    anti_cheat_min_files_explored: int = 3

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def load_config(env_path: Optional[Path] = None) -> Config:
    """Load configuration from .env file and environment variables.

    Args:
        env_path: Path to .env file. Defaults to project root .env.
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"

    if env_path.exists():
        load_dotenv(env_path)

    def _env(key: str, default: str) -> str:
        return os.environ.get(key, default)

    def _env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, default))
        except (ValueError, TypeError):
            return default

    def _env_float(key: str, default: float) -> float:
        try:
            return float(os.environ.get(key, default))
        except (ValueError, TypeError):
            return default

    return Config(
        bughunter_env=_env("BUGHUNTER_ENV", "sandbox"),
        session_timeout_minutes=_env_int("BUGHUNTER_SESSION_TIMEOUT", 240),
        max_concurrent_bugs=_env_int("BUGHUNTER_MAX_BUGS", 3),
        max_mutation_retries=_env_int("BUGHUNTER_MUTATION_RETRIES", 5),
        mutation_realism_threshold=_env_float("BUGHUNTER_REALISM_THRESHOLD", 0.7),
        external_llm_provider=_env("BUGHUNTER_EXTERNAL_LLM", ""),
        external_llm_model=_env("BUGHUNTER_EXTERNAL_MODEL", ""),
        external_llm_api_key=_env("BUGHUNTER_EXTERNAL_API_KEY", ""),
        local_model=_env("BUGHUNTER_LOCAL_MODEL", "qwen2.5-coder:7b"),
    )
