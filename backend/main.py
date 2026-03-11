#!/usr/bin/env python3
"""
PodPal Backend - Real-time podcast AI co-pilot
FastAPI + WebSocket server that streams transcription, topic detection, and research
"""

import asyncio
import json
import os
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from payfast_handler import router as payfast_router
    _payfast_ok = True
except Exception as e:
    print(f"[WARN] PayFast handler failed to load: {e}")
    _payfast_ok = False

try:
    from auth_handler import router as auth_router, get_current_user
    _auth_ok = True
except Exception as e:
    print(f"[WARN] Auth handler failed to load: {e}")
    _auth_ok = False
    def get_current_user(request): return None

try:
    import analytics as _analytics
    _analytics_ok = True
except Exception as e:
    print(f"[WARN] Analytics failed to load: {e}")
    _analytics_ok = False

try:
    from email_handler import send_waitlist_confirmation
    _email_ok = True
except Exception as e:
    print(f"[WARN] Email handler failed to load: {e}")
    _email_ok = False
    async def send_waitlist_confirmation(*a, **kw): pass

try:
    from trial_handler import (
        get_trial_status, add_trial_time, is_trial_expired,
        increment_trial_sessions, expire_trial,
        redeem_trial_code, create_trial_code, list_trial_codes, grant_comp_access,
        TRIAL_LIMIT_SECONDS,
    )
    _trial_ok = True
except Exception as e:
    print(f"[WARN] Trial handler failed to load: {e}")
    _trial_ok = False

try:
    from profile_handler import router as profile_router
    _profile_ok = True
except Exception as e:
    print(f"[WARN] Profile handler failed to load: {e}")
    _profile_ok = False

load_dotenv()

