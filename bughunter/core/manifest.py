"""Encrypted session manifest using Fernet symmetric encryption.

Stores mutation records and session data in encrypted JSON files at
~/.bughunter/sessions/{session_id}.enc — never in plain sight.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from bughunter.schemas.models import MutationRecord, SessionResult, SessionState


class ManifestError(Exception):
    """Raised when manifest operations fail (corrupt, missing, wrong key)."""


class ManifestStore:
    """Manages encrypted session manifests on disk."""

    def __init__(self, base_path: Optional[Path] = None):
        self._base_path = base_path or Path.home() / ".bughunter" / "sessions"
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._key = self._load_or_create_key()

    @property
    def sessions_dir(self) -> Path:
        return self._base_path

    def _key_path(self) -> Path:
        return self._base_path.parent / ".manifest_key"

    def _load_or_create_key(self) -> Fernet:
        key_path = self._key_path()
        if key_path.exists():
            with open(key_path, "rb") as f:
                key = f.read()
            logger.debug("Loaded existing manifest encryption key")
        else:
            key = Fernet.generate_key()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            # Restrictive permissions on the key file
            with open(key_path, "wb") as f:
                f.write(key)
            os.chmod(key_path, 0o600)
            logger.debug("Generated new manifest encryption key")
        return Fernet(key)

    def _session_path(self, session_id: str) -> Path:
        return self._base_path / f"{session_id}.enc"

    def save_session(self, state: SessionState) -> str:
        """Encrypt and persist session state. Returns session_id."""
        if not state.session_id:
            raise ManifestError("Session state has no session_id")

        data = {
            "session_id": state.session_id,
            "phase": state.phase.value,
            "original_branch": state.original_branch,
            "session_branch": state.session_branch,
            "mutations": [
                m.model_dump(mode="json") for m in state.mutations
            ],
            "hints_given": state.hints_given,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "saved_at": datetime.utcnow().isoformat(),
        }

        serialized = json.dumps(data, indent=2)
        encrypted = self._key.encrypt(serialized.encode())

        path = self._session_path(state.session_id)
        with open(path, "wb") as f:
            f.write(encrypted)
        os.chmod(path, 0o600)

        logger.debug(f"Saved encrypted manifest: {state.session_id}")
        return state.session_id

    def load_session(self, session_id: str) -> dict:
        """Decrypt and return session data as dict."""
        path = self._session_path(session_id)
        if not path.exists():
            raise ManifestError(f"Session manifest not found: {session_id}")

        try:
            with open(path, "rb") as f:
                encrypted = f.read()
            decrypted = self._key.decrypt(encrypted)
            return json.loads(decrypted)
        except InvalidToken:
            raise ManifestError(
                f"Cannot decrypt session {session_id}: key mismatch or corrupted file"
            )

    def delete_session(self, session_id: str) -> None:
        """Remove an encrypted session manifest."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted manifest: {session_id}")

    def list_sessions(self) -> list[str]:
        """List all session IDs currently stored."""
        ids = []
        for f in self._base_path.glob("*.enc"):
            ids.append(f.stem)
        return sorted(ids)

    def save_result(self, result: SessionResult) -> None:
        """Save a session result report alongside the encrypted manifest."""
        if not result.session_id:
            raise ManifestError("SessionResult has no session_id")

        report_path = self._base_path / f"{result.session_id}_report.json"
        with open(report_path, "w") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2, default=str)
        result.report_path = str(report_path)
        logger.debug(f"Saved session report: {report_path}")

    def lock_key(self) -> bytes:
        """Expose the raw encryption key hash for integrity verification."""
        import hashlib
        return hashlib.sha256(self._key._encryption_key).digest()
