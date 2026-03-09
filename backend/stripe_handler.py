"""
PodPal Stripe integration — checkout sessions, webhooks, subscription status.
All keys loaded from environment — no hardcoded values.
"""

import json
import os
from pathlib import Path

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

# ── Config ───────────────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_BETA = os.getenv("STRIPE_PRICE_BETA", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")

NETWORK_CALENDLY_URL = "https://calendly.com/mic-mannmade"

BASE_DIR = Path(__file__).parent.parent
SUBS_FILE = BASE_DIR / "data" / "subscriptions.json"
SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)

router = APIRouter()


def _stripe_ok() -> bool:
    if not STRIPE_SECRET_KEY:
        return False
    stripe.api_key = STRIPE_SECRET_KEY
    return True


def _load_subs() -> dict:
    if SUBS_FILE.exists():
        try:
            return json.loads(SUBS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_subs(data: dict):
    SUBS_FILE.write_text(json.dumps(data, indent=2))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/checkout")
async def create_checkout(payload: dict):
    """
    Create a Stripe Checkout session for beta or pro.
    Network tier → redirect to Calendly (no Stripe session created).

    Body: { "tier": "beta" | "pro" | "network", "email": "optional" }
    """
    tier = payload.get("tier", "").lower()
    email = payload.get("email", "")
    success_url = payload.get("success_url", "https://podpal.show/?checkout=success")
    cancel_url = payload.get("cancel_url", "https://podpal.show/?checkout=cancel")

    if tier not in ("beta", "pro", "network"):
        raise HTTPException(status_code=400, detail="tier must be beta, pro, or network")

    # Network always goes to Calendly
    if tier == "network":
        return JSONResponse({"redirect_url": NETWORK_CALENDLY_URL, "tier": "network"})

    if not _stripe_ok():
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY in your environment."
        )

    price_id = STRIPE_PRICE_BETA if tier == "beta" else STRIPE_PRICE_PRO

    if not price_id:
        env_var = "STRIPE_PRICE_BETA" if tier == "beta" else "STRIPE_PRICE_PRO"
        raise HTTPException(
            status_code=503,
            detail=f"Stripe price not configured. Set {env_var} in your environment."
        )

    try:
        session_kwargs = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"tier": tier},
        }
        if email:
            session_kwargs["customer_email"] = email

        session = stripe.checkout.Session.create(**session_kwargs)
        return JSONResponse({"redirect_url": session.url, "session_id": session.id, "tier": tier})

    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Handle Stripe webhook events.
    Requires STRIPE_WEBHOOK_SECRET to be set.
    """
    if not _stripe_ok():
        raise HTTPException(status_code=503, detail="Stripe not configured.")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="STRIPE_WEBHOOK_SECRET not set — webhook verification disabled."
        )

    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data_obj = event["data"]["object"]

    subs = _load_subs()

    if event_type == "checkout.session.completed":
        email = data_obj.get("customer_email") or data_obj.get("customer_details", {}).get("email", "")
        tier = data_obj.get("metadata", {}).get("tier", "unknown")
        sub_id = data_obj.get("subscription", "")
        if email:
            subs[email] = {
                "status": "active",
                "tier": tier,
                "subscription_id": sub_id,
                "customer_id": data_obj.get("customer", ""),
            }
            _save_subs(subs)

        # Send welcome email (import lazily to avoid circular)
        try:
            from email_handler import send_welcome_email
            await send_welcome_email(email, tier)
        except Exception as e:
            print(f"Welcome email failed: {e}")

    elif event_type == "customer.subscription.deleted":
        customer_id = data_obj.get("customer", "")
        # Find by customer_id
        for email, info in subs.items():
            if info.get("customer_id") == customer_id:
                info["status"] = "cancelled"
                break
        _save_subs(subs)

    elif event_type == "invoice.payment_failed":
        customer_id = data_obj.get("customer", "")
        customer_email = data_obj.get("customer_email", "")
        for email, info in subs.items():
            if info.get("customer_id") == customer_id or email == customer_email:
                info["status"] = "payment_failed"
                notify_email = email
                break
        else:
            notify_email = customer_email

        _save_subs(subs)

        try:
            from email_handler import send_payment_failed_email
            await send_payment_failed_email(notify_email)
        except Exception as e:
            print(f"Payment failed email error: {e}")

    return JSONResponse({"received": True, "type": event_type})


@router.get("/api/subscription/{email}")
async def get_subscription(email: str):
    """Return subscription status for a given email."""
    subs = _load_subs()
    decoded_email = email.replace("%40", "@")
    if decoded_email in subs:
        info = subs[decoded_email]
        return JSONResponse({
            "email": decoded_email,
            "status": info.get("status", "unknown"),
            "tier": info.get("tier", "unknown"),
        })
    return JSONResponse({"email": decoded_email, "status": "none", "tier": None})