app = FastAPI(title="PodPal", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if _payfast_ok:
    app.include_router(payfast_router)
if _auth_ok:
    app.include_router(auth_router)
if _profile_ok:
    app.include_router(profile_router)

# ── Prometheus metrics ────────────────────────────────────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_client import Counter, Gauge

    # Auto-instrument HTTP metrics (request count, duration, status codes)
    Instrumentator().instrument(app).expose(app)

    # Custom PodPal metrics
    active_sessions = Gauge(
        'podpal_active_sessions',
        'Number of active recording sessions'
    )
    total_transcriptions = Counter(
        'podpal_transcriptions_total',
        'Total transcription segments processed'
    )
    websocket_connections = Gauge(
        'podpal_websocket_connections',
        'Active WebSocket connections'
    )
    _metrics_ok = True
    print("[INFO] Prometheus metrics enabled on /metrics")
except Exception as _metrics_err:
    print(f"[WARN] Prometheus metrics not available: {_metrics_err}")
    _metrics_ok = False
    # Stub no-ops so the rest of the code doesn't break
    class _Noop:
        def inc(self): pass
        def dec(self): pass
        def labels(self, **kw): return self
    active_sessions = _Noop()
    total_transcriptions = _Noop()
    websocket_connections = _Noop()

# ── Page-view middleware ──────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware

class PageViewMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Track page views for HTML pages only (not API/WS/static)
        path = request.url.path
        if not path.startswith("/api/") and not path.startswith("/ws") and not "." in path.split("/")[-1]:
            try:
                if _analytics_ok:
                    user = get_current_user(request)
                    _analytics.page_view(path, user.get("email") if user else None)
            except Exception:
                pass
        return response

app.add_middleware(PageViewMiddleware)


# Config
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")


def _is_valid_key(key: str) -> bool:
    """Return False if key is empty, a SecretRef dict string, or looks non-functional."""
    if not key:
        return False
    s = key.strip()
    # SecretRef strings look like "{'ref': 'KEY_NAME'}" or "SecretRef(...)"
    if s.startswith('{') or 'SecretRef' in s or s.startswith('['):
        return False
    return True


claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Data directories
BASE_DIR = Path(__file__).parent.parent
SESSIONS_DIR = BASE_DIR / "data" / "sessions"
GUESTS_DIR = BASE_DIR / "data" / "guests"
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
GUESTS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory state (per session)
sessions: dict[str, "PodSession"] = {}


class PodSession:
    def __init__(self, session_id: str, host_profile: dict):
        self.session_id = session_id
        self.host_profile = host_profile
        self.transcript_buffer = deque(maxlen=200)
        self.full_transcript = []
        self.current_topic = ""
        self.last_research_at = 0
        self.last_transcript_text = ""
        self.research_cooldown = 15
        self.clients: list[WebSocket] = []
        self.start_time = time.time()
        self.user_email: Optional[str] = None
        # Tracked data for session history
        self.research_cards: list[dict] = []
        self.fact_check_results: list[dict] = []
        self.suggested_questions: list[str] = []
        self.topics_detected: list[str] = []

    def add_transcript(self, words: list[dict]):
        for word in words:
            self.transcript_buffer.append(word.get("word", ""))
            self.full_transcript.append(word)

    def get_recent_text(self, seconds: int = 60) -> str:
        return " ".join(list(self.transcript_buffer)[-100:])

    async def broadcast(self, event: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.remove(ws)

    def save_to_disk(self) -> Path:
        """Save session data to JSON file."""
        guest = self.host_profile.get("guest", "unknown")
        guest_slug = re.sub(r"[^a-z0-9]+", "-", guest.lower()).strip("-") or "unknown"
        dt = datetime.fromtimestamp(self.start_time)
        fname = dt.strftime(f"%Y-%m-%d-%H-%M-{guest_slug}.json")
        fpath = SESSIONS_DIR / fname

        transcript_text = " ".join([w.get("word", "") for w in self.full_transcript])
        snippets = []
        words = transcript_text.split()
        for i in range(0, min(len(words), 300), 60):
            chunk = " ".join(words[i:i+60])
            if chunk:
                snippets.append(chunk)

        data = {
            "session_id": self.session_id,
            "user_email": self.user_email or "",
            "start_time": self.start_time,
            "end_time": time.time(),
            "duration_seconds": int(time.time() - self.start_time),
            "metadata": {
                "guest": self.host_profile.get("guest", ""),
                "show": self.host_profile.get("show", ""),
                "host": self.host_profile.get("name", ""),
                "date": dt.strftime("%Y-%m-%d"),
                "notes": self.host_profile.get("notes", ""),
            },
            "topics_detected": list(dict.fromkeys(self.topics_detected)),
            "transcript_snippets": snippets[:5],
            "research_cards": self.research_cards[-10:],
            "fact_check_alerts": self.fact_check_results[-10:],
            "suggested_questions": list(dict.fromkeys(self.suggested_questions))[:10],
        }
        fpath.write_text(json.dumps(data, indent=2))
        return fpath


async def detect_topic(text: str, host_profile: dict, current_topic: str) -> dict:
    """Use Claude Haiku to detect current topic and whether it changed."""
    if not text.strip():
        return {"changed": False, "topic": current_topic, "entities": []}

    host_name = host_profile.get("name", "the host")
    host_topics = ", ".join(host_profile.get("topics", []))

    prompt = f"""You are analysing a live podcast transcript excerpt.
Host: {host_name} | Usual topics: {host_topics}
Previous topic: {current_topic or "none yet"}

Recent transcript (last ~60 seconds):
"{text}"

Respond in JSON only:
{{
  "topic": "2-5 word topic label",
  "changed": true/false,
  "entities": ["specific names/stats/claims mentioned"],
  "suggested_questions": ["2-3 follow-up questions the host could ask"],
  "fact_check": ["any specific factual claims that should be verified"]
}}"""

    try:
        resp = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Topic detection error: {e}")
        return {"changed": False, "topic": current_topic, "entities": [], "suggested_questions": [], "fact_check": []}


async def fetch_research(topic: str, entities: list[str], host_profile: dict) -> dict:
    """Fetch real-time research on the current topic."""
    query = topic
    if entities:
        query = f"{topic} {' '.join(entities[:2])}"

    results = {}

    if PERPLEXITY_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": f"Give me 3 key recent facts, statistics, or insights about: {query}. Be specific with numbers and sources. Format as bullet points."}],
                        "max_tokens": 300,
                    }
                )
                data = resp.json()
                results["research"] = data["choices"][0]["message"]["content"]
                results["source"] = "Perplexity"
        except Exception as e:
            print(f"Perplexity error: {e}")

    if not results.get("research") and _is_valid_key(BRAVE_API_KEY):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": BRAVE_API_KEY},
                    params={"q": query, "count": 3, "search_lang": "en"}
                )
                data = resp.json()
                brave_hits = data.get("web", {}).get("results", [])[:3]
                if brave_hits:
                    top_url = brave_hits[0].get("url", "")
                    result_snippets = "\n\n".join([
                        f"Title: {r.get('title', '')}\nSummary: {r.get('description', '')}\nURL: {r.get('url', '')}"
                        for r in brave_hits
                    ])
                    synth = await claude.messages.create(
                        model="claude-haiku-4-5",
                        max_tokens=400,
                        messages=[{"role": "user", "content": (
                            f"You are a research assistant helping a live podcast host. "
                            f"Synthesise these web search results about '{query}' into a clean 2-3 paragraph "
                            f"summary with specific facts and insights the host can use right now. "
                            f"Be concise and direct — no filler phrases.\n\n{result_snippets}"
                        )}]
                    )
                    results["research"] = synth.content[0].text
                    results["source"] = "Web Search"
                    results["source_url"] = top_url
        except Exception as e:
            print(f"Brave search error: {e}")

    if not results.get("research"):
        try:
            resp = await claude.messages.create(
                model="claude-haiku-4-5",
                max_tokens=250,
                messages=[{"role": "user", "content": f"Give me 3 key facts or statistics about '{query}' that would be useful in a podcast conversation. Be specific."}]
            )
            results["research"] = resp.content[0].text
            results["source"] = "AI Knowledge"
        except Exception as e:
            print(f"Claude fallback error: {e}")
            results["research"] = "Research unavailable"
            results["source"] = "Error"

    return results


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in sessions:
        await websocket.send_json({"type": "error", "message": "Session not found. Create session first."})
        await websocket.close()
        return

    session = sessions[session_id]
    session.clients.append(websocket)
    websocket_connections.inc()
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "transcript":
                words = data.get("words", [])
                text = data.get("text", "")
                session.add_transcript(words)
                total_transcriptions.inc()

                await session.broadcast({
                    "type": "transcript_update",
                    "text": text,
                    "timestamp": time.time()
                })

                now = time.time()
                recent_text = session.get_recent_text()

                if (now - session.last_research_at) >= session.research_cooldown and recent_text != session.last_transcript_text:
                    session.last_transcript_text = recent_text
                    session.last_research_at = now
                    asyncio.create_task(run_intelligence(session, recent_text))

            elif event_type == "stop_session":
                questions_asked = data.get("questions_asked", [])
                questions_unasked = data.get("questions_unasked", [])
                asyncio.create_task(generate_session_summary(session, questions_asked, questions_unasked))

            elif event_type == "suggest_question":
                context = data.get("context", "")
                if _analytics_ok:
                    try:
                        _analytics.feature_used(getattr(session, "user_email", None), "suggest_question")
                    except Exception:
                        pass
                asyncio.create_task(generate_question_suggestion(session, context))

            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if websocket in session.clients:
            session.clients.remove(websocket)
        websocket_connections.dec()


