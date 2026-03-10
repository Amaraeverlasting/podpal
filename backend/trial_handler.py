"""
PodPal Trial Handler
7-day / 3-session / 60-minute free trial (whichever hits first).
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR         = Path(__file__).parent.parent
USERS_FILE       = BASE_DIR / "data" / "users.json"
TRIAL_CODES_FILE = BASE_DIR / "data" / "trial_codes.json"

TRIAL_DAYS          = 7
TRIAL_SESSION_LIMIT = 3
TRIAL_MINUTE_LIMIT  = 3600   # 60 minutes in seconds
TRIAL_LIMIT_SECONDS = TRIAL_MINUTE_LIMIT  # backward-compat alias


# ── File helpers ──────────────────────────────────────────────────────────────

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


def _read_trial_codes() -> dict:
    if TRIAL_CODES_FILE.exists():
        try:
            return json.loads(TRIAL_CODES_FILE.read_text())
        except Exception:
            return {"codes": {}}
    return {"codes": {}}


def _write_trial_codes(data: dict):
    TRIAL_CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRIAL_CODES_FILE.write_text(json.dumps(data, indent=2))


def _ensure_trial_fields(user: dict) -> dict:
    user.setdefault("trial_seconds_used", 0)
    user.setdefault("trial_sessions_used", 0)
    user.setdefault("trial_started_at", None)
    user.setdefault("trial_expires_at", None)
    user.setdefault("trial_expired", False)
    user.setdefault("trial_expired_reason", None)
    user.setdefault("first_login", True)
    return user


# ── Comp expiry ───────────────────────────────────────────────────────────────

def check_comp_expiry(email: str, users: dict) -> dict:
    user = users.get(email, {})
    comp_expires = user.get("comp_expires")
    tier = user.get("tier", "free")
    if comp_expires and tier != "free":
        try:
            if datetime.utcnow() > datetime.fromisoformat(comp_expires):
                users[email]["tier"] = "free"
                users[email]["subscription_status"] = "free"
        except Exception:
            pass
    return users


# ── Trial status ──────────────────────────────────────────────────────────────

def get_trial_status(email: str) -> dict:
    users = _read_users()
    users = check_comp_expiry(email, users)
    user = users.get(email, {})
    _ensure_trial_fields(user)

    tier          = user.get("tier", "free")
    seconds_used  = user.get("trial_seconds_used", 0)
    sessions_used = user.get("trial_sessions_used", 0)
    expired       = user.get("trial_expired", False)
    reason        = user.get("trial_expired_reason", None)

    days_remaining = TRIAL_DAYS
    trial_started_at = user.get("trial_started_at")
    trial_expires_at = user.get("trial_expires_at")

    if trial_started_at:
        try:
            started = datetime.fromisoformat(trial_started_at)
            expires = (
                datetime.fromisoformat(trial_expires_at)
                if trial_expires_at
                else started + timedelta(days=TRIAL_DAYS)
            )
            days_remaining = max(0, (expires - datetime.utcnow()).days)
        except Exception:
            pass

    seconds_remaining  = max(0, TRIAL_MINUTE_LIMIT - seconds_used)
    sessions_remaining = max(0, TRIAL_SESSION_LIMIT - sessions_used)

    # Auto-expire for free tier
    if tier == "free" and not expired:
        if seconds_remaining == 0:
            expired, reason = True, "minutes"
        elif sessions_used >= TRIAL_SESSION_LIMIT:
            expired, reason = True, "sessions"
        elif days_remaining == 0 and trial_started_at:
            expired, reason = True, "time"

    pct_seconds  = (seconds_used / TRIAL_MINUTE_LIMIT) * 100
    pct_sessions = (sessions_used / TRIAL_SESSION_LIMIT) * 100
    days_used    = TRIAL_DAYS - days_remaining
    pct_days     = (days_used / TRIAL_DAYS) * 100
    percent_used = min(100.0, round(max(pct_seconds, pct_sessions, pct_days), 2))

    return {
        "tier": tier,
        "seconds_used": seconds_used,
        "seconds_remaining": seconds_remaining,
        "sessions_used": sessions_used,
        "sessions_remaining": sessions_remaining,
        "days_remaining": days_remaining,
        "expired": expired,
        "percent_used": percent_used,
        "reason": reason,
        "trial_limit": TRIAL_MINUTE_LIMIT,
    }


def increment_trial_sessions(email: str) -> dict:
    """Call when a free-tier user starts a new session."""
    users = _read_users()
    if email not in users:
        return get_trial_status(email)
    user = users[email]
    _ensure_trial_fields(user)
    if user.get("tier", "free") != "free":
        return get_trial_status(email)
    if user.get("trial_expired"):
        return get_trial_status(email)

    if not user.get("trial_started_at"):
        now = datetime.utcnow()
        user["trial_started_at"] = now.isoformat()
        user["trial_expires_at"] = (now + timedelta(days=TRIAL_DAYS)).isoformat()

    user["trial_sessions_used"] = user.get("trial_sessions_used", 0) + 1
    if user["trial_sessions_used"] >= TRIAL_SESSION_LIMIT:
        user["trial_expired"]        = True
        user["trial_expired_reason"] = "sessions"

    users[email] = user
    _write_users(users)
    return get_trial_status(email)


def add_trial_time(email: str, seconds: int) -> dict:
    users = _read_users()
    users = check_comp_expiry(email, users)
    if email not in users:
        return get_trial_status(email)
    user = users[email]
    _ensure_trial_fields(user)

    if user.get("tier", "free") != "free" or user.get("trial_expired"):
        return get_trial_status(email)

    if not user.get("trial_started_at"):
        now = datetime.utcnow()
        user["trial_started_at"] = now.isoformat()
        user["trial_expires_at"] = (now + timedelta(days=TRIAL_DAYS)).isoformat()

    user["trial_seconds_used"] = min(
        TRIAL_MINUTE_LIMIT,
        user.get("trial_seconds_used", 0) + seconds
    )
    if user["trial_seconds_used"] >= TRIAL_MINUTE_LIMIT:
        user["trial_expired"]        = True
        user["trial_expired_reason"] = "minutes"

    users[email] = user
    _write_users(users)
    return get_trial_status(email)


def expire_trial(email: str, reason: str = None) -> dict:
    users = _read_users()
    if email in users:
        _ensure_trial_fields(users[email])
        users[email]["trial_expired"] = True
        if reason:
            users[email]["trial_expired_reason"] = reason
        _write_users(users)
    return get_trial_status(email)


def is_trial_expired(email: str) -> bool:
    return get_trial_status(email)["expired"]


# ── Trial codes ───────────────────────────────────────────────────────────────

def create_trial_code(code: str, tier: str = "pro", days: int = 7) -> dict:
    data = _read_trial_codes()
    code = code.upper().strip()
    if code not in data.get("codes", {}):
        data.setdefault("codes", {})[code] = {
            "used": False, "used_by": None, "used_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "tier": tier, "days": days,
        }
        _write_trial_codes(data)
    return data["codes"][code]


def list_trial_codes() -> list:
    data = _read_trial_codes()
    return [{"code": c, **e} for c, e in data.get("codes", {}).items()]


def redeem_trial_code(code: str, email: str) -> dict:
    data  = _read_trial_codes()
    code  = code.upper().strip()
    entry = data.get("codes", {}).get(code)
    if not entry:
        return {"ok": False, "error": "Invalid code"}
    if entry.get("used"):
        return {"ok": False, "error": "Code already used"}

    tier    = entry.get("tier", "pro")
    days    = entry.get("days", 7)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()

    users = _read_users()
    if email not in users:
        users[email] = {
            "email": email, "tier": tier,
            "created_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
            "sessions": [], "subscription_status": "comp",
        }
    _ensure_trial_fields(users[email])
    users[email]["tier"]                   = tier
    users[email]["subscription_status"]    = "comp"
    users[email]["comp_expires"]           = expires
    users[email]["trial_override_expires"] = expires
    _write_users(users)

    data["codes"][code].update({"used": True, "used_by": email, "used_at": datetime.utcnow().isoformat()})
    _write_trial_codes(data)
    return {"ok": True, "tier": tier, "days": days, "expires": expires}


def grant_comp_access(email: str, tier: str, days: int) -> dict:
    users = _read_users()
    if email not in users:
        users[email] = {
            "email": email, "tier": tier,
            "created_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
            "sessions": [], "subscription_status": "comp",
        }
    _ensure_trial_fields(users[email])
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    users[email]["tier"]                = tier
    users[email]["subscription_status"] = "comp"
    users[email]["comp_expires"]        = expires
    _write_users(users)
    return {"ok": True, "email": email, "tier": tier, "days": days, "expires": expires}
