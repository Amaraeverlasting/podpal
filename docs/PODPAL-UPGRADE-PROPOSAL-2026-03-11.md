# PodPal Upgrade Proposal
**Date:** Wed 11 March 2026
**Prepared by:** Ava (CEO), Kai (CPO), Luna (CMO), Rex (CSO), Axel (CTO)

---

## Product State Summary (what we read)

The codebase is solid for a v0.3 product. Core loop works: magic link auth, WebSocket transcription via Deepgram, Claude Haiku for topic detection, Brave Search for live research, session save to disk, post-session content generation. Tiers are live (Beta $19, Pro $79). Trial codes system is functional. PayFast integration is in. Analytics middleware exists.

**Current gaps, in plain terms:**
- No session history UI - sessions are saved to disk but the dashboard doesn't render them
- Guest research is loaded by name but there's no pre-session prep screen
- Transcript panel is passive (read-only bottom strip) - no clip/bookmark actions
- Dashboard shows "Loading..." state but session list is rendering from `/api/dashboard`
- No way to resume or re-view a previous session's generated content
- Landing page pricing section exists but no trial code entry at signup

---

## Executive Summary (Ava - CEO)

**90-day vision:** PodPal becomes the tool podcasters open for every episode - not just sometimes, but as a habit. The shift from "interesting tool" to "I can't record without it" happens when three things are true: it works before, during, AND after every session with zero friction; the post-session content saves measurable time; and sharing a session summary becomes something hosts actually do.

**Top 3 bets for 90 days:**

1. **Session library** - hosts need to see their history, re-access show notes, and copy content. Right now sessions are saved to disk but invisible in the UI. This is table stakes for daily use.

2. **Pre-session prep mode** - a structured screen between "type guest name" and "hit space to record" that shows loaded guest intel, confirms the setup, and optionally lets the host add their own talking points. Reduces the cold-start anxiety of opening the app.

3. **One-click share** - after a session, the show notes + social posts should be shareable via a link or exportable to a Notion/Google Doc. Right now it's export as .md only. Lowering the friction from "content generated" to "content published" is where the $79/mo Pro tier justifies itself.

---

## UI/UX Improvements (Kai - CPO)

### index.html (main app)

**1. Transcript strip - add clip button that actually works**
Current state: The transcript strip at the bottom has `grid-row: 2; grid-column: 1 / -1` and shows live text. The `.mock-clip-btn` on the landing page shows a "Clip" button but the actual app has no clip functionality.
Change: Add a `✂ Clip` button inside `#transcript-panel .panel-header`. On click, save the last 30 seconds of transcript text to a `clips[]` array and show a toast. At session end, include clips in the generated content.
Why: Hosts catch key moments as they happen. This is the one feature that makes the app feel smart.

**2. Research panel - add source attribution**
Current state: Research content loads but there's no visible source URL or timestamp.
Change: Add a `<div class="research-source-tag">` below each research block showing domain + time (e.g. "via brave.com · 2 min ago"). Already styled in the CSS as `.research-source-tag` - just not being populated from the WebSocket event.
Why: Hosts want to reference sources. Fact-checking credibility depends on it.

**3. Questions panel - done/dismissed state**
Current state: Talking points stack up with no way to mark them used. `.point-item` has hover opacity but no click action beyond... nothing.
Change: On click, add class `used` to `.point-item`. CSS: `opacity: 0.35; text-decoration: line-through`. Move used items to bottom of list.
Why: Mid-interview, the host needs to track what's been covered without looking away from the guest.

**4. Header - add session timer**
Current state: The header shows logo, status dot, topic badge, and some buttons. No timer.
Change: Add `<span id="session-timer" class="status-label">00:00</span>` next to the status label. Start counting when WebSocket connects and status goes live.
Why: Hosts need to know how long they've been recording. Especially for episode pacing.

**5. Trial bar - make the upgrade CTA clearer**
Current state: `#trial-upgrade-link` says "Upgrade" with no context.
Change: Change text to "Upgrade - R190/mo" (or current pricing). Add a seconds-remaining counter inline: "14 min left - Upgrade".
Why: Urgency without being annoying. Hosts on trial don't know the price until they click.

### dashboard.html

**1. Session list is empty for most users**
Current state: The session list renders via JS from `/api/dashboard` but if there are no sessions, it shows `.empty` with "No sessions yet." There's no call to action.
Change: Replace the empty state with:
```html
<div class="empty">
  <div style="font-size:32px;margin-bottom:12px;">🎙️</div>
  <p style="margin-bottom:16px;">No sessions yet. Start your first episode.</p>
  <a href="/app" class="upgrade-cta">Open PodPal</a>
</div>
```
Why: First-time users land on dashboard after welcome and see nothing. This is a dead end.