async def run_intelligence(session: PodSession, recent_text: str):
    """Run topic detection + research in background."""
    try:
        topic_data = await detect_topic(recent_text, session.host_profile, session.current_topic)

        topic = topic_data.get("topic", session.current_topic)
        changed = topic_data.get("changed", False)
        entities = topic_data.get("entities", [])
        questions = topic_data.get("suggested_questions", [])
        fact_checks = topic_data.get("fact_check", [])

        # Track in session
        if topic and topic not in session.topics_detected:
            session.topics_detected.append(topic)
        for q in questions:
            if q not in session.suggested_questions:
                session.suggested_questions.append(q)

        await session.broadcast({
            "type": "topic_update",
            "topic": topic,
            "changed": changed,
            "suggested_questions": questions,
            "fact_checks": fact_checks,
            "timestamp": time.time()
        })

        if changed or not session.current_topic:
            session.current_topic = topic
            research = await fetch_research(topic, entities, session.host_profile)
            card = {
                "topic": topic,
                "research": research.get("research", ""),
                "source": research.get("source", ""),
                "source_url": research.get("source_url", ""),
                "timestamp": time.time()
            }
            session.research_cards.append(card)
            await session.broadcast({"type": "research_update", **card})
        elif fact_checks:
            for claim in fact_checks[:2]:
                research = await fetch_research(claim, [], session.host_profile)
                fc = {
                    "claim": claim,
                    "result": research.get("research", ""),
                    "source": research.get("source", ""),
                    "timestamp": time.time()
                }
                session.fact_check_results.append(fc)
                await session.broadcast({"type": "fact_check", **fc})

    except Exception as e:
        print(f"Intelligence error: {e}")


async def generate_session_summary(session: PodSession, questions_asked: list = None, questions_unasked: list = None):
    """Generate a post-session summary: bullets, social posts, show notes."""
    transcript_text = " ".join([w.get("word", "") for w in session.full_transcript])
    if not transcript_text.strip():
        await session.broadcast({
            "type": "session_summary",
            "bullets": ["No transcript was recorded."],
            "posts": [],
            "show_notes": "No content was recorded in this session."
        })
        return

    guest = session.host_profile.get("guest", "the guest")
    show = session.host_profile.get("show", "the podcast")

    questions_ctx = ""
    if questions_asked:
        questions_ctx += "\nQuestions asked during the interview:\n" + "\n".join(f"- {q}" for q in questions_asked[:12])
    if questions_unasked:
        questions_ctx += "\nQuestions not covered (could fuel a follow-up episode):\n" + "\n".join(f"- {q}" for q in questions_unasked[:5])

    prompt = f"""You are a podcast production assistant for "{show}". Analyse this transcript and produce a post-session package.

Transcript:
{transcript_text[:5000]}
{questions_ctx}

Return JSON only — no markdown, no extra text:
{{
  "bullets": [
    "5 specific bullet points summarising what was actually discussed (not generic — name topics, claims, and key moments)",
    "bullet 2",
    "bullet 3",
    "bullet 4",
    "bullet 5"
  ],
  "posts": [
    "Social post 1 — under 280 chars, no em dashes, no buzzwords (leverage/synergy/transformative/groundbreaking etc), specific and punchy",
    "Social post 2 — same rules, different angle",
    "Social post 3 — same rules, a question or hook"
  ],
  "show_notes": "One concise paragraph of show notes. Specific topics, key insights, guest name if known. No filler. Write in third person."
}}"""

    try:
        resp = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        summary_data = json.loads(raw)
        await session.broadcast({"type": "session_summary", **summary_data})
    except Exception as e:
        print(f"Session summary error: {e}")
        await session.broadcast({
            "type": "session_summary",
            "bullets": ["Summary generation failed — check logs."],
            "posts": [],
            "show_notes": "Could not generate show notes for this session."
        })


async def generate_question_suggestion(session: PodSession, context: str):
    """Use Claude Haiku to generate a single sharp follow-up question from recent transcript."""
    words = context.split()[-100:] if context.strip() else []
    recent = " ".join(words).strip()

    if not recent:
        await session.broadcast({
            "type": "question_suggestion",
            "question": "What's the one thing you'd want our audience to remember from this conversation?"
        })
        return

    host_name = session.host_profile.get("name", "the host")
    guest_name = session.host_profile.get("guest", "the guest")

    prompt = f"""You are a live podcast co-pilot helping {host_name} interview {guest_name}.

Based on the last thing said, generate ONE sharp, specific follow-up question the host should ask RIGHT NOW. 

Recent transcript:
"{recent}"

Rules:
- Output ONLY the question — no labels, no explanation, no quotes
- Under 20 words
- Specific and curious, not generic ("tell me more about X" is lazy)
- Conversational — the kind of question that catches a guest off-guard in a good way
- No filler phrases"""

    try:
        resp = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        question = resp.content[0].text.strip().strip('"').strip("'")
        # Track it
        if question and question not in session.suggested_questions:
            session.suggested_questions.append(question)
        await session.broadcast({"type": "question_suggestion", "question": question})
    except Exception as e:
        print(f"Question suggestion error: {e}")
        await session.broadcast({
            "type": "question_suggestion",
            "question": "What surprised you most about that?"
        })


# ── Session endpoints ────────────────────────────────────────────────────────

