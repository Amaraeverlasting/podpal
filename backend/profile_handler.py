"""
PodPal Profile Handler
Routes: GET/POST /api/profile, POST /api/profile/update
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

BASE_DIR   = Path(__file__).parent.parent
USERS_FILE = BASE_DIR / "data" / "users.json"


def _read_users() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _write_users(data: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(data, indent=2))


def _get_user(request: Request):
    """Reuse auth_handler.get_current_user without circular import."""
    try:
        from auth_handler import get_current_user
        return get_current_user(request)
    except Exception:
        return None


# ── API routes ────────────────────────────────────────────────────────────────

@router.get("/api/profile")
async def get_profile(request: Request):
    user = _get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    users = _read_users()
    email = user.get("email", "")
    data  = users.get(email, user)

    return {
        "email":            email,
        "name":             data.get("name", ""),
        "show_name":        data.get("show_name", ""),
        "episode_frequency": data.get("episode_frequency", ""),
        "show_description": data.get("show_description", ""),
        "tier":             data.get("tier", "free"),
        "profile_completed": data.get("profile_completed", False),
        "profile_shown":    data.get("profile_shown", False),
        "created_at":       data.get("created_at", ""),
        "total_sessions":   len(data.get("sessions", [])),
    }


@router.post("/api/profile/update")
async def update_profile(payload: dict, request: Request):
    user = _get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    email = user.get("email", "")
    users = _read_users()

    if email not in users:
        return JSONResponse({"error": "User not found"}, status_code=404)

    allowed = ["name", "show_name", "episode_frequency", "show_description"]
    for field in allowed:
        val = payload.get(field)
        if val is not None:
            users[email][field] = str(val).strip()

    if any(payload.get(f) for f in ["name", "show_name"]):
        users[email]["profile_completed"] = True

    users[email]["profile_shown"]  = True
    users[email]["profile_updated_at"] = datetime.utcnow().isoformat()

    _write_users(users)
    return {"ok": True, "email": email}


@router.get("/api/profile/stats")
async def profile_stats(request: Request):
    """Return session stats for the profile page."""
    user = _get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    email      = user.get("email", "")
    sessions_dir = BASE_DIR / "data" / "sessions"
    total_sessions   = 0
    total_seconds    = 0
    show_notes_count = 0

    if sessions_dir.exists():
        for f in sessions_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("user_email") == email:
                    total_sessions   += 1
                    total_seconds    += data.get("duration_seconds", 0)
                    if data.get("show_notes") or data.get("transcript_snippets"):
                        show_notes_count += 1
            except Exception:
                pass

    minutes = total_seconds // 60
    return {
        "total_sessions":    total_sessions,
        "total_minutes":     minutes,
        "show_notes_generated": show_notes_count,
    }