**2. Stats row - show meaningful numbers sooner**
Current state: Stats row shows 4 cards but new users see 0/0/0/0. Makes the product feel empty.
Change: For users with 0 sessions, replace stat values with motivational copy: "Your first session will appear here." Or just hide the stat row entirely until session count > 0.

**3. Quick actions - add "View Last Session"**
Current state: Quick actions has "New Session", "Profile", and "Upgrade". 
Change: If `sessions.length > 0`, add a fourth quick action: "View Last Session" linking to `/session/{last_session_id}`.
Why: Returning users want to get back to their content fast.

### welcome.html

**1. Trial box copy - too passive**
Current state: The `.trial-box` says (presumably) "You have a 7-day free trial."
Change: Make it specific and time-aware: "Your trial runs until [date]. That's [X] full episodes worth of AI co-pilot time."
Why: Abstract "7 days" means nothing. A deadline date creates real urgency.

**2. Missing trial code entry**
Current state: No way to enter a trial code on the welcome screen.
Change: Add a small link below `.ctas`: `<a href="#" onclick="showCodeEntry()">Have a promo code?</a>`. On click, show an inline input that calls `POST /api/redeem-trial-code`.
Why: We're handing out codes (GARETH2026, PHIL2026, etc.) but there's no user-facing entry point on this screen. Users who got a code have to find `/redeem` on their own.

---

## New Features Shortlist (Kai + Axel)

Ranked by impact/effort ratio (high impact, low effort first):

| # | Feature | Description | Impact | Effort |
|---|---------|-------------|--------|--------|
| 1 | Session viewer page | `/session/{id}` - view show notes, social posts, transcript clips for any past session | High | Low |
| 2 | Clip button (live) | Mark transcript moments mid-session; surface in post-session content | High | Low |
| 3 | Pre-session prep screen | Dedicated screen showing loaded guest intel before recording starts | High | Medium |
| 4 | Trial code entry on welcome | Input field for promo codes on welcome.html | High | Low |
| 5 | Copy-to-clipboard for social posts | One-click copy for each of the 3 generated social posts | Medium | Low |
| 6 | Session timer in app header | Elapsed time display during recording | Medium | Low |
| 7 | Guest notes field | Let host add their own talking points before recording | Medium | Medium |
| 8 | Email session summary | Auto-email show notes + social posts to host after session ends | High | Medium |
| 9 | Notion export | Push session content to a Notion page via API | High | Medium |
| 10 | Guest research cache | Save guest profiles locally so repeat guests load instantly | Medium | Medium |
| 11 | Mobile-responsive app | index.html is desktop-only; some hosts use tablets | Low | High |
| 12 | Multi-mic support | Select audio input device before recording (Rode, Focusrite, etc.) | Medium | Medium |
| 13 | Webhook on session end | POST to Zapier/Make when session ends - enables automation | High | Low |
| 14 | Episode series / show tags | Group sessions by show name for multi-podcast hosts | Low | Medium |

---

## Conversion Improvements (Luna + Rex)

### Landing page copy changes (landing/index.html)

**Hero h1 - current:** Something like "The AI Co-Pilot for Live Podcasts"
**Proposed:** "Your second screen during every podcast." 
Why: More concrete. "AI Co-Pilot" is abstract. "Second screen" is how hosts actually describe the use case.

**Hero sub - current:** Describes what PodPal does functionally.
**Proposed:** Add social proof number early. Example: "Used by [X] podcasters to skip 3 hours of post-production per episode."
Why: Specificity converts. "Used by podcasters" is vague. A number (even small) is real.

**The nav CTA - current:** "Start Free Trial" (assumed)
**Proposed:** Keep CTA but add the trial length prominently: "Try free - 7 days, no card"
Why: "No credit card" is the #1 objection killer for SaaS. It's not in the nav CTA right now.

**Pricing section:** Add a comparison line under each tier.
- Beta: "Good for one show, getting started"
- Pro: "For full-time podcasters and agencies"
Why: People don't know which tier to pick. One line of context removes friction.

**Add a trial code input to the pricing section:**
Below the Beta tier card, add: `<div class="code-entry">Have a promo code? <input placeholder="Enter code"> <button>Apply</button></div>`
Why: Promo codes are a growth lever we're not activating from the landing page.

