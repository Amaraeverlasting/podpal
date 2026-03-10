"""
PayFast payment integration for PodPal.
Handles checkout initiation, ITN webhook validation, and subscription tracking.
"""
import os
import json
import hashlib
import urllib.parse
import uuid
import requests
from datetime import datetime, date
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent
SUBS_FILE = BASE_DIR / "data" / "subscriptions.json"

MERCHANT_ID   = os.getenv("PAYFAST_MERCHANT_ID", "")
MERCHANT_KEY  = os.getenv("PAYFAST_MERCHANT_KEY", "")
PASSPHRASE    = os.getenv("PAYFAST_PASSPHRASE", "")
SANDBOX       = os.getenv("PAYFAST_SANDBOX", "false").lower() == "true"

PAYFAST_URL   = "https://sandbox.payfast.co.za/eng/process" if SANDBOX else "https://www.payfast.co.za/eng/process"
BASE_URL      = os.getenv("BASE_URL", "https://podpal.show")

PRICES = {
    "beta": {"amount": "349.00", "name": "PodPal Beta - $19/month"},
    "pro":  {"amount": "1449.00", "name": "PodPal Pro - $79/month"},
}


def _load_subs() -> dict:
    if SUBS_FILE.exists():
        return json.loads(SUBS_FILE.read_text())
    return {}


def _save_subs(data: dict):
    SUBS_FILE.parent.mkdir(exist_ok=True)
    SUBS_FILE.write_text(json.dumps(data, indent=2))


def _generate_signature(params: dict) -> str:
    """MD5 signature per PayFast spec - no sorting, no empty values, passphrase appended."""
    pairs = []
    for k, v in params.items():
        if v != "" and k != "signature":
            # PayFast uses quote_plus encoding (spaces → +)
            pairs.append(f"{k}={urllib.parse.quote_plus(str(v))}")
    query = "&".join(pairs)
    if PASSPHRASE:
        query += f"&passphrase={urllib.parse.quote_plus(PASSPHRASE)}"
    return hashlib.md5(query.encode("utf-8")).hexdigest()


class CheckoutRequest(BaseModel):
    tier: str
    email: str = ""
    name: str = ""


@router.post("/api/checkout")
async def create_checkout(req: CheckoutRequest):
    if req.tier == "network":
        return {"redirect": "https://calendly.com/mic-mannmade"}

    if req.tier not in PRICES:
        raise HTTPException(status_code=400, detail="Invalid tier")

    if not MERCHANT_ID or not MERCHANT_KEY:
        raise HTTPException(status_code=500, detail="PayFast not configured")

    price = PRICES[req.tier]
    payment_id = str(uuid.uuid4())[:8].upper()
    name_parts = (req.name or "PodPal User").split(" ", 1)

    params = {
        "merchant_id":       MERCHANT_ID,
        "merchant_key":      MERCHANT_KEY,
        "return_url":        f"{BASE_URL}/app?payment=success",
        "cancel_url":        f"{BASE_URL}/?payment=cancelled",
        "notify_url":        f"{BASE_URL}/api/webhook/payfast",
        "name_first":        name_parts[0],
        "name_last":         name_parts[1] if len(name_parts) > 1 else "",
        "email_address":     req.email or "",
        "m_payment_id":      payment_id,
        "amount":            price["amount"],
        "item_name":         price["name"],
        "subscription_type": "1",
        "billing_date":      date.today().strftime("%Y-%m-%d"),
        "recurring_amount":  price["amount"],
        "frequency":         "3",
        "cycles":            "0",
    }

    params["signature"] = _generate_signature(params)

    # Build auto-submitting HTML form (PayFast recommended approach)
    fields = "\n".join(
        f'<input type="hidden" name="{k}" value="{v}">'
        for k, v in params.items()
    )
    html = f"""<!DOCTYPE html>
<html>
<head><title>Redirecting to PayFast...</title>
<style>body{{background:#0a0a0f;color:#e8e8f2;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}.box{{text-align:center;}}.spinner{{width:40px;height:40px;border:3px solid #333;border-top-color:#7c6df0;border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px;}}@keyframes spin{{to{{transform:rotate(360deg)}}}}</style>
</head>
<body>
<div class="box">
  <div class="spinner"></div>
  <p>Redirecting to secure payment...</p>
  <form id="pf" action="{PAYFAST_URL}" method="post">{fields}</form>
</div>
<script>document.getElementById('pf').submit();</script>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.post("/api/webhook/payfast")
async def payfast_itn(request: Request):
    """PayFast Instant Transaction Notification handler."""
    body = await request.body()
    form = dict(urllib.parse.parse_qsl(body.decode()))

    received_sig = form.pop("signature", "")
    expected_sig = _generate_signature(form)

    if received_sig != expected_sig:
        raise HTTPException(status_code=400, detail="Invalid signature")

    status  = form.get("payment_status", "")
    email   = form.get("email_address", "")
    item    = form.get("item_name", "")
    tier    = "pro" if "Pro" in item else "beta"

    subs = _load_subs()

    if status == "COMPLETE":
        subs[email] = {
            "tier": tier,
            "status": "active",
            "since": datetime.now().isoformat(),
            "payment_id": form.get("m_payment_id", ""),
        }
        _save_subs(subs)

        # Create/update user profile
        try:
            from auth_handler import update_user_tier, get_or_create_user
            update_user_tier(email, tier)
        except Exception as e:
            print(f"[payfast] user update error: {e}")

        # Track analytics
        try:
            from analytics import payment_completed
            amount = PRICES.get(tier, {}).get("amount", "0")
            payment_completed(email, tier, amount)
        except Exception as e:
            print(f"[payfast] analytics error: {e}")

        # Fire welcome email (import here to avoid circular)
        try:
            from email_handler import send_welcome_email
            import asyncio
            asyncio.create_task(send_welcome_email(email, tier))
        except Exception:
            pass

    elif status == "CANCELLED":
        if email in subs:
            subs[email]["status"] = "cancelled"
            _save_subs(subs)

    return JSONResponse({"status": "ok"})


@router.get("/api/subscription/{email}")
async def get_subscription(email: str):
    subs = _load_subs()
    if email in subs:
        return subs[email]
    return {"status": "none", "tier": None}
# PayFast integration active
