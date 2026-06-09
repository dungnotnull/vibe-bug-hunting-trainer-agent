"""Centralized logging configuration using Loguru.

Silent by default — only writes to file unless verbosity is enabled.
The agent operates covertly, so console output is minimal unless the
developer explicitly requests verbose mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(
    verbose: bool = False,
    log_dir: Path | None = None,
) -> None:
    """Initialize logging with silent-by-default behavior.

    Args:
        verbose: If True, enable DEBUG-level console output.
        log_dir: Directory for log files. Defaults to ~/.bughunter/logs/.
    """
    logger.remove()  # Remove default handler

    log_dir = log_dir or Path.home() / ".bughunter" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # File sink — always active, rotation on size
    logger.add(
        log_dir / "bughunter_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        enqueue=True,  # Thread-safe
    )

    # Error file sink — separate for critical issues
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        rotation="5 MB",
        retention="60 days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}\n{exception}",
        enqueue=True,
    )

    if verbose:
        # Console output for verbose/debug mode
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
            colorize=True,
        )
    else:
        # Minimal console — warnings and errors only (covert mode)
        logger.add(
            sys.stderr,
            level="WARNING",
            format="<level>{level}</level> | {message}",
            colorize=True,
        )

    logger.debug("Logging configured — silent mode active")


def silence_console() -> None:
    """Ensure absolutely no console output (for stealth injection phase)."""
    logger.remove()
    log_dir = Path.home() / ".bughunter" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "bughunter_{time}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        enqueue=True,
    )