### Onboarding flow tweaks

**Current flow:** Landing -> Sign up -> Magic link email -> welcome.html -> /app

**Proposed changes:**
1. welcome.html needs to ask "What's your podcast called?" and "Who are you recording with this week?" - storing this in the user profile so the first session doesn't start cold.
2. After magic link clicks, redirect to welcome.html with `?new=1` param. On `?new=1`, show a 3-step mini-onboarding (30 seconds total). Skip it on return visits.
3. welcome.html should show a visual of the app on the right side for desktop users. Currently it's a centered column with no screenshot. First-timers don't know what they're about to see.

### A/B test ideas

| Test | Variant A (current) | Variant B (proposed) | Metric |
|------|---------------------|----------------------|--------|
| Hero CTA | "Start Free Trial" | "Try it on your next episode" | Click-through to signup |
| Trial length | 7 days | 14 days for email subscribers | Trial-to-paid rate |
| Pricing page | Monthly only | Monthly + "Pay yearly, 2 months free" | Revenue per signup |
| Welcome screen | Text-only bullets | Short 30-second demo video | Session starts within 24h |
| Post-session email | None (not built) | Auto-email with show notes | Retention at day 7 |

---

## Technical Improvements (Axel - CTO)

**1. Session viewer endpoint missing**
Sessions save to disk in `SESSIONS_DIR` but there's no `/session/{id}` route in main.py. The dashboard has a `.btn-view` button in the HTML but it's not wired to anything. This is a blocker for session history being useful.
Fix: Add `GET /session/{session_id}` that reads the JSON file and renders a static page, or `GET /api/session/{session_id}` that returns JSON for a client-side rendered page.

**2. WebSocket error handling on client side**
index.html has WebSocket connection code but if the connection drops mid-session, there's no auto-reconnect logic. Hosts would see the live panels freeze with no indication.
Fix: Add reconnect logic with exponential backoff (3 attempts, 1s/2s/4s delays). Show a "Reconnecting..." state in the status dot.

**3. In-memory sessions - no crash recovery**
`sessions: dict[str, PodSession]` lives in memory only. If the server restarts mid-session, the session is gone. The transcript buffer (deque maxlen=200) is also in-memory.
Fix: Periodic snapshot of active session state to disk (every 60 seconds). On startup, check for incomplete sessions and offer recovery.

**4. Deepgram API key validation**
`_is_valid_key()` checks for SecretRef patterns but the WebSocket handler will still crash if Deepgram key is invalid - just later, with a less clear error.
Fix: Add a `/api/health` endpoint that checks all API keys on startup and returns their status. Surface this in the admin panel.

**5. Claude model pinning**
main.py uses `claude-haiku-4-5` hardcoded in `detect_topic()`. Model names change.
Fix: Move to an env var `CLAUDE_FAST_MODEL=claude-haiku-4-5` so it's easy to update without a code change.

**6. CORS - `allow_origins=["*"]`**
Currently open to all origins. Fine for beta, not for production.
Fix: Add `ALLOWED_ORIGINS` env var, default to `["https://podpal.show"]` in production.

**7. No rate limiting on WebSocket upgrades**
Any client can open a WebSocket session without auth check (or with a weak one). Under load this could be exploited.
Fix: Validate the user token before upgrading the WebSocket connection. Reject unauthenticated upgrades.

**8. analytics.py - check what's actually being tracked**
The `PageViewMiddleware` calls `_analytics.page_view()` but it's unclear if the data is being queried anywhere meaningful in the admin panel.
Fix: Ensure `/admin` surfaces the top 5 pages by view count and daily active users. If analytics data isn't being used, it's just overhead.

---

## Build Priority Matrix

| Feature | Impact | Effort | Revenue Impact | Build This Week? |
|---------|--------|--------|----------------|-----------------|
| Session viewer page `/session/{id}` | High | Low | Medium - reduces churn | YES |
| Trial code entry on welcome.html | High | Low | High - activates outreach codes | YES |
| Clip button in transcript panel | High | Low | Medium - stickiness | YES |
| Pre-session prep screen | High | Medium | High - reduces bounce | YES |
| Session timer in app header | Medium | Low | Low | YES |
| Copy-to-clipboard social posts | Medium | Low | Medium | YES |
| Auto-reconnect WebSocket | High | Medium | High - reliability | YES |
| Email session summary | High | Medium | High - retention | Next week |
| Notion export | Medium | Medium | Medium - Pro feature | Next week |
| Guest notes field | Medium | Medium | Low | Next week |
| Mobile responsive | Low | High | Low | Later |
| Multi-mic device selection | Medium | Medium | Low | Later |
| Webhook on session end | High | Low | High - power users | Next week |
| Yearly pricing option | High | Low | High - revenue | Next week |

