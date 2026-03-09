"""
PodPal email integration via Resend API.
All keys from environment — no hardcoded values.
"""

import os

import httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = "hello@podpal.show"
RESEND_URL = "https://api.resend.com/emails"


async def _send(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Returns True on success."""
    if not RESEND_API_KEY:
        print(f"[email] RESEND_API_KEY not set — skipping email to {to}")
        return False
    if not to or "@" not in to:
        print(f"[email] Invalid recipient: {to!r}")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            )
            if resp.status_code in (200, 201):
                print(f"[email] Sent '{subject}' → {to}")
                return True
            else:
                print(f"[email] Resend error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        print(f"[email] Send failed: {e}")
        return False


# ── Templates ─────────────────────────────────────────────────────────────────

def _base_layout(content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <style>
    body {{ margin: 0; padding: 0; background: #08080f; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .wrap {{ max-width: 560px; margin: 0 auto; padding: 40px 24px; }}
    .logo {{ font-size: 22px; font-weight: 800; color: #e8e8f2; margin-bottom: 32px; }}
    .logo span {{ color: #4ecdc4; }}
    .card {{ background: #0f0f1a; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 32px; }}
    h1 {{ color: #e8e8f2; font-size: 22px; margin: 0 0 12px; }}
    p {{ color: #9b9bba; font-size: 15px; line-height: 1.7; margin: 0 0 16px; }}
    .btn {{ display: inline-block; background: #7c6df0; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; margin-top: 8px; }}
    .footer {{ margin-top: 28px; color: #555570; font-size: 12px; text-align: center; }}
    .highlight {{ color: #e8e8f2; font-weight: 600; }}
    .badge {{ display: inline-block; background: rgba(124,109,240,0.15); color: #7c6df0; border: 1px solid rgba(124,109,240,0.3); border-radius: 6px; padding: 3px 10px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">Pod<span>Pal</span></div>
    <div class="card">
      {content}
    </div>
    <div class="footer">
      PodPal · hello@podpal.show<br />
      You received this because you signed up at podpal.show.
    </div>
  </div>
</body>
</html>"""


def _welcome_html(email: str, tier: str) -> str:
    tier_label = {"beta": "Beta", "pro": "Pro"}.get(tier, tier.title())
    tier_price = {"beta": "$19/mo", "pro": "$79/mo"}.get(tier, "")
    locked = " — price locked for life" if tier == "beta" else ""

    content = f"""
    <div class="badge">{tier_label} Plan</div>
    <h1>You're in. Welcome to PodPal 🎙️</h1>
    <p>Your <span class="highlight">{tier_label} subscription ({tier_price}{locked})</span> is active and ready to go.</p>
    <p>You now have full access to PodPal's real-time research, live fact-checking, and suggested questions — all running silently in the background while you record.</p>
    <p><strong style="color:#e8e8f2;">Get started:</strong></p>
    <p style="margin:0 0 8px;">① Open the PodPal app and create a session<br />
    ② Enter your guest's name for a pre-interview intel brief<br />
    ③ Hit record — PodPal handles the rest</p>
    <a href="https://podpal.show/app" class="btn">Open PodPal →</a>
    <p style="margin-top:24px;font-size:13px;color:#555570;">Questions? Just reply to this email — we actually read them.</p>
    """
    return _base_layout(content)


def _waitlist_html(email: str, show: str) -> str:
    content = f"""
    <div class="badge">Waitlist Confirmed</div>
    <h1>You're on the list 🎉</h1>
    <p>We've saved your spot for <span class="highlight">{show or "your show"}</span>.</p>
    <p>PodPal's Beta is limited to 200 podcasters. When your spot opens, you'll be the first to know — and you'll lock in <span class="highlight">$19/month for life</span> (vs $79 at public launch).</p>
    <p>While you wait, take a look at what's coming:</p>
    <a href="https://podpal.show" class="btn">See PodPal in action →</a>
    <p style="margin-top:24px;font-size:13px;color:#555570;">Referred someone? Have a question? Hit reply — we're a small team and we respond.</p>
    """
    return _base_layout(content)


def _payment_failed_html(email: str) -> str:
    content = f"""
    <div class="badge" style="background:rgba(240,80,80,0.15);color:#f05050;border-color:rgba(240,80,80,0.3);">Action Required</div>
    <h1>Payment didn't go through</h1>
    <p>We couldn't process your PodPal subscription payment. This usually means your card expired or has insufficient funds.</p>
    <p>Your access is still active for now, but we'll need to pause it if payment doesn't go through in the next few days.</p>
    <p><strong style="color:#e8e8f2;">Fix it in 30 seconds:</strong></p>
    <a href="https://billing.stripe.com" class="btn" style="background:#f05050;">Update payment method →</a>
    <p style="margin-top:24px;font-size:13px;color:#555570;">Need help? Reply to this email and we'll sort it out.</p>
    """
    return _base_layout(content)


# ── Public send functions ──────────────────────────────────────────────────────

async def send_welcome_email(email: str, tier: str) -> bool:
    subject = f"You're in — PodPal {tier.title()} is active"
    return await _send(email, subject, _welcome_html(email, tier))


async def send_waitlist_confirmation(email: str, show: str = "") -> bool:
    subject = "You're on the PodPal waitlist 🎙️"
    return await _send(email, subject, _waitlist_html(email, show))


async def send_payment_failed_email(email: str) -> bool:
    subject = "PodPal: payment failed — action needed"
    return await _send(email, subject, _payment_failed_html(email))
