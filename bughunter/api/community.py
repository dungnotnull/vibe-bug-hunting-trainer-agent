"""Public REST API — community bug pattern library and instructor API.

Phase 4.2:
- Custom bug pattern submission (community contributions)
- Bug pattern review workflow (human + ML moderation)
- Community bug pattern library (opt-in sharing)
- Instructor API: custom curriculum for bootcamps
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

community_app = FastAPI(
    title="BugHunterAgent Community API",
    description="Public API for bug pattern contributions and curriculum management",
    version="0.1.0",
)

community_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PATTERNS_DIR = Path.home() / ".bughunter" / "community_patterns"
PATTERNS_DIR.mkdir(parents=True, exist_ok=True)


class PatternCategory(str, Enum):
    BOUNDARY = "boundary"
    TYPE_COERCION = "type_coercion"
    ASYNC_CONCURRENCY = "async_concurrency"
    STATE_MUTATION = "state_mutation"
    SECURITY = "security"
    LOGIC_ALGORITHM = "logic_algorithm"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class BugPatternSubmission(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20, max_length=5000)
    category: PatternCategory
    language: str = Field(..., pattern="^(python|javascript|typescript|go|rust|java|ruby)$")
    difficulty: int = Field(..., ge=1, le=5)
    code_before: str = Field(default="", max_length=5000)
    code_after: str = Field(default="", max_length=5000)
    teaching_points: str = Field(default="", max_length=2000)
    references: str = Field(default="", max_length=1000)
    contributor_name: str = Field(default="anonymous", max_length=100)
    tags: list[str] = Field(default_factory=list)


class BugPatternResponse(BaseModel):
    id: str
    title: str
    category: str
    language: str
    difficulty: int
    status: ReviewStatus
    submitted_at: str
    approved_at: Optional[str] = None
    contributor: str
    downloads: int = 0
    rating: float = 0.0


class CurriculumRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    pattern_ids: list[str] = Field(default_factory=list)
    target_bcts: list[int] = Field(default=[1, 2])
    estimated_sessions: int = Field(default=10, ge=1, le=100)
    instructor_email: str = Field(default="", max_length=200)


class CurriculumResponse(BaseModel):
    id: str
    name: str
    pattern_count: int
    estimated_sessions: int
    created_at: str


class PatternReviewRequest(BaseModel):
    status: ReviewStatus
    reviewer_notes: str = Field(default="", max_length=2000)


class RatingRequest(BaseModel):
    rating: float = Field(..., ge=0.0, le=5.0)


@community_app.get("/")
async def root():
    return {"service": "BugHunterAgent Community API", "version": "0.1.0"}


@community_app.get("/api/v1/patterns")
async def list_patterns(
    category: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    status: str = Query("approved"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List community bug patterns with filtering."""
    patterns = []
    for fpath in PATTERNS_DIR.glob("*.json"):
        try:
            with open(fpath, "r") as f:
                p = json.load(f)
            if p.get("status") != status and status != "all":
                continue
            if category and p.get("category") != category:
                continue
            if language and p.get("language") != language:
                continue
            if difficulty and p.get("difficulty") != difficulty:
                continue
            patterns.append(p)
        except Exception:
            continue

    patterns.sort(key=lambda p: p.get("submitted_at", ""), reverse=True)
    return {
        "total": len(patterns),
        "offset": offset,
        "limit": limit,
        "patterns": patterns[offset : offset + limit],
    }


@community_app.get("/api/v1/patterns/{pattern_id}", response_model=BugPatternResponse)
async def get_pattern(pattern_id: str):
    """Get a specific bug pattern by ID."""
    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Pattern not found")
    with open(fpath, "r") as f:
        data = json.load(f)
    return BugPatternResponse(**data)


@community_app.post("/api/v1/patterns", status_code=201)
async def submit_pattern(submission: BugPatternSubmission):
    """Submit a new bug pattern to the community library."""
    pattern_id = f"COMM-{uuid.uuid4().hex[:12]}"
    data = {
        "id": pattern_id,
        "title": submission.title,
        "description": submission.description,
        "category": submission.category.value,
        "language": submission.language,
        "difficulty": submission.difficulty,
        "code_before": submission.code_before,
        "code_after": submission.code_after,
        "teaching_points": submission.teaching_points,
        "references": submission.references,
        "contributor": submission.contributor_name,
        "tags": submission.tags,
        "status": ReviewStatus.PENDING.value,
        "submitted_at": datetime.utcnow().isoformat(),
        "approved_at": None,
        "downloads": 0,
        "rating": 0.0,
        "reviews": [],
    }

    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)

    return {
        "id": pattern_id,
        "status": "pending",
        "message": "Pattern submitted for review. Thank you for your contribution!",
    }


@community_app.put("/api/v1/patterns/{pattern_id}/review")
async def review_pattern(pattern_id: str, review: PatternReviewRequest):
    """Review and approve/reject a submitted pattern."""
    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Pattern not found")

    with open(fpath, "r") as f:
        data = json.load(f)

    data["status"] = review.status.value
    if review.status == ReviewStatus.APPROVED:
        data["approved_at"] = datetime.utcnow().isoformat()
    data.setdefault("reviews", []).append({
        "status": review.status.value,
        "notes": review.reviewer_notes,
        "reviewed_at": datetime.utcnow().isoformat(),
    })

    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)

    return {"id": pattern_id, "status": review.status.value}


