# PodPal - Product Requirements Document
**Version:** 0.1 | **Owner:** Mic Mann | **Date:** March 2026

---

## What Is PodPal

PodPal is a real-time AI co-pilot for podcasters. It listens to your live conversation, understands the context of who you are and what you talk about, and feeds you live research, stats, talking points, and fact-checks — on screen, as the conversation happens.

The podcaster gets a superpower. Their guest never knows it exists.

---

## The Problem

Podcasters fly blind in real time:
- A guest drops a statistic — is it accurate? No way to check without breaking flow
- A topic comes up you're not deep on — you can't Google mid-sentence
- A great follow-up question exists — you don't know it because you haven't read the paper
- You want to sound current — but research takes hours before each episode

The best podcast hosts (Rogan, Fridman, Conan) seem omniscient. They're not. They prep obsessively. PodPal gives every podcaster that same depth, live.

---

## The Solution

PodPal runs on a laptop screen beside the host (or a second monitor, or a tablet). It listens via microphone. It displays:

1. **Live Transcript Strip** — rolling last 30 seconds, so you can glance at what was just said
2. **Topic Detector** — "Currently discussing: climate tech / carbon markets"
3. **Live Research Panel** — real-time facts, stats, papers related to the current topic
4. **Talking Points** — 3 suggested follow-up questions or angles based on the conversation
5. **Fact Check Alert** — if a guest makes a specific claim, PodPal flags it with a confidence score
6. **Guest Intel** — quick-access profile of the current guest: key works, known positions, hot takes, controversies
7. **Host Memory** — knows what Mic has said on this topic before, avoids repetition

---

## User Flow

```
1. Pre-show setup (2 min)
   - Select episode profile (guest name, topic, format)
   - PodPal loads guest context + host context
   - Confirm mic input

2. Live session
   - PodPal listens continuously
   - Transcript appears in rolling strip
   - Research panel updates every 15-20 seconds as topics shift
   - Talking points refresh as conversation moves
   - Fact alerts pop when specific claims are made

3. Post-show
   - Full transcript saved
   - Key claims + fact-check log exported
   - Best moments flagged (high-engagement topic shifts)
   - Clip suggestions for social
```

---

## Technical Architecture

### Audio Pipeline
```
Mic Input → Web Audio API → Chunked Audio Buffer (3-5s chunks)
         → Deepgram Streaming API (real-time transcription, <500ms latency)
         → Rolling Transcript Buffer (last 120 seconds)
```

**Why Deepgram over Whisper:** Deepgram Nova-2 has ~200-300ms latency for streaming vs Whisper's batch-only model. Real-time requires streaming.

### Intelligence Pipeline
```
Transcript Buffer → Topic Extractor (Claude Haiku, every 10s)
                 → Research Trigger (if new topic detected)
                 → Web Search (Perplexity API or Brave Search)
                 → Fact Synthesiser (Claude Sonnet)
                 → WebSocket Push → Frontend Display
```

### Host Knowledge Base
```
Onboarding → Podcaster fills profile (name, show, topics, past episodes)
           → Past episode transcripts ingested (optional)
           → Guest database built over time
           → Vector store (ChromaDB or pgvector) for semantic search
```

### Frontend
- React web app (runs locally or in browser)
- Two layout modes: full-screen second monitor / sidebar overlay
- Dark mode by default (studio-friendly)
- Minimal UI - designed to be glanced at, not stared at
- WebSocket connection to backend for live updates

### Backend
- Python FastAPI
- WebSocket server for real-time push
- Deepgram streaming client
- Research orchestrator (search + synthesise)
- Host profile store (SQLite for MVP, Postgres later)

---

## AI Company Structure (Autonomous Agents)

PodPal runs as an autonomous AI company. Each agent has a defined role, runs on a cron schedule, and reports to the CEO agent.

