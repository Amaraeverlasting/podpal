"""
PodPal Magic-Link Authentication
- POST /api/auth/request-link  → send magic link via Resend
- GET  /api/auth/verify        → verify token, set session cookie
- GET  /api/auth/me            → return current user
- POST /api/auth/logout        → clear session cookie
- GET  /api/dashboard          → serve dashboard (auth required)
- GET  /api/admin              → serve admin (admin email required)
- GET  /login                  → serve login.html
- GET  /dashboard              → redirect-aware dashboard serve
- GET  /admin                  → redirect-aware admin serve
"""

import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent
USERS_FILE      = BASE_DIR / "data" / "users.json"
TOKENS_FILE     = BASE_DIR / "data" / "auth_tokens.json"
SESSIONS_FILE   = BASE_DIR / "data" / "sessions_auth.json"
FRONTEND_DIR    = BASE_DIR / "frontend" / "dist"

ADMIN_EMAIL     = os.getenv("ADMIN_EMAIL", "mic@mannmade.co.za")
BASE_URL        = os.getenv("BASE_URL", "https://podpal.show")

TOKEN_TTL       = 15 * 60      # 15 minutes
SESSION_TTL     = 30 * 24 * 3600  # 30 days


# ── Data helpers ──────────────────────────────────────────────────────────────

def _read(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _users() -> dict:    return _read(USERS_FILE)
def _tokens() -> dict:   return _read(TOKENS_FILE)
def _sessions() -> dict: return _read(SESSIONS_FILE)


# ── User helpers ───────────────────────────────────────────────────────────────

def get_or_create_user(email: str, tier: str = "free") -> dict:
    users = _users()
    if email not in users:
        users[email] = {
            "email":               email,
            "tier":                tier,
            "created_at":          datetime.utcnow().isoformat(),
            "last_seen":           datetime.utcnow().isoformat(),
            "sessions":            [],
            "subscription_status": "active" if tier != "free" else "free",
            "trial_seconds_used":  0,
            "trial_started_at":    None,
            "trial_expired":       False,
            "first_login":         True,
        }
        _write(USERS_FILE, users)
    else:
        # Backfill trial fields for existing users
        changed = False
        user = users[email]
        for field, default in [
            ("trial_seconds_used", 0),
            ("trial_started_at", None),
            ("trial_expired", False),
            ("first_login", False),   # existing users have already logged in
        ]:
            if field not in user:
                user[field] = default
                changed = True
        if changed:
            _write(USERS_FILE, users)
    return users[email]


def update_user_last_seen(email: str):
    users = _users()
    if email in users:
        users[email]["last_seen"] = datetime.utcnow().isoformat()
        _write(USERS_FILE, users)


def update_user_tier(email: str, tier: str):
    users = _users()
    user = users.get(email) or {
        "email": email,
        "tier": tier,
        "created_at": datetime.utcnow().isoformat(),
        "sessions": [],
    }
    user["tier"] = tier
    user["subscription_status"] = "active"
    user["last_seen"] = datetime.utcnow().isoformat()
    users[email] = user
    _write(USERS_FILE, users)


def add_session_to_user(email: str, session_id: str):
    users = _users()
    if email in users:
        if session_id not in users[email].get("sessions", []):
            users[email].setdefault("sessions", []).append(session_id)
            _write(USERS_FILE, users)


# ── Session helpers ────────────────────────────────────────────────────────────

def create_session(email: str, tier: str) -> str:
    session_id = secrets.token_urlsafe(32)
    sessions = _sessions()
    sessions[session_id] = {
        "email": email,
        "tier": tier,
        "created": time.time(),
    }
    _write(SESSIONS_FILE, sessions)
    return session_id


def get_current_user(request: Request) -> Optional[dict]:
    """Read session cookie and return user dict or None."""
    session_id = request.cookies.get("podpal_session")
    if not session_id:
        return None
    sessions = _sessions()
    sess = sessions.get(session_id)
    if not sess:
        return None
    if time.time() - sess.get("created", 0) > SESSION_TTL:
        # Expired — clean up
        sessions.pop(session_id, None)
        _write(SESSIONS_FILE, sessions)
        return None
    email = sess.get("email", "")
    users = _users()
    return users.get(email)


def require_tier(minimum: str):
    """
    Returns a callable that checks the user's tier meets the minimum.
    Tier order: free < beta < pro < network
    """
    _order = {"free": 0, "beta": 1, "pro": 2, "network": 3}

    def _check(request: Request) -> Optional[dict]:
        user = get_current_user(request)
        if not user:
            return None
        user_level = _order.get(user.get("tier", "free"), 0)
        required_level = _order.get(minimum, 0)
        if user_level >= required_level:
            return user
        return None

    return _check


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/auth/request-link")
async def request_magic_link(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"error": "Valid email required"}, status_code=400)

    # Ensure user exists
    get_or_create_user(email)

    token = secrets.token_urlsafe(32)
    tokens = _tokens()
    tokens[token] = {
        "email": email,
        "expires": time.time() + TOKEN_TTL,
        "used": False,
    }
    _write(TOKENS_FILE, tokens)

    verify_url = f"{BASE_URL}/api/auth/verify?token={token}"

    # Send magic link email
    try:
        from email_handler import send_magic_link_email
        await send_magic_link_email(email, verify_url)
    except Exception as e:
        print(f"[auth] Email send error: {e}")

    return {"ok": True, "message": "Magic link sent. Check your email."}