@community_app.post("/api/v1/patterns/{pattern_id}/rate")
async def rate_pattern(pattern_id: str, rating: RatingRequest):
    """Rate a community pattern."""
    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Pattern not found")

    with open(fpath, "r") as f:
        data = json.load(f)

    current_rating = data.get("rating", 0.0)
    rating_count = data.get("rating_count", 0)
    new_count = rating_count + 1
    new_rating = (current_rating * rating_count + rating.rating) / new_count
    data["rating"] = round(new_rating, 2)
    data["rating_count"] = new_count

    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)

    return {"id": pattern_id, "rating": new_rating}


@community_app.post("/api/v1/patterns/{pattern_id}/download")
async def download_pattern(pattern_id: str):
    """Track pattern download count."""
    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Pattern not found")

    with open(fpath, "r") as f:
        data = json.load(f)

    data["downloads"] = data.get("downloads", 0) + 1
    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)

    return {
        "id": pattern_id,
        "title": data.get("title"),
        "category": data.get("category"),
        "language": data.get("language"),
        "code_before": data.get("code_before", ""),
        "code_after": data.get("code_after", ""),
        "teaching_points": data.get("teaching_points", ""),
    }


@community_app.get("/api/v1/patterns/{pattern_id}/export")
async def export_pattern(pattern_id: str):
    """Export a pattern in a format ready for injection."""
    fpath = PATTERNS_DIR / f"{pattern_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Pattern not found")

    with open(fpath, "r") as f:
        data = json.load(f)

    return {
        "version": "1.0",
        "pattern": {
            "id": data["id"],
            "category": data["category"],
            "language": data["language"],
            "difficulty": f"BCT-{data['difficulty']}",
            "injection": {
                "before": data.get("code_before", ""),
                "after": data.get("code_after", ""),
            },
            "metadata": {
                "title": data["title"],
                "teaching_points": data.get("teaching_points", ""),
            },
        },
    }


@community_app.post("/api/v1/curriculum", status_code=201)
async def create_curriculum(request: CurriculumRequest):
    """Create a custom training curriculum for bootcamps/instructors."""
    curriculum_id = f"CURR-{uuid.uuid4().hex[:8]}"
    data = {
        "id": curriculum_id,
        "name": request.name,
        "description": request.description,
        "pattern_ids": request.pattern_ids,
        "target_bcts": request.target_bcts,
        "estimated_sessions": request.estimated_sessions,
        "instructor_email": request.instructor_email,
        "created_at": datetime.utcnow().isoformat(),
        "sessions_completed": 0,
        "active": True,
    }

    curriculum_dir = PATTERNS_DIR / "curricula"
    curriculum_dir.mkdir(exist_ok=True)
    with open(curriculum_dir / f"{curriculum_id}.json", "w") as f:
        json.dump(data, f, indent=2)

    return {
        "id": curriculum_id,
        "name": request.name,
        "pattern_count": len(request.pattern_ids),
        "estimated_sessions": request.estimated_sessions,
        "created_at": data["created_at"],
    }


@community_app.get("/api/v1/curriculum/{curriculum_id}")
async def get_curriculum(curriculum_id: str):
    """Get curriculum details including progress."""
    fpath = PATTERNS_DIR / "curricula" / f"{curriculum_id}.json"
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Curriculum not found")

    with open(fpath, "r") as f:
        data = json.load(f)

    patterns = []
    for pid in data.get("pattern_ids", []):
        pfpath = PATTERNS_DIR / f"{pid}.json"
        if pfpath.exists():
            with open(pfpath, "r") as f:
                patterns.append(json.load(f))

    data["patterns"] = patterns
    return data


@community_app.get("/api/v1/curriculum")
async def list_curricula():
    """List all curricula."""
    curriculum_dir = PATTERNS_DIR / "curricula"
    curricula = []
    if curriculum_dir.exists():
        for fpath in curriculum_dir.glob("*.json"):
            with open(fpath, "r") as f:
                data = json.load(f)
            curricula.append({
                "id": data["id"],
                "name": data["name"],
                "pattern_count": len(data.get("pattern_ids", [])),
                "created_at": data.get("created_at"),
            })
    return {"curricula": curricula}


@community_app.get("/api/v1/stats")
async def community_stats():
    """Get community-wide statistics."""
    total_patterns = len(list(PATTERNS_DIR.glob("*.json")))
    pending = 0
    approved = 0
    for fpath in PATTERNS_DIR.glob("*.json"):
        with open(fpath, "r") as f:
            data = json.load(f)
        if data.get("status") == "approved":
            approved += 1
        elif data.get("status") == "pending":
            pending += 1

    return {
        "total_patterns": total_patterns,
        "approved_patterns": approved,
        "pending_review": pending,
        "contributors": total_patterns,
        "updated_at": datetime.utcnow().isoformat(),
    }


def run_community_server(host: str = "0.0.0.0", port: int = 8001):
    import uvicorn
    uvicorn.run(community_app, host=host, port=port, log_level="info")