@app.post("/session/create")
async def create_session(payload: dict, request: Request):
    session_id   = f"session_{int(time.time())}"
    host_profile = payload.get("host_profile", {})
    sessions[session_id] = PodSession(session_id, host_profile)
    active_sessions.inc()

    # Associate with logged-in user
    user       = get_current_user(request)
    user_email = None
    if user:
        user_email = user.get("email")
        sessions[session_id].user_email = user_email
        try:
            from auth_handler import add_session_to_user
            add_session_to_user(user_email, session_id)
        except Exception:
            pass

        # Trial gate: free tier only
        if _trial_ok and user.get("tier", "free") == "free":
            if is_trial_expired(user_email):
                return JSONResponse(
                    {"error": "trial_expired", "type": "trial_expired"},
                    status_code=403
                )
            increment_trial_sessions(user_email)

    # Track analytics
    if _analytics_ok:
        try:
            _analytics.session_started(user_email, session_id)
        except Exception:
            pass

    return {
        "session_id": session_id,
        "status": "created",
        "user_email": user_email,
        "deepgram_key": DEEPGRAM_API_KEY[:8] + "..." if DEEPGRAM_API_KEY else "NOT SET"
    }


@app.post("/session/{session_id}/save")
async def save_session(session_id: str):
    """Save session data to disk."""
    if session_id not in sessions:
        return {"error": "Not found"}
    s = sessions[session_id]
    fpath = s.save_to_disk()
    # Track session_completed analytics
    if _analytics_ok:
        try:
            word_count = len(s.full_transcript)
            duration = int(time.time() - s.start_time)
            _analytics.session_completed(s.user_email, session_id, duration, word_count)
        except Exception:
            pass
    return {"ok": True, "file": fpath.name}


@app.post("/api/analytics/feature")
async def track_feature(payload: dict, request: Request):
    """Track feature usage from frontend."""
    user = get_current_user(request)
    feature = payload.get("feature", "unknown")
    if _analytics_ok:
        try:
            _analytics.feature_used(user.get("email") if user else None, feature)
        except Exception:
            pass
    return {"ok": True}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        return {"error": "Not found"}
    session = sessions[session_id]
    return {
        "session_id": session_id,
        "current_topic": session.current_topic,
        "transcript_words": len(session.transcript_buffer),
        "clients": len(session.clients)
    }


@app.get("/session/{session_id}/transcript")
async def get_transcript(session_id: str):
    if session_id not in sessions:
        return {"error": "Not found"}
    session = sessions[session_id]
    text = " ".join([w.get("word", "") for w in session.full_transcript])
    return {"transcript": text, "word_count": len(session.full_transcript)}


@app.get("/api/session/{session_id}/export")
async def export_session(session_id: str, request: Request):
    """Export session as show notes markdown. Requires beta+ tier."""
    user = get_current_user(request)
    if user:
        tier_order = {"free": 0, "beta": 1, "pro": 2, "network": 3}
        if tier_order.get(user.get("tier", "free"), 0) < 1:
            from fastapi.responses import JSONResponse as _JR
            return _JR({"error": "tier_required", "required": "beta"}, status_code=403)
        if _analytics_ok:
            try: _analytics.feature_used(user.get("email"), "export")
            except Exception: pass
    if session_id not in sessions:
        return {"error": "Not found"}
    s = sessions[session_id]
    md = _build_show_notes(s)
    from fastapi.responses import Response
    fname = f"show-notes-{session_id}.md"
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _build_show_notes(s: PodSession) -> str:
    meta = s.host_profile
    dur = int(time.time() - s.start_time)
    dur_str = f"{dur//60}m {dur%60}s"
    date_str = datetime.fromtimestamp(s.start_time).strftime("%Y-%m-%d")
    topics = list(dict.fromkeys(s.topics_detected))
    questions = list(dict.fromkeys(s.suggested_questions))[:5]
    research = s.research_cards[:5]
    fact_checks = s.fact_check_results[:5]

    lines = [
        f"# Show Notes – {meta.get('show', 'My Podcast')}",
        "",
        f"**Episode Title:** {meta.get('notes', 'Untitled Episode')[:80]}",
        f"**Guest:** {meta.get('guest', 'N/A')}",
        f"**Host:** {meta.get('name', 'N/A')}",
        f"**Date:** {date_str}",
        f"**Duration:** {dur_str}",
        "",
        "---",
        "",
        "## Key Topics Discussed",
        "",
    ]
    for t in topics or ["(none detected)"]:
        lines.append(f"- {t}")
    lines += ["", "## Research Highlights", ""]
    for card in research:
        lines.append(f"### {card.get('topic', 'Topic')}")
        lines.append(card.get('research', ''))
        lines.append(f"*Source: {card.get('source', '')}*")
        lines.append("")
    lines += ["## Fact-Checks", ""]
    for fc in fact_checks:
        lines.append(f"**Claim:** {fc.get('claim', '')}")
        lines.append(f"{fc.get('result', '')}")
        lines.append("")
    lines += ["## Best Questions Asked", ""]
    for q in questions or ["(none recorded)"]:
        lines.append(f"- {q}")
    lines += ["", "## Host Notes", "", "> *(Add your notes here)*", "", "---", "*Generated by PodPal*"]
    return "\n".join(lines)


