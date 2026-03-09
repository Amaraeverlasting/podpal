"""
PodPal Analytics — event tracking to data/analytics.json
All writes are append-only. No external services needed.
"""

import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ANALYTICS_FILE = BASE_DIR / "data" / "analytics.json"


def _load() -> list:
    if ANALYTICS_FILE.exists():
        try:
            return json.loads(ANALYTICS_FILE.read_text())
        except Exception:
            return []
    return []


def _save(events: list):
    ANALYTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANALYTICS_FILE.write_text(json.dumps(events, indent=2))


def track(event_type: str, data: dict):
    """Append one analytics event. Fire-and-forget — never raises."""
    try:
        events = _load()
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        }
        events.append(event)
        # Keep last 10 000 events to avoid unbounded growth
        if len(events) > 10_000:
            events = events[-10_000:]
        _save(events)
    except Exception as e:
        print(f"[analytics] track error: {e}")


# ── Named helpers ─────────────────────────────────────────────────────────────

def user_signup(email: str, tier: str):
    track("user_signup", {"email": email, "tier": tier})


def session_started(user_email: str | None, session_id: str):
    track("session_started", {"user_email": user_email or "", "session_id": session_id})


def session_completed(user_email: str | None, session_id: str, duration_seconds: int, word_count: int):
    track("session_completed", {
        "user_email": user_email or "",
        "session_id": session_id,
        "duration_seconds": duration_seconds,
        "word_count": word_count,
    })


def feature_used(user_email: str | None, feature_name: str):
    track("feature_used", {"user_email": user_email or "", "feature_name": feature_name})


def payment_completed(email: str, tier: str, amount: str):
    track("payment_completed", {"email": email, "tier": tier, "amount": amount})


def page_view(path: str, user_email: str | None = None):
    track("page_view", {"path": path, "user_email": user_email or ""})


# ── Stats builder for admin dashboard ────────────────────────────────────────

def get_stats() -> dict:
    """Return aggregated analytics for the admin dashboard."""
    from datetime import timezone, timedelta
    events = _load()
    now = datetime.utcnow()

    def ts(e) -> datetime:
        try:
            return datetime.fromisoformat(e["timestamp"])
        except Exception:
            return datetime.min

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    signups = [e for e in events if e["type"] == "user_signup"]
    payments = [e for e in events if e["type"] == "payment_completed"]
    sessions_ev = [e for e in events if e["type"] == "session_started"]
    features = [e for e in events if e["type"] == "feature_used"]
    views = [e for e in events if e["type"] == "page_view"]

    # MRR estimate
    tier_prices = {"beta": 19, "pro": 79, "network": 299}
    # Use latest user tier per email from users.json
    users_file = BASE_DIR / "data" / "users.json"
    users = {}
    if users_file.exists():
        try:
            users = json.loads(users_file.read_text())
        except Exception:
            pass
    active_subs = {e: u for e, u in users.items() if u.get("subscription_status") == "active"}
    mrr = sum(tier_prices.get(u.get("tier", ""), 0) for u in active_subs.values())

    # Sessions counts
    def count_since(evts, since):
        return sum(1 for e in evts if ts(e) >= since)

    # Feature usage breakdown
    feature_counts: dict[str, int] = {}
    for e in features:
        fn = e.get("feature_name", "unknown")
        feature_counts[fn] = feature_counts.get(fn, 0) + 1

    # Conversion funnel
    unique_visitors = len({e.get("user_email", "anon_" + e.get("timestamp", "")) for e in views})
    unique_signups = len({e.get("email", "") for e in signups})
    paid_emails = {e.get("email", "") for e in payments}
    paid_count = len(paid_emails)

    return {
        "users": {
            "total": len(users),
            "active_subscribers": len(active_subs),
            "mrr_usd": mrr,
            "recent_signups": sorted(signups, key=lambda e: e.get("timestamp", ""), reverse=True)[:10],
        },
        "sessions": {
            "today": count_since(sessions_ev, today_start),
            "this_week": count_since(sessions_ev, week_start),
            "this_month": count_since(sessions_ev, month_start),
            "total": len(sessions_ev),
        },
        "features": feature_counts,
        "payments": {
            "total": len(payments),
            "recent": sorted(payments, key=lambda e: e.get("timestamp", ""), reverse=True)[:10],
        },
        "funnel": {
            "visitors": unique_visitors,
            "signups": unique_signups,
            "paid": paid_count,
        },
    }
