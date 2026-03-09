#!/usr/bin/env python3
"""
PodPal Backend - Real-time podcast AI co-pilot
FastAPI + WebSocket server that streams transcription, topic detection, and research
"""

import asyncio
import json
import os
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
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="PodPal", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Config
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# In-memory state (per session)
sessions: dict[str, "PodSession"] = {}


class PodSession:
    def __init__(self, session_id: str, host_profile: dict):
        self.session_id = session_id
        self.host_profile = host_profile
        self.transcript_buffer = deque(maxlen=200)  # last ~120 seconds of words
        self.full_transcript = []
        self.current_topic = ""
        self.last_research_at = 0
        self.last_transcript_text = ""
        self.research_cooldown = 15  # seconds between research triggers
        self.clients: list[WebSocket] = []

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
        # Extract JSON
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

    # Try Perplexity first (best for real-time research)
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

    # Fallback: Brave Search
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
                    # Synthesise with Claude
                    synth = await claude.messages.create(
                        model="claude-haiku-4-5",
                        max_tokens=250,
                        messages=[{"role": "user", "content": f"Summarise these search results about '{query}' into 3 key bullet points with specific facts/stats:\n\n" + "\n".join(snippets)}]
                    )
                    results["research"] = synth.content[0].text
                    results["source"] = "Web Search"
        except Exception as e:
            print(f"Brave search error: {e}")

    # Fallback: Claude knowledge
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
                # Incoming transcript words from Deepgram (via frontend)
                words = data.get("words", [])
                text = data.get("text", "")
                session.add_transcript(words)

                await session.broadcast({
                    "type": "transcript_update",
                    "text": text,
                    "timestamp": time.time()
                })

                # Check if we should run topic detection + research
                now = time.time()
                recent_text = session.get_recent_text()

                if (now - session.last_research_at) >= session.research_cooldown and recent_text != session.last_transcript_text:
                    session.last_transcript_text = recent_text
                    session.last_research_at = now

                    # Run in background to not block
                    asyncio.create_task(run_intelligence(session, recent_text))

            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if websocket in session.clients:
            session.clients.remove(websocket)


async def run_intelligence(session: PodSession, recent_text: str):
    """Run topic detection + research in background."""
    try:
        # Detect topic
        topic_data = await detect_topic(
            recent_text,
            session.host_profile,
            session.current_topic
        )

        topic = topic_data.get("topic", session.current_topic)
        changed = topic_data.get("changed", False)
        entities = topic_data.get("entities", [])
        questions = topic_data.get("suggested_questions", [])
        fact_checks = topic_data.get("fact_check", [])

        # Always send topic update
        await session.broadcast({
            "type": "topic_update",
            "topic": topic,
            "changed": changed,
            "suggested_questions": questions,
            "fact_checks": fact_checks,
            "timestamp": time.time()
        })

        # Fetch research if topic changed or first run
        if changed or not session.current_topic:
            session.current_topic = topic
            research = await fetch_research(topic, entities, session.host_profile)
            await session.broadcast({
                "type": "research_update",
                "topic": topic,
                "research": research.get("research", ""),
                "source": research.get("source", ""),
                "timestamp": time.time()
            })
        elif fact_checks:
            # Fact-check specific claims even without topic change
            for claim in fact_checks[:2]:
                research = await fetch_research(claim, [], session.host_profile)
                await session.broadcast({
                    "type": "fact_check",
                    "claim": claim,
                    "result": research.get("research", ""),
                    "source": research.get("source", ""),
                    "timestamp": time.time()
                })

    except Exception as e:
        print(f"Intelligence error: {e}")


@app.post("/session/create")
async def create_session(payload: dict):
    """Create a new PodPal session."""
    session_id = f"session_{int(time.time())}"
    host_profile = payload.get("host_profile", {})
    sessions[session_id] = PodSession(session_id, host_profile)
    return {
        "session_id": session_id,
        "status": "created",
        "deepgram_key": DEEPGRAM_API_KEY[:8] + "..." if DEEPGRAM_API_KEY else "NOT SET"
    }


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


@app.post("/api/waitlist")
async def join_waitlist(payload: dict):
    """Save waitlist signups."""
    import json
    from pathlib import Path
    wl_file = Path(__file__).parent.parent / "data" / "waitlist.json"
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
    from pathlib import Path
    import json
    wl_file = Path(__file__).parent.parent / "data" / "waitlist.json"
    entries = json.loads(wl_file.read_text()) if wl_file.exists() else []
    return {"count": len(entries)}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve landing page at root, app at /app
landing_dir = Path(__file__).parent.parent / "landing"
frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"


@app.get("/app")
@app.get("/app/")
async def serve_app():
    from fastapi.responses import HTMLResponse
    app_html = frontend_dir / "index.html"
    return HTMLResponse(content=app_html.read_text())


if landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(landing_dir), html=True), name="landing")