# ── Sessions list (for history page) ────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions(request: Request):
    """List saved sessions. If logged in, shows only user's sessions; otherwise all."""
    user = get_current_user(request)
    user_email = user.get("email") if user else None
    files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)
    result = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            owner = data.get("user_email", "")
            # Filter: authenticated users see their own sessions only; anon sees anonymous sessions
            if user_email:
                if owner and owner != user_email:
                    continue
            result.append({
                "file": f.name,
                "session_id": data.get("session_id", ""),
                "user_email": owner,
                "metadata": data.get("metadata", {}),
                "duration_seconds": data.get("duration_seconds", 0),
                "topics_count": len(data.get("topics_detected", [])),
                "questions_count": len(data.get("suggested_questions", [])),
                "research_count": len(data.get("research_cards", [])),
                "fact_checks_count": len(data.get("fact_check_alerts", [])),
                "start_time": data.get("start_time", 0),
            })
        except Exception:
            pass
    return result


@app.get("/api/sessions/{filename}")
async def get_session_file(filename: str):
    """Get full session data by filename."""
    fpath = SESSIONS_DIR / filename
    if not fpath.exists():
        return {"error": "Not found"}
    return json.loads(fpath.read_text())


@app.get("/api/session/{session_id}")
async def get_session_detail(session_id: str, request: Request):
    """Return full session JSON for the session viewer page (auth required)."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    files = list(SESSIONS_DIR.glob("*.json"))
    for f in files:
        try:
            data = json.loads(f.read_text())
            if data.get("session_id") == session_id:
                if data.get("user_email") and data.get("user_email") != user.get("email"):
                    raise HTTPException(status_code=403, detail="Access denied")
                return data
        except HTTPException:
            raise
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/session-file/{session_id}/export")
async def export_session_file(session_id: str):
    """Export a saved session (by session_id) as show notes markdown."""
    files = list(SESSIONS_DIR.glob("*.json"))
    for f in files:
        try:
            data = json.loads(f.read_text())
            if data.get("session_id") == session_id:
                md = _build_show_notes_from_data(data)
                from fastapi.responses import Response
                fname = f"show-notes-{session_id}.md"
                return Response(content=md, media_type="text/markdown",
                                headers={"Content-Disposition": f'attachment; filename="{fname}"'})
        except Exception:
            pass
    return {"error": "Not found"}


def _build_show_notes_from_data(data: dict) -> str:
    meta = data.get("metadata", {})
    dur = data.get("duration_seconds", 0)
    dur_str = f"{dur//60}m {dur%60}s"
    date_str = meta.get("date", "")
    topics = data.get("topics_detected", [])
    questions = data.get("suggested_questions", [])[:5]
    research = data.get("research_cards", [])[:5]
    fact_checks = data.get("fact_check_alerts", [])[:5]

    lines = [
        f"# Show Notes – {meta.get('show', 'My Podcast')}",
        "",
        f"**Episode Title:** {meta.get('notes', 'Untitled Episode')[:80]}",
        f"**Guest:** {meta.get('guest', 'N/A')}",
        f"**Host:** {meta.get('host', 'N/A')}",
        f"**Date:** {date_str}",
        f"**Duration:** {dur_str}",
        "",
        "---",
        "",
        "## Key Topics Discussed",
        "",
    ]
    for t in topics or ["(none detected)"]:
        lines.append(f"- {t}")
    lines += ["", "## Research Highlights", ""]
    for card in research:
        lines.append(f"### {card.get('topic', 'Topic')}")
        lines.append(card.get('research', ''))
        lines.append(f"*Source: {card.get('source', '')}*")
        lines.append("")
    lines += ["## Fact-Checks", ""]
    for fc in fact_checks:
        lines.append(f"**Claim:** {fc.get('claim', '')}")
        lines.append(f"{fc.get('result', '')}")
        lines.append("")
    lines += ["## Best Questions Asked", ""]
    for q in questions or ["(none recorded)"]:
        lines.append(f"- {q}")
    lines += ["", "## Host Notes", "", "> *(Add your notes here)*", "", "---", "*Generated by PodPal*"]
    return "\n".join(lines)


# ── Guest Intel ──────────────────────────────────────────────────────────────

@app.post("/api/guest-intel")
async def guest_intel(payload: dict, request: Request):
    """Research a guest and return a structured brief. Requires beta+ tier."""
    # Tier check
    user = get_current_user(request)
    if user:
        tier_order = {"free": 0, "beta": 1, "pro": 2, "network": 3}
        if tier_order.get(user.get("tier", "free"), 0) < 1:
            from fastapi.responses import JSONResponse as _JR
            return _JR({"error": "tier_required", "required": "beta", "message": "Guest intel requires Beta or higher."}, status_code=403)
        if _analytics_ok:
            try: _analytics.feature_used(user.get("email"), "guest_intel")
            except Exception: pass
    guest_name = payload.get("name", "")
    social_url = payload.get("social_url", "")
    if not guest_name:
        return {"error": "Guest name required"}

    guest_slug = re.sub(r"[^a-z0-9]+", "-", guest_name.lower()).strip("-")
    cache_file = GUESTS_DIR / f"{guest_slug}.json"

    # Return cached if fresh (<24h)
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if time.time() - cached.get("cached_at", 0) < 86400:
            return cached

    context = f"Guest: {guest_name}"
    if social_url:
        context += f"\nSocial profile: {social_url}"

    search_results = ""

    # Try Brave Search first
    if BRAVE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": BRAVE_API_KEY},
                    params={"q": f"{guest_name} podcast speaker bio", "count": 5}
                )
                data = resp.json()
                snippets = [r.get("description", "") for r in data.get("web", {}).get("results", [])[:4]]
                search_results = "\n".join(snippets)
        except Exception as e:
            print(f"Brave guest search error: {e}")

    prompt = f"""Research this podcast guest and create a structured brief for the host.

{context}
{"Search results: " + search_results if search_results else "Use your knowledge."}