@router.get("/api/auth/verify")
async def verify_magic_link(token: str):
    tokens = _tokens()
    entry = tokens.get(token)

    if not entry:
        return HTMLResponse("<h2>Invalid or expired link. Please try again.</h2>", status_code=400)
    if entry.get("used"):
        return HTMLResponse("<h2>This link has already been used. Request a new one.</h2>", status_code=400)
    if time.time() > entry.get("expires", 0):
        return HTMLResponse("<h2>This link has expired. Please request a new one.</h2>", status_code=400)

    email = entry["email"]
    # Mark token used
    tokens[token]["used"] = True
    _write(TOKENS_FILE, tokens)

    # Get user (create if missing)
    user = get_or_create_user(email)
    is_first = user.get("first_login", False)

    # Clear first_login flag
    if is_first:
        users = _users()
        if email in users:
            users[email]["first_login"] = False
            _write(USERS_FILE, users)

    update_user_last_seen(email)

    # Trigger welcome email on first login (async, non-blocking)
    if is_first:
        import asyncio
        try:
            from email_handler import send_welcome_trial_email
            asyncio.create_task(send_welcome_trial_email(email))
        except Exception as e:
            print(f"[auth] Welcome email error: {e}")

    # Create session
    session_id = create_session(email, user.get("tier", "free"))

    # Redirect: first-time users go to /welcome, returning users go to /app
    redirect_url = "/welcome" if is_first else "/app"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="podpal_session",
        value=session_id,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=not os.getenv("DEV_MODE"),  # set secure=False in dev if needed
    )
    return response


@router.get("/api/auth/me")
async def auth_me(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "user": user}


@router.post("/api/auth/logout")
async def auth_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("podpal_session")
    return response


# ── Page routes ───────────────────────────────────────────────────────────────

@router.get("/welcome")
async def serve_welcome(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    welcome_html = FRONTEND_DIR / "welcome.html"
    if welcome_html.exists():
        return HTMLResponse(welcome_html.read_text())
    return RedirectResponse(url="/app", status_code=302)


@router.get("/login")
async def serve_login(request: Request):
    # Already logged in? Go to dashboard
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    login_html = FRONTEND_DIR / "login.html"
    if login_html.exists():
        return HTMLResponse(login_html.read_text())
    return HTMLResponse("<h2>Login page not found</h2>", status_code=404)


@router.get("/dashboard")
async def serve_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    dash_html = FRONTEND_DIR / "dashboard.html"
    if dash_html.exists():
        return HTMLResponse(dash_html.read_text())
    return HTMLResponse("<h2>Dashboard not found</h2>", status_code=404)


@router.get("/admin")
async def serve_admin(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("email", "").lower() != ADMIN_EMAIL.lower():
        return HTMLResponse("<h2>Access denied.</h2>", status_code=403)
    admin_html = FRONTEND_DIR / "admin.html"
    if admin_html.exists():
        return HTMLResponse(admin_html.read_text())
    return HTMLResponse("<h2>Admin page not found</h2>", status_code=404)


# ── Dashboard data API ────────────────────────────────────────────────────────

@router.get("/api/dashboard")
async def dashboard_data(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    email = user["email"]
    update_user_last_seen(email)

    # Load their sessions from disk
    sessions_dir = BASE_DIR / "data" / "sessions"
    user_sessions = []
    if sessions_dir.exists():
        for f in sorted(sessions_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                owner = data.get("user_email", "")
                if owner == email:
                    meta = data.get("metadata", {})
                    user_sessions.append({
                        "file": f.name,
                        "session_id": data.get("session_id", ""),
                        "date": meta.get("date", ""),
                        "guest": meta.get("guest", ""),
                        "show": meta.get("show", ""),
                        "duration_seconds": data.get("duration_seconds", 0),
                        "topics_count": len(data.get("topics_detected", [])),
                        "transcript_snippets": data.get("transcript_snippets", []),
                        "show_notes": data.get("show_notes", ""),
                        "social_posts": data.get("social_posts", []),
                    })
            except Exception:
                pass

    total_duration = sum(s.get("duration_seconds", 0) for s in user_sessions)
    return {
        "user": user,
        "sessions": user_sessions,
        "stats": {
            "total_sessions": len(user_sessions),
            "total_recording_seconds": total_duration,
            "posts_generated": sum(len(s.get("social_posts", [])) for s in user_sessions),
        }
    }


@router.get("/api/admin/stats")
async def admin_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    if user.get("email", "").lower() != ADMIN_EMAIL.lower():
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    try:
        from analytics import get_stats
        return get_stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
