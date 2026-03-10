"""
PodPal email integration via Gmail SMTP (Google Workspace).
All keys from environment — no hardcoded values.
"""

import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER     = os.getenv("GMAIL_USER", "hello@podpal.show")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
FROM_EMAIL     = "PodPal <hello@podpal.show>"


def _send_smtp(to: str, subject: str, html: str) -> bool:
    """Send email via Gmail SMTP. Runs synchronously (called via run_in_executor)."""
    if not GMAIL_PASSWORD:
        print(f"[email] GMAIL_APP_PASSWORD not set — skipping email to {to}")
        return False
    if not to or "@" not in to:
        print(f"[email] Invalid recipient: {to!r}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = FROM_EMAIL
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, to, msg.as_string())

        print(f"[email] Sent '{subject}' → {to}")
        return True
    except Exception as e:
        print(f"[email] Send failed: {e}")
        return False


async def _send(to: str, subject: str, html: str) -> bool:
    """Async wrapper — runs SMTP in thread pool so it doesn't block."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_smtp, to, subject, html)


# ── Templates ─────────────────────────────────────────────────────────────────

def _base_layout(content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <style>
    body {{ margin:0;padding:0;background:#08080f;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    .wrap {{ max-width:560px;margin:0 auto;padding:40px 24px; }}
    .logo {{ font-size:22px;font-weight:800;color:#e8e8f2;margin-bottom:32px; }}
    .logo span {{ color:#4ecdc4; }}
    .card {{ background:#0f0f1a;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:32px; }}
    h1 {{ color:#e8e8f2;font-size:22px;margin:0 0 12px; }}
    p {{ color:#9b9bba;font-size:15px;line-height:1.7;margin:0 0 16px; }}
    .btn {{ display:inline-block;background:#7c6df0;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:15px;margin-top:8px; }}
    .footer {{ margin-top:28px;color:#555570;font-size:12px;text-align:center; }}
    .highlight {{ color:#e8e8f2;font-weight:600; }}
    .badge {{ display:inline-block;background:rgba(124,109,240,0.15);color:#7c6df0;border:1px solid rgba(124,109,240,0.3);border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">Pod<span>Pal</span></div>
    <div class="card">{content}</div>
    <div class="footer">PodPal · hello@podpal.show<br/>You received this because you signed up at podpal.show.</div>
  </div>
</body>
</html>"""


def _welcome_html(email: str, tier: str) -> str:
    tier_label = {"beta": "Beta", "pro": "Pro"}.get(tier, tier.title())
    tier_price = {"beta": "$19/mo", "pro": "$79/mo"}.get(tier, "")
    locked = " - price locked for life" if tier == "beta" else ""
    content = f"""
    <div class="badge">{tier_label} Plan</div>
    <h1>You're in. Welcome to PodPal 🎙</h1>
    <p>Your <span class="highlight">{tier_label} subscription ({tier_price}{locked})</span> is active.</p>
    <p>You now have full access to PodPal's real-time research, live talking points, and post-session show notes - all running while you record.</p>
    <p><strong style="color:#e8e8f2;">Get started:</strong><br/>
    Type your guest's name in setup - PodPal pre-loads their bio automatically.<br/>
    Hit record. Research appears as you talk.<br/>
    When you stop, your show notes and 3 social posts are ready.</p>
    <a href="https://podpal.show/app" class="btn">Open PodPal →</a>
    <p style="margin-top:24px;font-size:13px;color:#555570;">Questions? Reply to this email - we read every one.</p>"""
    return _base_layout(content)


def _magic_link_html(email: str, link: str) -> str:
    content = f"""
    <div class="badge">Login Link</div>
    <h1>Here's your PodPal link</h1>
    <p>You've got <span class="highlight">10 minutes of free recording</span> waiting for you. Click below to open the app - this link expires in 15 minutes.</p>
    <a href="{link}" class="btn">Open PodPal →</a>
    <p style="margin-top:20px;font-size:13px;color:#555570;">Didn't request this? Ignore it. The link expires in 15 minutes and nothing happens if you don't click.</p>"""
    return _base_layout(content)