---

## Today's Build Plan (Wed 11 March 2026)

Realistic for one focused day. In priority order:

### 1. Trial code entry on welcome.html (30 min)
**File:** `/Users/mannai/.openclaw/workspace/podpal/frontend/dist/welcome.html`
Add below `.ctas` div:
```html
<div style="margin-top:8px;text-align:center;">
  <a href="#" onclick="document.getElementById('code-box').style.display='block';this.style.display='none'" 
     style="font-size:12px;color:var(--muted);text-decoration:underline;cursor:pointer;">
    Have a promo code?
  </a>
  <div id="code-box" style="display:none;margin-top:12px;display:flex;gap:8px;">
    <input id="code-input" placeholder="Enter code" 
      style="flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;color:var(--text);font-size:14px;outline:none;" />
    <button onclick="redeemCode()" 
      style="background:var(--accent);color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer;">
      Apply
    </button>
  </div>
  <div id="code-msg" style="font-size:12px;margin-top:8px;"></div>
</div>
```
Add JS:
```js
async function redeemCode() {
  const code = document.getElementById('code-input').value.trim().toUpperCase();
  const msg = document.getElementById('code-msg');
  if (!code) return;
  const r = await fetch('/api/redeem-trial-code', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({code})
  });
  const d = await r.json();
  if (r.ok) {
    msg.style.color = 'var(--accent2)';
    msg.textContent = d.message || 'Code applied!';
    setTimeout(() => window.location.reload(), 1500);
  } else {
    msg.style.color = '#ff5c5c';
    msg.textContent = d.detail || 'Invalid code.';
  }
}
```

### 2. Session viewer page (2-3 hours)
**New file:** `/Users/mannai/.openclaw/workspace/podpal/frontend/dist/session.html`
**New backend route in main.py:** `GET /session/{session_id}` (serve session.html) + `GET /api/session/{session_id}` (return JSON from sessions dir)

The session viewer shows: guest name + date, duration, topics detected, talking points used, research cards, show notes, 3 social posts with copy buttons, and the transcript snippets. Use the existing dark theme CSS variables.

### 3. Clip button in transcript panel (45 min)
**File:** `/Users/mannai/.openclaw/workspace/podpal/frontend/dist/index.html`

In `#transcript-panel .panel-header`, add:
```html
<button id="clip-btn" class="btn btn-outline" onclick="clipNow()" style="font-size:11px;">✂ Clip</button>
```

Add JS:
```js
const clips = [];
function clipNow() {
  const text = document.getElementById('transcript-text').textContent.trim();
  if (!text) return;
  const last = text.split(' ').slice(-50).join(' ');
  clips.push({ time: new Date().toISOString(), text: last });
  showToast('Clipped!');
}
```
Pass `clips` array to the session end payload (add to the `POST /api/session/end` body or equivalent).

### 4. Session timer in app header (20 min)
**File:** `/Users/mannai/.openclaw/workspace/podpal/frontend/dist/index.html`

In the header, after `.status-label`, add:
```html
<span id="session-timer" style="font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;display:none;">00:00</span>
```

In JS, when the session goes live (WebSocket `type: "status"` with `status: "live"`):
```js
let timerStart = null, timerInterval = null;
function startTimer() {
  timerStart = Date.now();
  document.getElementById('session-timer').style.display = 'inline';
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - timerStart) / 1000);
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    document.getElementById('session-timer').textContent = `${m}:${sec}`;
  }, 1000);
}
```

### 5. Talking points "done" state (20 min)
**File:** `/Users/mannai/.openclaw/workspace/podpal/frontend/dist/index.html`

Add CSS:
```css
.point-item.used { opacity: 0.3; }
.point-item.used .point-text { text-decoration: line-through; }
```

Add JS to the existing `point-item` click handler (or create one):
```js
document.getElementById('questions-list').addEventListener('click', e => {
  const item = e.target.closest('.point-item');
  if (!item) return;
  item.classList.toggle('used');
  // Move used items to bottom
  const parent = item.parentNode;
  if (item.classList.contains('used')) parent.appendChild(item);
});
```

---

**End of proposal. 5 items. All shippable today.**
