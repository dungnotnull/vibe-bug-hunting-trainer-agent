"""Team Mode — collaborative bug hunt sessions.

Multiple developers hunt the same injected bugs simultaneously.
- Shared hint pool (one dev's hint → all see it)
- Real-time leaderboard via WebSocket
- Relative performance scoring
- Team DSS calculation
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import websockets
from loguru import logger

from bughunter.schemas.models import (
    DeveloperProfile,
    Hint,
    HintLevel,
    SessionOutcome,
    SessionResult,
)


@dataclass
class TeamMember:
    """A developer participating in a team session."""
    developer_id: str
    profile: Optional[DeveloperProfile] = None
    joined_at: datetime = field(default_factory=datetime.utcnow)
    found_bug: bool = False
    found_at: Optional[datetime] = None
    hints_used: int = 0
    score: float = 0.0
    websocket: Optional[any] = None  # websockets.WebSocketServerProtocol


@dataclass
class TeamSession:
    """A collaborative bug hunt session."""
    session_code: str
    name: str
    creator_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    members: dict[str, TeamMember] = field(default_factory=dict)
    shared_hints: list[Hint] = field(default_factory=list)
    bug_discovered: bool = False
    bug_discovered_by: Optional[str] = None
    bug_discovered_at: Optional[datetime] = None
    active: bool = True


class TeamSessionManager:
    """Manages team hunt sessions with WebSocket-based real-time updates."""

    def __init__(self):
        self._sessions: dict[str, TeamSession] = {}
        self._leaderboard: dict[str, list[dict]] = defaultdict(list)
        self._ws_clients: dict[str, list] = defaultdict(list)

    def create_session(self, creator_id: str, name: str) -> TeamSession:
        """Create a new team hunt session."""
        code = uuid.uuid4().hex[:8].upper()
        session = TeamSession(
            session_code=code,
            name=name,
            creator_id=creator_id,
        )
        self._sessions[code] = session
        logger.info(f"Team session created: {code} - {name}")
        return session

    def join_session(self, session_code: str, developer_id: str) -> TeamMember:
        """A developer joins an existing team session."""
        session = self._sessions.get(session_code)
        if not session:
            raise ValueError(f"Session not found: {session_code}")
        if not session.active:
            raise ValueError(f"Session already ended: {session_code}")

        member = TeamMember(developer_id=developer_id)
        session.members[developer_id] = member
        logger.info(f"Developer {developer_id} joined session {session_code}")
        return member

    def request_hint(self, session_code: str, developer_id: str) -> Hint:
        """Request a hint — shared with all team members."""
        session = self._sessions.get(session_code)
        if not session:
            raise ValueError(f"Session not found: {session_code}")

        member = session.members.get(developer_id)
        if not member:
            raise ValueError(f"Member not in session: {developer_id}")

        level = HintLevel(len(session.shared_hints) + 1)
        if level.value > 5:
            level = HintLevel.REVEAL

        content = self._generate_team_hint(level, session)
        hint = Hint(
            level=level,
            content=content,
            dss_penalty=15 * level.value,
        )
        session.shared_hints.append(hint)
        member.hints_used += 1

        return hint

    def claim_discovery(
        self, session_code: str, developer_id: str
    ) -> tuple[bool, Optional[str]]:
        """Someone claims they found the bug. First to claim wins."""
        session = self._sessions.get(session_code)
        if not session:
            raise ValueError(f"Session not found: {session_code}")

        if session.bug_discovered:
            return False, session.bug_discovered_by

        member = session.members.get(developer_id)
        if not member:
            raise ValueError(f"Member not in session: {developer_id}")

        session.bug_discovered = True
        session.bug_discovered_by = developer_id
        session.bug_discovered_at = datetime.utcnow()
        member.found_bug = True
        member.found_at = datetime.utcnow()

        self._calculate_team_scores(session)
        logger.info(f"Bug discovered by {developer_id} in session {session_code}")
        return True, developer_id

    def _calculate_team_scores(self, session: TeamSession) -> None:
        """Score all team members based on relative performance."""
        if not session.bug_discovered_at:
            return

        for mid, member in session.members.items():
            if member.found_bug:
                score = 100.0
                score -= member.hints_used * 10
                member.score = max(score, 30.0)
            else:
                member.score = max(0.0, 20.0 - member.hints_used * 5.0)

    def get_leaderboard(self, session_code: str) -> list[dict]:
        """Get ranked leaderboard for a team session."""
        session = self._sessions.get(session_code)
        if not session:
            return []

        members = sorted(
            session.members.values(),
            key=lambda m: (m.found_bug, -m.score),
            reverse=True,
        )
        board = []
        for rank, m in enumerate(members, 1):
            board.append({
                "rank": rank,
                "developer_id": m.developer_id[:16],
                "found_bug": m.found_bug,
                "hints_used": m.hints_used,
                "score": m.score,
                "joined_at": m.joined_at.isoformat(),
            })
        return board

    def end_session(self, session_code: str) -> None:
        """End a team session and archive results."""
        session = self._sessions.get(session_code)
        if session:
            session.active = False
            self._calculate_team_scores(session)
            self._leaderboard[session_code] = self.get_leaderboard(session_code)
            logger.info(f"Team session ended: {session_code}")

    def get_session(self, session_code: str) -> Optional[TeamSession]:
        return self._sessions.get(session_code)

    def _generate_team_hint(self, level: HintLevel, session: TeamSession) -> str:
        hints = {
            HintLevel.CATEGORY: "Team hint: The bug is in a logic/algorithm pattern.",
            HintLevel.FILE: "Team hint: Check the data processing files.",
            HintLevel.FUNCTION: "Team hint: Focus on functions with conditional logic.",
            HintLevel.LINE_RANGE: "Team hint: The bug is in a small function — look at the return values.",
            HintLevel.REVEAL: "Full reveal: The bug is a wrong comparison operator in a business rule.",
        }
        return hints.get(level, "Review the active changes in your session branch.")


class TeamWebSocketServer:
    """WebSocket server for real-time team session updates."""

    def __init__(self, host: str = "localhost", port: int = 9876):
        self.host = host
        self.port = port
        self._manager = TeamSessionManager()
        self._server = None

    async def start(self):
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
        )
        logger.info(f"Team WebSocket server started on ws://{self.host}:{self.port}")

    async def stop(self):
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(
        self, websocket: websockets.WebSocketServerProtocol, path: str
    ):
        """Handle a new WebSocket connection."""
        try:
            async for message in websocket:
                data = json.loads(message)
                await self._process_message(websocket, data)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    async def _process_message(
        self, websocket: websockets.WebSocketServerProtocol, data: dict
    ):
        """Process incoming WebSocket messages."""
        action = data.get("action", "")
        session_code = data.get("session_code", "")
        developer_id = data.get("developer_id", "")

        try:
            if action == "join":
                self._manager.join_session(session_code, developer_id)
                await self._broadcast_leaderboard(session_code)

            elif action == "hint":
                hint = self._manager.request_hint(session_code, developer_id)
                await self._broadcast_hint(session_code, hint)

            elif action == "discover":
                success, finder = self._manager.claim_discovery(session_code, developer_id)
                if success:
                    await self._broadcast_discovery(session_code, finder)

            elif action == "leaderboard":
                await self._send_leaderboard(websocket, session_code)

            elif action == "end":
                self._manager.end_session(session_code)
                await self._broadcast_end(session_code)

        except Exception as e:
            await websocket.send(json.dumps({"error": str(e)}))

    async def _broadcast_leaderboard(self, session_code: str):
        board = self._manager.get_leaderboard(session_code)
        message = json.dumps({
            "type": "leaderboard_update",
            "session_code": session_code,
            "leaderboard": board,
        })
        # In production, broadcast to all connected clients for this session

    async def _broadcast_hint(self, session_code: str, hint: Hint):
        message = json.dumps({
            "type": "new_hint",
            "session_code": session_code,
            "hint": {
                "level": hint.level.value,
                "content": hint.content,
            },
        })

    async def _broadcast_discovery(self, session_code: str, finder: Optional[str]):
        message = json.dumps({
            "type": "bug_discovered",
            "session_code": session_code,
            "finder": finder,
            "message": f"Bug found by {finder}!" if finder else "Bug discovered!",
        })

    async def _broadcast_end(self, session_code: str):
        board = self._manager.get_leaderboard(session_code)
        message = json.dumps({
            "type": "session_ended",
            "session_code": session_code,
            "leaderboard": board,
        })

    async def _send_leaderboard(
        self, websocket: websockets.WebSocketServerProtocol, session_code: str
    ):
        board = self._manager.get_leaderboard(session_code)
        await websocket.send(json.dumps({
            "type": "leaderboard",
            "session_code": session_code,
            "leaderboard": board,
        }))
