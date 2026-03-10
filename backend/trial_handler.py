"""
PodPal Trial Handler
Manages the 10-minute free trial, trial codes, and comp access.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
USERS_FILE       = BASE_DIR / "data" / "users.json"
TRIAL_CODES_FILE = BASE_DIR / "data" / "trial_codes.json"

TRIAL_LIMIT_SECONDS = 600  # 10 minutes


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
    """Add trial fields to a user dict if they're missing."""
    user.setdefault("trial_seconds_used", 0)
    user.setdefault("trial_started_at", None)
    user.setdefault("trial_expired", False)
    user.setdefault("first_login", True)
    return user


# ── Comp expiry check ─────────────────────────────────────────────────────────

def check_comp_expiry(email: str, users: dict) -> dict:
    """
    If a user has a comp_expires date in the past, revert them to free.
    Modifies the users dict in-place; caller must save.
    """
    user = users.get(email, {})
    comp_expires = user.get("comp_expires")
    tier = user.get("tier", "free")
    if comp_expires and tier != "free":
        try:
            exp_dt = datetime.fromisoformat(comp_expires)
            if datetime.utcnow() > exp_dt:
                users[email]["tier"] = "free"
                users[email]["subscription_status"] = "free"
        except Exception:
            pass
    return users


# ── Trial status ──────────────────────────────────────────────────────────────

def get_trial_status(email: str) -> dict:
    """Return trial status for a user.

    Returns:
        {tier, seconds_used, seconds_remaining, expired, percent_used, trial_limit}
    """
    users = _read_users()
    users = check_comp_expiry(email, users)
    user = users.get(email, {})
    _ensure_trial_fields(user)

    tier            = user.get("tier", "free")
    seconds_used    = user.get("trial_seconds_used", 0)
    expired         = user.get("trial_expired", False)
    seconds_remaining = max(0, TRIAL_LIMIT_SECONDS - seconds_used)
    percent_used    = min(100.0, round((seconds_used / TRIAL_LIMIT_SECONDS) * 100, 2))

    # Hard-expire if time is up and still free tier
    if tier == "free" and seconds_remaining == 0:
        expired = True

    return {
        "tier": tier,
        "seconds_used": seconds_used,
        "seconds_remaining": seconds_remaining,
        "expired": expired,
        "percent_used": percent_used,
        "trial_limit": TRIAL_LIMIT_SECONDS,
    }


def add_trial_time(email: str, seconds: int) -> dict:
    """Add recording seconds to a user's trial counter.

    Non-free-tier users skip the counter.
    Returns updated trial status.
    """
    users = _read_users()
    users = check_comp_expiry(email, users)

    if email not in users:
        return get_trial_status(email)

    user = users[email]
    _ensure_trial_fields(user)

    tier = user.get("tier", "free")
    if tier != "free":
        return get_trial_status(email)

    if user.get("trial_expired", False):
        return get_trial_status(email)

    # Mark start time on first tick
    if not user.get("trial_started_at"):
        user["trial_started_at"] = datetime.utcnow().isoformat()

    user["trial_seconds_used"] = min(
        TRIAL_LIMIT_SECONDS,
        user.get("trial_seconds_used", 0) + seconds
    )

    if user["trial_seconds_used"] >= TRIAL_LIMIT_SECONDS:
        user["trial_expired"] = True

    users[email] = user
    _write_users(users)
    return get_trial_status(email)


def expire_trial(email: str) -> dict:
    """Force-expire a user's trial."""
    users = _read_users()
    if email in users:
        _ensure_trial_fields(users[email])
        users[email]["trial_expired"] = True
        _write_users(users)
    return get_trial_status(email)


def is_trial_expired(email: str) -> bool:
    """Quick check: is the trial expired?"""
    return get_trial_status(email)["expired"]


# ── Trial codes ───────────────────────────────────────────────────────────────

def create_trial_code(code: str, tier: str = "pro", days: int = 7) -> dict:
    """Create a new trial code. Returns the code entry."""
    data = _read_trial_codes()
    code = code.upper().strip()
    if code not in data.get("codes", {}):
        data.setdefault("codes", {})[code] = {
            "used":       False,
            "used_by":    None,
            "used_at":    None,
            "created_at": datetime.utcnow().isoformat(),
            "tier":       tier,
            "days":       days,
        }
        _write_trial_codes(data)
    return data["codes"][code]


def list_trial_codes() -> list:
    """List all trial codes with usage info."""
    data = _read_trial_codes()
    result = []
    for code, entry in data.get("codes", {}).items():
        result.append({"code": code, **entry})
    return result


def redeem_trial_code(code: str, email: str) -> dict:
    """Redeem a trial code for an email address.

    Returns: {ok: bool, tier, days, expires} or {ok: False, error: str}
    """
    data = _read_trial_codes()
    code = code.upper().strip()
    entry = data.get("codes", {}).get(code)

    if not entry:
        return {"ok": False, "error": "Invalid code"}
    if entry.get("used"):
        return {"ok": False, "error": "Code already used"}

    tier    = entry.get("tier", "pro")
    days    = entry.get("days", 7)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()

    # Update user
    users = _read_users()
    if email not in users:
        users[email] = {
            "email":               email,
            "tier":                tier,
            "created_at":          datetime.utcnow().isoformat(),
            "last_seen":           datetime.utcnow().isoformat(),
            "sessions":            [],
            "subscription_status": "comp",
        }

    _ensure_trial_fields(users[email])
    users[email]["tier"]                   = tier
    users[email]["subscription_status"]    = "comp"
    users[email]["comp_expires"]           = expires
    users[email]["trial_override_expires"] = expires
    _write_users(users)

    # Mark code used
    data["codes"][code]["used"]    = True
    data["codes"][code]["used_by"] = email
    data["codes"][code]["used_at"] = datetime.utcnow().isoformat()
    _write_trial_codes(data)

    return {"ok": True, "tier": tier, "days": days, "expires": expires}


# ── Comp access (admin) ───────────────────────────────────────────────────────

def grant_comp_access(email: str, tier: str, days: int) -> dict:
    """Grant complimentary access to any user (admin action)."""
    users = _read_users()
    if email not in users:
        users[email] = {
            "email":               email,
            "tier":                tier,
            "created_at":          datetime.utcnow().isoformat(),
            "last_seen":           datetime.utcnow().isoformat(),
            "sessions":            [],
            "subscription_status": "comp",
        }

    _ensure_trial_fields(users[email])
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    users[email]["tier"]                = tier
    users[email]["subscription_status"] = "comp"
    users[email]["comp_expires"]        = expires
    _write_users(users)

    return {
        "ok":      True,
        "email":   email,
        "tier":    tier,
        "days":    days,
        "expires": expires,
    }