Return JSON only:
{{
  "bio": "2-3 sentence bio",
  "key_works": ["project/book/company 1", "project/book/company 2", "project/book/company 3"],
  "known_positions": ["their stance on topic 1", "their stance on topic 2"],
  "recent_activity": "1-2 sentences on recent news/projects",
  "suggested_questions": [
    "specific question 1",
    "specific question 2",
    "specific question 3",
    "specific question 4",
    "specific question 5"
  ]
}}"""

    try:
        resp = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        brief = json.loads(raw)
        brief["name"] = guest_name
        brief["slug"] = guest_slug
        brief["cached_at"] = time.time()
        cache_file.write_text(json.dumps(brief, indent=2))
        return brief
    except Exception as e:
        print(f"Guest intel error: {e}")
        return {"error": str(e)}


# ── Questions endpoints ──────────────────────────────────────────────────────

@app.post("/api/questions/generate")
async def generate_questions(request: Request):
    """Generate AI interview questions for a guest. Requires ANTHROPIC_API_KEY."""
    body = await request.json()
    guest_name = body.get("guest_name", "")
    topic = body.get("topic", "")
    guest_profile = body.get("guest_profile", {})
    num_questions = body.get("num_questions", 12)

    if not _is_valid_key(ANTHROPIC_API_KEY):
        return JSONResponse({"error": "AI generation requires API key — set ANTHROPIC_API_KEY on the server"}, status_code=503)

    profile_summary = ""
    if guest_profile:
        bio = guest_profile.get("background", guest_profile.get("bio", ""))
        recent = guest_profile.get("recent_work", guest_profile.get("key_works", []))
        topics = guest_profile.get("topics", [])
        quotes = guest_profile.get("quotes", guest_profile.get("key_beliefs", []))
        profile_summary = f"""
Guest background: {bio}
Recent work: {', '.join(recent[:3]) if recent else ''}
Key topics: {', '.join(topics[:5]) if topics else ''}
Notable positions: {', '.join(quotes[:2]) if quotes else ''}
"""

    prompt = f"""Generate {num_questions} sharp interview questions for a podcast interview.

Guest: {guest_name}
Topic/focus: {topic or 'their area of expertise'}
{profile_summary}

Requirements:
- Questions must be specific, not generic. "What advice would you give?" is banned.
- Mix of: opening warmup (1-2), deep expertise (4-5), contrarian/challenging (2-3), future/vision (2-3), personal (1-2)
- Each question should invite a story or specific example, not a yes/no
- No em dashes anywhere
- Label each with its type in brackets: [warmup] [expertise] [challenge] [vision] [personal]

Return as a JSON array of objects:
[
  {{"id": "q1", "question": "...", "type": "warmup", "theme": "background"}},
  ...
]

Return ONLY the JSON array, no other text."""

    # Check for pre-loaded questions from guest profile first (fallback)
    def get_preloaded_questions(name):
        slug = name.lower().replace(" ", "-").replace(".", "")
        gf = GUESTS_DIR / f"{slug}.json"
        if gf.exists():
            data = json.loads(gf.read_text())
            qs = data.get("suggested_questions", [])
            if qs:
                return [{"id": f"q{i+1}", "question": q, "type": "expertise", "theme": "general"} for i, q in enumerate(qs)]
        return []

    try:
        message = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        try:
            questions = json.loads(raw)
        except Exception:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            questions = json.loads(raw[start:end])
        return {"questions": questions, "guest": guest_name, "topic": topic}
    except Exception as e:
        print(f"Generate questions error: {e}")
        # Fallback to pre-loaded questions
        preloaded = get_preloaded_questions(guest_name)
        if preloaded:
            print(f"Using {len(preloaded)} pre-loaded questions for {guest_name}")
            return {"questions": preloaded, "guest": guest_name, "topic": topic, "source": "preloaded"}
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/guests")
async def list_guests():
    """List all saved guest profiles."""
    if not GUESTS_DIR.exists():
        return []
    guests = []
    for f in GUESTS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            guests.append({"slug": f.stem, "name": data.get("name", f.stem), "title": data.get("title", "")})
        except Exception:
            pass
    return guests


@app.get("/api/guests/{guest_slug}")
async def get_guest(guest_slug: str):
    """Return a cached guest profile by slug."""
    guest_file = GUESTS_DIR / f"{guest_slug}.json"
    if not guest_file.exists():
        raise HTTPException(status_code=404, detail="Guest not found")
    return json.loads(guest_file.read_text())


# ── Misc endpoints ───────────────────────────────────────────────────────────

@app.post("/api/waitlist")
async def join_waitlist(payload: dict):
    wl_file = BASE_DIR / "data" / "waitlist.json"
    wl_file.parent.mkdir(exist_ok=True)
    entries = json.loads(wl_file.read_text()) if wl_file.exists() else []
    entry = {
        "email": payload.get("email", ""),
        "show": payload.get("show", ""),
        "ts": payload.get("ts", ""),
        "ip": "hidden"
    }
    entries.append(entry)
    wl_file.write_text(json.dumps(entries, indent=2))
    print(f"Waitlist signup: {entry['email']} - {entry['show']}")

    # Send confirmation email (non-blocking)
    asyncio.create_task(
        send_waitlist_confirmation(entry["email"], entry["show"])
    )

    return {"ok": True, "position": len(entries)}


@app.get("/api/waitlist/count")
async def waitlist_count():
    wl_file = BASE_DIR / "data" / "waitlist.json"
    entries = json.loads(wl_file.read_text()) if wl_file.exists() else []
    return {"count": len(entries)}


# ── Trial endpoints ──────────────────────────────────────────────────────────

@app.get("/api/trial/status")
async def trial_status(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)
    return get_trial_status(user["email"])


@app.post("/api/trial/redeem")
async def api_trial_redeem(payload: dict, request: Request):
    """Redeem a trial code via JSON POST. Called by welcome.html."""
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)
    code = (payload.get("code") or "").strip()
    if not code:
        return JSONResponse({"error": "No code provided"}, status_code=400)
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated — please log in first"}, status_code=401)
    result = redeem_trial_code(code, user["email"])
    if not result.get("ok"):
        return JSONResponse({"success": False, "error": result.get("error", "Invalid or expired code")}, status_code=400)
    return JSONResponse({
        "success": True,
        "tier": result.get("tier"),
        "days": result.get("days"),
        "expires": result.get("expires"),
    })


@app.post("/api/trial/tick")
async def trial_tick(payload: dict, request: Request):
    """Called by frontend every 30 seconds while recording.
    Adds seconds to trial and broadcasts trial_expired if needed."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)

    email = user["email"]
    seconds = min(int(payload.get("seconds", 30)), 60)  # cap at 60 per tick
    status = add_trial_time(email, seconds)

    # If trial just expired, broadcast to any open WS sessions for this user
    if status.get("expired") and status.get("tier") == "free":
        for sess in sessions.values():
            if getattr(sess, "user_email", None) == email:
                asyncio.create_task(sess.broadcast({"type": "trial_expired"}))

    # Send trial reminder email after 2nd session (1 remaining) - only once
    if _email_ok and status.get("sessions_used", 0) >= 2 and not status.get("expired"):
        reminder_sent_key = f"trial_reminder_sent_{email}"
        if not _tick_state.get(reminder_sent_key):
            _tick_state[reminder_sent_key] = True
            try:
                from email_handler import send_trial_reminder_email
                asyncio.create_task(send_trial_reminder_email(email))
            except Exception:
                pass

    # Send trial expired email once
    if _email_ok and status.get("expired"):
        expired_sent_key = f"trial_expired_sent_{email}"
        if not _tick_state.get(expired_sent_key):
            _tick_state[expired_sent_key] = True
            try:
                from email_handler import send_trial_expired_email
                asyncio.create_task(send_trial_expired_email(email))
            except Exception:
                pass

    return status


