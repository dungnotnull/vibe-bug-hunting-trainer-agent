"""Environment safety gate — the hard requirement.

Enforces CLAUDE.md §3.4 (Bug Injection Safety Rules) and §7 (What the Agent Must Never Do):
- NEVER activate unless BUGHUNTER_ENV=sandbox
- NEVER run in production, CI, or remote environments
- ALWAYS verify the environment before any injection operation
"""

from __future__ import annotations

import os
import platform
import socket
import sys
from pathlib import Path

from loguru import logger


class SafetyGateError(Exception):
    """Raised when safety gate blocks activation."""


class SafetyGate:
    """Validates the execution environment is safe for bug injection.

    The safety gate must pass BEFORE any mutation or injection code runs.
    This is non-negotiable and enforced at multiple call sites.
    """

    REQUIRED_ENV_VAR = "BUGHUNTER_ENV"
    REQUIRED_ENV_VALUE = "sandbox"

    CI_ENV_VARS = [
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "JENKINS_HOME",
        "TRAVIS",
        "CIRCLECI",
        "BUILD_ID",
        "BUILD_NUMBER",
        "TEAMCITY_VERSION",
        "BAMBOO_AGENT",
    ]

    PRODUCTION_HOSTNAME_PATTERNS = [
        "prod",
        "production",
        "live",
        "deploy",
    ]

    @classmethod
    def check(cls) -> None:
        """Run all safety checks. Raises SafetyGateError if any fail."""
        cls._check_env_var()
        cls._check_not_ci()
        cls._check_local_environment()
        cls._check_not_root()
        cls._check_sandbox_directory()
        logger.debug("Safety gate: all checks passed")

    @classmethod
    def _check_env_var(cls) -> None:
        value = os.environ.get(cls.REQUIRED_ENV_VAR, "")
        if value != cls.REQUIRED_ENV_VALUE:
            raise SafetyGateError(
                f"BugHunterAgent: Not in sandbox environment.\n"
                f"  Current {cls.REQUIRED_ENV_VAR}='{value or '(unset)'}'\n"
                f"  Required: {cls.REQUIRED_ENV_VAR}={cls.REQUIRED_ENV_VALUE}\n"
                f"  Set 'export BUGHUNTER_ENV=sandbox' to activate.\n"
                f"  NEVER run in production."
            )

    @classmethod
    def _check_not_ci(cls) -> None:
        for var in cls.CI_ENV_VARS:
            if os.environ.get(var):
                raise SafetyGateError(
                    f"BugHunterAgent: CI environment detected ({var}={os.environ[var]}).\n"
                    f"  Bug injection is NEVER allowed in CI/CD pipelines.\n"
                    f"  Aborting."
                )

    @classmethod
    def _check_local_environment(cls) -> None:
        hostname = socket.gethostname().lower()
        for pattern in cls.PRODUCTION_HOSTNAME_PATTERNS:
            if pattern in hostname:
                raise SafetyGateError(
                    f"BugHunterAgent: Hostname '{hostname}' contains production indicator "
                    f"'{pattern}'.\nAborting."
                )

    @classmethod
    def _check_not_root(cls) -> None:
        if platform.system() != "Windows":
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                raise SafetyGateError(
                    "BugHunterAgent: Running as root is not allowed.\n"
                    "Bug injection must run as a normal user in a sandbox."
                )

    @classmethod
    def _check_sandbox_directory(cls) -> None:
        cwd = Path.cwd()
        resolved = cwd.resolve()
        home = Path.home().resolve()
        if resolved == home or resolved == Path("/"):
            raise SafetyGateError(
                f"BugHunterAgent: Refusing to run in home or root directory: {resolved}\n"
                f"  Use a dedicated sandbox project directory."
            )

    @classmethod
    def is_safe(cls) -> bool:
        """Non-raising check — returns True if environment is safe."""
        try:
            cls.check()
            return True
        except SafetyGateError:
            return False


def guard(fn=None):
    """Decorator to enforce safety gate on function entry."""
    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            SafetyGate.check()
            return func(*args, **kwargs)

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator
