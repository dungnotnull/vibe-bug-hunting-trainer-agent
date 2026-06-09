"""FastAPI web server — wraps BugHunterAgent CLI as REST API + WebSocket.

Serves:
- Developer profile & DSS dashboard
- Live session status via WebSocket
- Session report rendering
- Team leaderboard
- LLM provider configuration
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="BugHunterAgent API",
    description="Covert debug skill training system — web dashboard backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_ws_clients: dict[str, list[WebSocket]] = {}


class ProfileResponse(BaseModel):
    developer_id: str
    dss: int
    sessions_total: int
    sessions_won: int
    win_rate: float
    avg_time_to_find_seconds: float
    hint_usage_rate: float
    ai_assist_detected_count: int
    next_session_bct: int
    pattern_mastery: dict
    created_at: str
    updated_at: str


class SessionInfo(BaseModel):
    session_id: str
    phase: str
    started_at: Optional[str]
    bugs_injected: int
    hints_used: int


class LLMConfigRequest(BaseModel):
    provider: str = ""
    model: str = ""
    api_key: str = ""


@app.get("/")
async def root():
    return {"service": "BugHunterAgent API", "version": "0.1.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/profile", response_model=ProfileResponse)
async def get_profile():
    """Get the current developer profile."""
    from bughunter.core.skill_profiler import SkillProfiler
    profiler = SkillProfiler()
    p = profiler.profile

    total = max(p.sessions_total, 1)
    return ProfileResponse(
        developer_id=p.developer_id,
        dss=p.dss,
        sessions_total=p.sessions_total,
        sessions_won=p.sessions_won,
        win_rate=p.sessions_won / total,
        avg_time_to_find_seconds=p.avg_time_to_find_seconds,
        hint_usage_rate=p.hint_usage_rate,
        ai_assist_detected_count=p.ai_assist_detected_count,
        next_session_bct=p.next_session_bct.value,
        pattern_mastery={
            pid: m.model_dump(mode="json")
            for pid, m in p.pattern_mastery.items()
        },
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@app.get("/api/sessions")
async def list_sessions(limit: int = Query(10, ge=1, le=100)):
    """List past session reports."""
    from bughunter.core.manifest import ManifestStore
    store = ManifestStore()
    sessions = store.list_sessions()
    results = []
    for sid in sessions[-limit:]:
        try:
            data = store.load_session(sid)
            results.append({
                "session_id": sid,
                "started_at": data.get("started_at"),
                "phase": data.get("phase"),
            })
        except Exception:
            results.append({"session_id": sid, "error": "corrupted"})
    return {"sessions": results}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session report."""
    from bughunter.core.manifest import ManifestStore
    store = ManifestStore()
    report_path = store.sessions_dir / f"{session_id}_report.md"
    if report_path.exists():
        with open(report_path, "r") as f:
            return {"session_id": session_id, "report": f.read()}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/leaderboard")
async def get_leaderboard():
    """Get global leaderboard."""
    from bughunter.core.skill_profiler import SkillProfiler
    profiler = SkillProfiler()
    p = profiler.profile
    return {
        "leaderboard": [{
            "developer_id": p.developer_id,
            "dss": p.dss,
            "sessions_won": p.sessions_won,
            "win_rate": p.sessions_won / max(p.sessions_total, 1),
        }]
    }


@app.post("/api/llm/config")
async def update_llm_config(config: LLMConfigRequest):
    """Update LLM provider configuration."""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()

    updated = {
        "BUGHUNTER_EXTERNAL_LLM": config.provider,
        "BUGHUNTER_EXTERNAL_MODEL": config.model,
        "BUGHUNTER_EXTERNAL_API_KEY": config.api_key,
    }
    new_lines = []
    seen = set()
    for line in lines:
        for key, val in updated.items():
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={val}\n")
                seen.add(key)
                break
        else:
            new_lines.append(line)
    for key, val in updated.items():
        if key not in seen:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
    return {"status": "updated"}


@app.get("/api/knowledge/status")
async def knowledge_status():
    """Get knowledge brain status."""
    brain_path = Path(__file__).resolve().parent.parent.parent / "SECOND-KNOWLEDGE-BRAIN.md"
    if brain_path.exists():
        return {
            "exists": True,
            "size_kb": round(brain_path.stat().st_size / 1024, 1),
            "atoms": 22,
            "crawl_runs": 0,
        }
    return {"exists": False}


@app.post("/api/knowledge/crawl")
async def trigger_knowledge_crawl():
    """Manually trigger knowledge crawl."""
    from bughunter.core.knowledge_crawler import KnowledgeUpdater
    updater = KnowledgeUpdater()
    results = updater.run_full_crawl()
    return results


@app.post("/api/hunt/start")
async def start_hunt():
    """Start a new bug hunt session via API."""
    from bughunter.core.agent_loop import AgentLoop
    from bughunter.core.config import load_config
    config = load_config()
    agent = AgentLoop(config)
    state = agent.start_hunt()
    return {
        "session_id": state.session_id,
        "phase": state.phase.value,
        "bugs_injected": len(state.mutations),
    }


@app.get("/api/hunt/status")
async def hunt_status():
    """Get current hunt session status."""
    from bughunter.core.agent_loop import AgentLoop
    from bughunter.core.config import load_config
    config = load_config()
    agent = AgentLoop(config)
    state = agent.state
    return {
        "session_id": state.session_id,
        "phase": state.phase.value,
        "bugs_injected": len(state.mutations),
        "hints_used": state.hints_given,
    }


@app.websocket("/ws/session/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    """WebSocket for real-time session updates."""
    await websocket.accept()
    if session_id not in active_ws_clients:
        active_ws_clients[session_id] = []
    active_ws_clients[session_id].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "file_opened":
                event = {"type": "file_event", "file": msg.get("file"), "timestamp": datetime.utcnow().isoformat()}
                for client in active_ws_clients.get(session_id, []):
                    try:
                        await client.send_json(event)
                    except Exception:
                        pass

            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        active_ws_clients.get(session_id, []).remove(websocket)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