# In-memory state for one-shot email triggers (resets on server restart - fine for our scale)
_tick_state: dict = {}


@app.get("/trial")
async def redeem_code_page(code: str, request: Request):
    """Shareable trial link. Validates code, sets user tier, redirects to /welcome."""
    if not _trial_ok:
        return HTMLResponse("<h2>Trial system unavailable.</h2>", status_code=503)
    if not code:
        return HTMLResponse("<h2>No code provided.</h2>", status_code=400)

    # Require login to redeem (create anonymous session or redirect to login)
    user = get_current_user(request)
    if not user:
        # Store code in redirect URL so they can redeem after login
        from urllib.parse import quote
        next_url = quote(f"/trial?code={code}", safe="")
        return RedirectResponse(url=f"/login?next={next_url}", status_code=302)

    email = user["email"]
    result = redeem_trial_code(code, email)
    if not result["ok"]:
        return HTMLResponse(
            f"<h2>Code error: {result.get('error', 'Unknown error')}</h2>"
            "<p><a href='/app'>Go to app</a></p>",
            status_code=400
        )

    tier = result["tier"]
    days = result["days"]
    return RedirectResponse(url=f"/welcome?trial={tier}&days={days}", status_code=302)


# ── Admin trial-code endpoints ─────────────────────────────────────────────

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "mic@mannmade.co.za")


def _require_admin(request: Request):
    user = get_current_user(request)
    if not user:
        return None, JSONResponse({"error": "Not authenticated"}, status_code=401)
    if user.get("email", "").lower() != ADMIN_EMAIL.lower():
        return None, JSONResponse({"error": "Forbidden"}, status_code=403)
    return user, None


@app.get("/api/admin/trial-codes")
async def admin_list_trial_codes(request: Request):
    _, err = _require_admin(request)
    if err:
        return err
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)
    return {"codes": list_trial_codes()}


@app.post("/api/admin/trial-codes")
async def admin_create_trial_code(payload: dict, request: Request):
    _, err = _require_admin(request)
    if err:
        return err
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)
    code = (payload.get("code") or "").strip().upper()
    tier = payload.get("tier", "pro")
    days = int(payload.get("days", 7))
    if not code:
        return JSONResponse({"error": "Code required"}, status_code=400)
    entry = create_trial_code(code, tier, days)
    return {"ok": True, "code": code, **entry}