### CEO Agent (Strategic)
- Reviews weekly metrics (signups, churn, revenue, feature requests)
- Sets priorities for the week
- Allocates "budget" (API spend) across agents
- Escalates to Mic when human decision needed
- Runs: weekly Monday 8am

### Product Agent
- Monitors GitHub issues and user feedback
- Prioritises backlog
- Writes feature specs for Dev agent
- Tracks release progress
- Runs: daily 9am

### Dev Agent
- Builds features from Product specs
- Fixes bugs from error logs
- Writes and runs tests
- Opens PRs for review
- Runs: triggered by Product agent

### Marketing Agent
- Writes weekly social content (X, LinkedIn, TikTok)
- Drafts podcast outreach emails (meta: uses PodPal to sell PodPal to podcasters)
- Tracks content performance
- Runs: daily 10am

### Sales Agent
- Scrapes podcast directories for prospects (Spotify, Apple Podcasts, RSS)
- Builds lead database (show name, host, email, episode count, topic category)
- Sends personalised outreach (email + LinkedIn)
- Tracks pipeline: contacted → demo booked → trial → paid
- Runs: daily 11am

### Finance Agent
- Tracks revenue, MRR, churn daily
- Monitors API costs (Deepgram, Claude, Perplexity)
- Alerts if burn rate exceeds threshold
- Prepares weekly P&L summary for CEO agent
- Runs: daily 8am

### Support Agent
- Monitors email/Telegram for user issues
- Resolves tier-1 problems autonomously
- Escalates tier-2 to Mic
- Tracks CSAT
- Runs: hourly during business hours

---

## MVP Scope (Week 1)

Build the core experience first. Everything else can wait.

**MVP = The Magic Moment:**
- Mic speaks into a mic
- PodPal transcribes in real time
- A topic is detected
- Research appears on screen within 5 seconds
- Mic says "wow, that actually works"

**MVP features:**
- [x] Real-time audio transcription (Deepgram)
- [x] Topic detection every 10 seconds (Claude Haiku)
- [x] Research fetch on topic change (Brave/Perplexity search)
- [x] Live display (React, WebSocket)
- [x] Basic host profile (name, show, topics)
- [ ] Guest profile pre-load
- [ ] Fact-check alerts
- [ ] Talking points panel
- [ ] Post-show export

**Not in MVP:**
- Mobile app
- Multi-host support
- Recording/editing features
- Payment/billing
- AI company agents (Phase 2)

---

## Pricing (Proposed)

| Tier | Price | Includes |
|------|-------|---------|
| Solo | $29/month | 1 show, 10 hours/month live |
| Pro | $79/month | 3 shows, unlimited hours, guest DB |
| Studio | $199/month | 10 shows, team access, priority support |

**Unit economics (Pro tier):**
- Deepgram: ~$0.0059/min = ~$3.54/hour → 40 hours/month = ~$142/month
- Claude API: ~$10/month at typical usage
- Server: ~$20/month
- Total COGS: ~$172/month
- Revenue: $79/month
- **Note:** Need to optimise Deepgram usage or price higher for Pro

---

## Go-to-Market

The product sells itself — demo it live on a podcast. 

1. Mic uses PodPal on his own podcast first (dogfood)
2. Share a clip of the live research panel in action (social)
3. Offer free beta to 10 South African podcasters
4. Sales agent builds pipeline from podcast directories
5. Launch publicly with waitlist

---

## Competitive Landscape

- **Castmagic** — post-production AI, not real-time
- **Descript** — editing, not real-time assistance
- **Otter.ai** — transcription only
- **No direct real-time research competitor exists yet**

This is a genuine gap. The "live research during podcast" use case is unsolved.

---

## Success Metrics

| Metric | Week 4 Target | Month 3 Target |
|--------|--------------|----------------|
| Beta users | 10 | 50 |
| Paying users | 0 | 15 |
| MRR | $0 | $750 |
| Avg session length | - | 45 min |
| Research accuracy | - | >85% |
