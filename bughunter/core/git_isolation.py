"""Git branch isolation using GitPython.

All bug injections operate on a dedicated session branch (bughunter/session-{id}),
never on main/master. Rollback is a simple git checkout back to the original branch.

CLAUDE.md §3.2 (Stealth Principle): injections must never be visible via git status
on the developer's working branch.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import git
from loguru import logger


class GitBranchError(Exception):
    """Raised when git operations fail (not a repo, dirty state, etc.)."""


class GitIsolation:
    """Manages git branch isolation for bug injection sessions.

    Workflow:
    1. snapshot() — save current branch name and ensure clean state
    2. create_session_branch() — create bughunter/session-{id} from current HEAD
    3. [bugs are injected on the session branch]
    4. rollback() — checkout original branch, delete session branch (optional)
    """

    SESSION_BRANCH_PREFIX = "bughunter/session"

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        try:
            self.repo = git.Repo(self.project_path, search_parent_directories=True)
        except git.InvalidGitRepositoryError:
            raise GitBranchError(
                f"Not a git repository: {self.project_path}\n"
                f"  BugHunterAgent requires a git-tracked project for safe rollback."
            )
        self._original_branch: Optional[str] = None
        self._session_branch: Optional[str] = None

    @property
    def original_branch(self) -> Optional[str]:
        return self._original_branch

    @property
    def session_branch(self) -> Optional[str]:
        return self._session_branch

    def snapshot(self) -> str:
        """Record current state: branch name and clean working tree.

        Returns the current branch name.
        Raises GitBranchError if repo is dirty (uncommitted changes).
        """
        if self.repo.is_dirty(untracked_files=False):
            raise GitBranchError(
                "Working tree has uncommitted changes.\n"
                "  Commit or stash changes before starting a bug hunt session.\n"
                f"  Dirty files: {self.repo.git.diff('--name-only')}"
            )

        try:
            self._original_branch = self.repo.active_branch.name
        except TypeError:
            # Detached HEAD
            self._original_branch = self.repo.head.commit.hexsha[:8]
            logger.warning(f"Detached HEAD at {self._original_branch}")

        logger.debug(f"Snapshot: branch={self._original_branch}")
        return self._original_branch

    def create_session_branch(self, session_id: Optional[str] = None) -> str:
        """Create an isolated session branch from current HEAD.

        Args:
            session_id: Optional session ID. Generated if not provided.

        Returns:
            The session branch name (bughunter/session-{id}).

        Raises:
            GitBranchError: If branch already exists or repo is in bad state.
        """
        if session_id is None:
            session_id = uuid.uuid4().hex[:12]

        branch_name = f"{self.SESSION_BRANCH_PREFIX}-{session_id}"

        # Check if branch already exists
        if branch_name in [b.name for b in self.repo.branches]:
            raise GitBranchError(
                f"Session branch already exists: {branch_name}\n"
                f"  This should not happen — session IDs are unique."
            )

        try:
            # Create and switch to the new branch
            current = self.repo.active_branch
            new_branch = self.repo.create_head(branch_name)
            new_branch.checkout()
        except Exception as e:
            raise GitBranchError(f"Failed to create session branch: {e}")

        self._session_branch = branch_name
        logger.debug(f"Created session branch: {branch_name}")
        return branch_name

    def rollback(self, delete_branch: bool = True) -> str:
        """Rollback to original branch, optionally deleting the session branch.

        Returns the name of the branch checked out after rollback.

        Raises:
            GitBranchError: If original branch was not recorded or checkout fails.
        """
        if not self._original_branch:
            raise GitBranchError(
                "Cannot rollback: no original branch recorded.\n"
                "  Did you call snapshot() before creating the session branch?"
            )

        try:
            # Force checkout original branch (discard any changes)
            self.repo.git.checkout(self._original_branch, force=True)

            if delete_branch and self._session_branch:
                self.repo.delete_head(self._session_branch, force=True)
                logger.debug(f"Deleted session branch: {self._session_branch}")

            logger.debug(f"Rolled back to: {self._original_branch}")
            return self._original_branch

        except Exception as e:
            raise GitBranchError(
                f"CRITICAL: Rollback failed: {e}\n"
                f"  Original branch: {self._original_branch}\n"
                f"  Session branch: {self._session_branch}\n"
                f"  Manual recovery: git checkout {self._original_branch}"
            )

    def is_on_session_branch(self) -> bool:
        """Check if HEAD is currently on the session branch."""
        if not self._session_branch:
            return False
        try:
            return self.repo.active_branch.name == self._session_branch
        except TypeError:
            return False

    def verify_clean_state(self) -> bool:
        """Ensure the working tree is clean (no uncommitted changes from injection)."""
        return not self.repo.is_dirty(untracked_files=False)

    def get_session_diff(self) -> str:
        """Get the diff between original and session branch. For diagnostics only."""
        if not self._original_branch or not self._session_branch:
            return ""
        try:
            return self.repo.git.diff(f"{self._original_branch}..{self._session_branch}")
        except git.GitCommandError:
            return ""

    def list_active_sessions(self) -> list[str]:
        """List all session branches still present in the repo."""
        prefix = self.SESSION_BRANCH_PREFIX
        return [b.name for b in self.repo.branches if b.name.startswith(prefix)]