@app.post("/api/admin/comp-access")
async def admin_comp_access(payload: dict, request: Request):
    _, err = _require_admin(request)
    if err:
        return err
    if not _trial_ok:
        return JSONResponse({"error": "Trial system unavailable"}, status_code=503)

    email = (payload.get("email") or "").strip().lower()
    tier  = payload.get("tier", "beta")
    days  = int(payload.get("days", 30))

    if not email or "@" not in email:
        return JSONResponse({"error": "Valid email required"}, status_code=400)
    if tier not in ("beta", "pro", "network"):
        return JSONResponse({"error": "Invalid tier"}, status_code=400)

    result = grant_comp_access(email, tier, days)

    # Send welcome email for the granted tier
    if _email_ok:
        try:
            from email_handler import send_welcome_email
            asyncio.create_task(send_welcome_email(email, tier))
        except Exception:
            pass

    return result


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/status")
async def status():
    """Real-time PodPal health and metrics - no external services needed."""
    import psutil, time as _time

    # Sessions
    active = [s for s in _sessions.values() if getattr(s, "recording", False)]
    all_sessions = list(_sessions.values())

    # Users
    users_data = json.loads(USERS_FILE.read_text()) if USERS_FILE.exists() else {}
    total_users = len(users_data)
    trial_users = sum(1 for u in users_data.values() if u.get("tier") == "trial")
    paid_users = sum(1 for u in users_data.values() if u.get("tier") in ("beta", "pro"))

    # Recent errors from log
    errors_today = []
    log_path = BASE_DIR / "data" / "podpal_errors.log"
    if log_path.exists():
        lines = log_path.read_text().splitlines()[-50:]
        errors_today = [l for l in lines if "ERROR" in l]

    # System
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Uptime
    boot_time = psutil.boot_time()
    uptime_hours = (_time.time() - boot_time) / 3600

    return {
        "status": "ok",
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "podpal": {
            "active_sessions": len(active),
            "total_sessions_loaded": len(all_sessions),
            "websocket_connections": len(_sessions),
        },
        "users": {
            "total": total_users,
            "trial": trial_users,
            "paid": paid_users,
        },
        "errors": {
            "recent_count": len(errors_today),
            "last_error": errors_today[-1] if errors_today else None,
        },
        "system": {
            "cpu_percent": cpu,
            "memory_used_gb": round(mem.used / 1024**3, 2),
            "memory_total_gb": round(mem.total / 1024**3, 2),
            "memory_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1024**3, 2),
            "disk_free_gb": round(disk.free / 1024**3, 2),
            "uptime_hours": round(uptime_hours, 1),
        },
    }


# ── Static serving ───────────────────────────────────────────────────────────

frontend_dir = BASE_DIR / "frontend" / "dist"
landing_dir = BASE_DIR / "landing"


@app.get("/app")
@app.get("/app/")
async def serve_app():
    app_html = frontend_dir / "index.html"
    return HTMLResponse(content=app_html.read_text())


@app.get("/session")
@app.get("/session/")
async def serve_session_page():
    sess_html = frontend_dir / "session.html"
    if sess_html.exists():
        return HTMLResponse(content=sess_html.read_text())
    return HTMLResponse("<h1>Session page not found</h1>", status_code=404)


@app.get("/history")
@app.get("/history/")
async def serve_history():
    hist_html = frontend_dir / "history.html"
    if hist_html.exists():
        return HTMLResponse(content=hist_html.read_text())
    return HTMLResponse("<h1>History page not found</h1>", status_code=404)


if landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(landing_dir), html=True), name="landing")


# ── Drip email background task ────────────────────────────────────────────────

async def _drip_loop():
    """Background task: checks every hour and sends scheduled drip emails."""
    import time as _time
    while True:
        try:
            await asyncio.sleep(3600)  # run every hour
            _run_drip_check()
        except Exception as e:
            print(f"[drip] Loop error: {e}")


def _run_drip_check():
    try:
        from pathlib import Path as _Path
        import json as _json
        from datetime import datetime as _dt

        users_path = BASE_DIR / "data" / "users.json"
        if not users_path.exists():
            return
        users = _json.loads(users_path.read_text())
        now   = _dt.utcnow()
        changed = False

        for email, user in users.items():
            if not email or "@" not in email:
                continue
            tier = user.get("tier", "free")

            # Day 3
            d3_at   = user.get("drip_day3_at")
            d3_sent = user.get("drip_day3_sent", False)
            if d3_at and not d3_sent and tier == "free":
                try:
                    if now >= _dt.fromisoformat(d3_at):
                        sessions_used = user.get("trial_sessions_used", 0)
                        asyncio.create_task(_send_drip3(email, sessions_used))
                        users[email]["drip_day3_sent"] = True
                        changed = True
                except Exception as e:
                    print(f"[drip] Day3 error {email}: {e}")

            # Day 6
            d6_at   = user.get("drip_day6_at")
            d6_sent = user.get("drip_day6_sent", False)
            if d6_at and not d6_sent and tier == "free":
                try:
                    if now >= _dt.fromisoformat(d6_at):
                        asyncio.create_task(_send_drip6(email))
                        users[email]["drip_day6_sent"] = True
                        changed = True
                except Exception as e:
                    print(f"[drip] Day6 error {email}: {e}")

            # Day 7
            d7_at   = user.get("drip_day7_at")
            d7_sent = user.get("drip_day7_sent", False)
            if d7_at and not d7_sent and tier == "free":
                try:
                    if now >= _dt.fromisoformat(d7_at):
                        asyncio.create_task(_send_drip7(email))
                        users[email]["drip_day7_sent"] = True
                        changed = True
                except Exception as e:
                    print(f"[drip] Day7 error {email}: {e}")

        if changed:
            users_path.write_text(_json.dumps(users, indent=2))
    except Exception as e:
        print(f"[drip] Check error: {e}")


async def _send_drip3(email: str, sessions_used: int):
    try:
        from email_handler import send_trial_day3_email
        await send_trial_day3_email(email, sessions_used)
    except Exception as e:
        print(f"[drip] Day3 send error: {e}")


async def _send_drip6(email: str):
    try:
        from email_handler import send_trial_day6_email
        await send_trial_day6_email(email)
    except Exception as e:
        print(f"[drip] Day6 send error: {e}")


async def _send_drip7(email: str):
    try:
        from email_handler import send_trial_expired_email
        await send_trial_expired_email(email)
    except Exception as e:
        print(f"[drip] Day7 send error: {e}")


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_drip_loop())
    print("[podpal] Drip email scheduler started")