def _welcome_trial_html(email: str) -> str:
    content = """
    <div class="badge">Welcome</div>
    <h1>Your 10 minutes start now</h1>
    <p>PodPal listens while you record. As you talk, it surfaces live research, suggests follow-up questions, and spots fact-check moments - all without you lifting a finger.</p>
    <p>In your 10-minute trial you get the full thing: real-time research cards, AI-suggested questions, and a session summary with social posts when you stop.</p>
    <p style="margin-bottom:4px;"><span class="highlight">When you upgrade to Beta ($19/mo) you unlock:</span></p>
    <p style="margin-top:0;">Unlimited sessions, guest intel pre-load before you go live, show notes export, and the AI question suggester on demand.</p>
    <a href="https://podpal.show/app" class="btn">Open the app →</a>
    <p style="margin-top:24px;font-size:13px;color:#555570;">Questions? Just reply - we read every one.</p>"""
    return _base_layout(content)


def _trial_expired_html(email: str) -> str:
    content = """
    <div class="badge" style="background:rgba(124,109,240,0.15);color:#7c6df0;border-color:rgba(124,109,240,0.3);">Trial Complete</div>
    <h1>Your PodPal trial is up</h1>
    <p>You just saw PodPal work in real time - research surfacing as you talk, questions appearing when you need them, and a summary waiting when you stop.</p>
    <p>Beta gets you all of that with no time limit, plus guest intel before you go live and show notes ready to publish. It's <span class="highlight">$19/mo</span> and you can cancel anytime.</p>
    <a href="https://podpal.show/dashboard" class="btn">Upgrade to Beta - $19/mo →</a>
    <p style="margin-top:20px;font-size:13px;color:#555570;">Not ready yet? No pressure. Your session data is saved. Come back when you are.</p>"""
    return _base_layout(content)


def _trial_reminder_html(email: str) -> str:
    content = """
    <div class="badge" style="background:rgba(255,165,0,0.12);color:#f0a040;border-color:rgba(255,165,0,0.3);">2 Minutes Left</div>
    <h1>2 minutes left on your trial</h1>
    <p>You're at 8 minutes in. PodPal stops recording at 10 minutes for free accounts.</p>
    <p>If you want to keep going - now or for any future episode - Beta is <span class="highlight">$19/mo</span> with no recording limits.</p>
    <a href="https://podpal.show/dashboard" class="btn">Upgrade to Beta →</a>
    <p style="margin-top:20px;font-size:13px;color:#555570;">Already done? Your summary and social posts are generating now.</p>"""
    return _base_layout(content)


def _waitlist_html(email: str, show: str) -> str:
    content = f"""
    <div class="badge">Waitlist Confirmed</div>
    <h1>You're on the list 🎉</h1>
    <p>We've saved your spot for <span class="highlight">{show or "your show"}</span>.</p>
    <p>PodPal Beta is limited to 200 podcasters. When your spot opens you'll lock in <span class="highlight">$19/month for life</span>.</p>
    <a href="https://podpal.show" class="btn">See PodPal →</a>"""
    return _base_layout(content)


def _payment_failed_html(email: str) -> str:
    content = f"""
    <div class="badge" style="background:rgba(240,80,80,0.15);color:#f05050;border-color:rgba(240,80,80,0.3);">Action Required</div>
    <h1>Payment didn't go through</h1>
    <p>We couldn't process your PodPal subscription. Your access is still active for now.</p>
    <p>Please update your payment method to keep access.</p>
    <a href="https://podpal.show/dashboard" class="btn" style="background:#f05050;">Update payment →</a>"""
    return _base_layout(content)


# ── Public send functions ──────────────────────────────────────────────────────

async def send_welcome_email(email: str, tier: str) -> bool:
    return await _send(email, f"You're in - PodPal {tier.title()} is active", _welcome_html(email, tier))

async def send_magic_link_email(email: str, link: str) -> bool:
    return await _send(email, "Here's your PodPal link", _magic_link_html(email, link))

async def send_welcome_trial_email(email: str) -> bool:
    """Sent on first login - not on magic link request."""
    return await _send(email, "Welcome to PodPal - your 10 minutes start now", _welcome_trial_html(email))

async def send_trial_expired_email(email: str) -> bool:
    """Sent when the 10-minute trial runs out."""
    return await _send(email, "Your PodPal trial is up", _trial_expired_html(email))

async def send_trial_reminder_email(email: str) -> bool:
    """Sent at 8 minutes used (2 minutes remaining)."""
    return await _send(email, "2 minutes left on your PodPal trial", _trial_reminder_html(email))

async def send_waitlist_confirmation(email: str, show: str = "") -> bool:
    return await _send(email, "You're on the PodPal waitlist 🎙", _waitlist_html(email, show))

async def send_payment_failed_email(email: str) -> bool:
    return await _send(email, "PodPal: payment failed - action needed", _payment_failed_html(email))
