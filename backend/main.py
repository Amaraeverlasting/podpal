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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="PodPal", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Config
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Data directories
BASE_DIR = Path(__file__).parent.parent
SESSIONS_DIR = BASE_DIR / "data" / "sessions"
GUESTS_DIR = BASE_DIR / "data" / "guests"
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

    if not results.get("research") and BRAVE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": BRAVE_API_KEY},
                    params={"q": query, "count": 5, "freshness": "pw"}
                )
                data = resp.json()
                snippets = [r.get("description", "") for r in data.get("web", {}).get("results", [])[:3]]
                if snippets:
                    synth = await claude.messages.create(
                        model="claude-haiku-4-5",
                        max_tokens=250,
                        messages=[{"role": "user", "content": f"Summarise these search results about '{query}' into 3 key bullet points with specific facts/stats:\n\n" + "\n".join(snippets)}]
                    )
                    results["research"] = synth.content[0].text
                    results["source"] = "Web Search"
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
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "transcript":
                words = data.get("words", [])
                text = data.get("text", "")
                session.add_transcript(words)

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

            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if websocket in session.clients:
            session.clients.remove(websocket)


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


# ── Session endpoints ────────────────────────────────────────────────────────

@app.post("/session/create")
async def create_session(payload: dict):
    session_id = f"session_{int(time.time())}"
    host_profile = payload.get("host_profile", {})
    sessions[session_id] = PodSession(session_id, host_profile)
    return {
        "session_id": session_id,
        "status": "created",
        "deepgram_key": DEEPGRAM_API_KEY[:8] + "..." if DEEPGRAM_API_KEY else "NOT SET"
    }


@app.post("/session/{session_id}/save")
async def save_session(session_id: str):
    """Save session data to disk."""
    if session_id not in sessions:
        return {"error": "Not found"}
    fpath = sessions[session_id].save_to_disk()
    return {"ok": True, "file": fpath.name}


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
async def export_session(session_id: str):
    """Export session as show notes markdown."""
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
async def list_sessions():
    """List all saved sessions from disk."""
    files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)
    result = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            result.append({
                "file": f.name,
                "session_id": data.get("session_id", ""),
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
async def guest_intel(payload: dict):
    """Research a guest and return a structured brief."""
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
    return {"ok": True, "position": len(entries)}


@app.get("/api/waitlist/count")
async def waitlist_count():
    wl_file = BASE_DIR / "data" / "waitlist.json"
    entries = json.loads(wl_file.read_text()) if wl_file.exists() else []
    return {"count": len(entries)}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


# ── Static serving ───────────────────────────────────────────────────────────

frontend_dir = BASE_DIR / "frontend" / "dist"
landing_dir = BASE_DIR / "landing"


@app.get("/app")
@app.get("/app/")
async def serve_app():
    app_html = frontend_dir / "index.html"
    return HTMLResponse(content=app_html.read_text())


@app.get("/history")
@app.get("/history/")
async def serve_history():
    hist_html = frontend_dir / "history.html"
    if hist_html.exists():
        return HTMLResponse(content=hist_html.read_text())
    return HTMLResponse("<h1>History page not found</h1>", status_code=404)


if landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(landing_dir), html=True), name="landing")
