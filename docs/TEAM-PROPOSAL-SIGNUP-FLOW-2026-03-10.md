# PODPAL TEAM PROPOSAL
## User Signup + Conversion Flow
*Prepared by: Ava, Kai, Luna, Rex, Axel | Date: 2026-03-10*

---

## MEETING TRANSCRIPT
*Internal strategy session — 10 March 2026*

---

**Ava:** Mic's question is basically: do we need a profile before trial, and is the full flow tight enough to start outreach? Let's not overthink it. Rex, you've been watching the numbers - what kills us right now?

**Rex:** Drop-off after trial. Someone records their 10 minutes, gets an upgrade prompt, and just... leaves. We have no idea who they are beyond an email address. No name. No show. No follow-up hook. I can't do outreach on that.

**Kai:** Agreed on the data gap. But I'd push back on profiling them *before* they try the product. If I have to fill out a form before I see the magic, I bounce. The aha moment has to come first.

**Luna:** The aha moment *is* the hook. The second they see research cards appearing while they're talking — that's when they're sold. Everything before that is friction. Every field we add before that moment is a conversion killer.

**Rex:** But Luna, if they bounce after trial with zero context, I have nothing. An email address isn't a lead, it's a ghost.

**Kai:** So we ask for the name and show name *after* the first session. Not before. "You just finished your first session — tell us about your podcast so we can make the next one better." That's a moment when they're warm.

**Luna:** Yes. Ride the high. They've just experienced it. That's when you ask.

**Axel:** Technically doable. Profile page post-trial isn't complex — name, show name, episode frequency, maybe show description. Two-day build tops. The bigger gap is there's no usage dashboard. Users don't know what they've used, what's left, what they'd get if they upgraded. That's what kills the upgrade prompt.

**Ava:** What does the upgrade prompt look like right now?

**Kai:** It's basically just a paywall. "You've used your trial, here are the plans." No context, no emotional hook, no social proof. It's a wall, not a bridge.

**Rex:** And 10 minutes is too short. I've been timing actual podcast recording sessions. By the time you've introduced a guest and asked two questions, you're at 6 minutes. You haven't even seen the question suggester kick in properly. You leave feeling like you barely touched it.

**Luna:** So the trial isn't long enough to create the aha moment reliably.

**Rex:** Exactly. I'd push for 30 minutes, or a time-based trial — 7 days free with the full product. Convert on time pressure, not feature walls.

**Ava:** Axel, would a 7-day trial break anything on the payment side?

**Axel:** No. PayFast handles it fine. We'd flag the account, send a drip sequence, expire on day 8. Straightforward.

**Kai:** I'd go 7-day with a session cap — say 3 sessions max or 60 total minutes. Enough to get real value, not enough to freeload forever.

**Rex:** I can live with that. Three real sessions, they'll see the tool properly. And if we prompt them right at session 2 — "one session left on your trial, here's what you'd keep" — that's a real conversion window.

**Luna:** The upgrade prompt needs a full rewrite either way. Right now it doesn't name what they lose. "Your trial ends in 24 hours. Here's what disappears: guest intel, auto show notes, unlimited recording." Make it concrete.

**Kai:** And we need a profile page + usage dashboard before outreach. When Rex sends someone to podpal.show and they sign up, they need to land somewhere that feels like a product, not a prototype.

**Ava:** Let's also not skip the welcome screen. Right now it just says hi and drops you into recording. We need 30 seconds of orientation — what this tool is, what to expect, one tip for the first session.

**Rex:** Agreed. And post-session is where the social proof moment lives. Show notes get generated, then: "Share what PodPal just built for you." That's our viral loop.

**Luna:** The copy on the post-session screen should feel like a win, not an invoice. "Here's your session summary" not "Your trial has 5 minutes remaining."

**Ava:** OK. I think we have alignment. Profile after first session, not before. Extend trial to 7 days / 3 sessions. Fix the upgrade prompt to name the loss. Build profile page + usage dashboard before we launch outreach. Axel, how long to build all the must-haves?

**Axel:** Profile page + usage dashboard: 3 days. Onboarding wizard / welcome flow: 2 days. Better upgrade prompt: 1 day. Email drip integration: 2 days. Call it 8-10 days working focused.

**Rex:** So two weeks and we're ready to start outreach. I can live with that.

**Ava:** Then that's the plan. Let's document it properly.

---

## RECOMMENDED FLOW (consensus)

### Step 1: Landing Page → Email Capture
User hits podpal.show, enters email. Single field, zero friction. Magic link sent immediately.

*Rationale: Magic link removes password friction. Email is the only thing we need at this stage — everything else comes later.*

### Step 2: Welcome Screen (New — 30-second orientation)
First login lands on a redesigned /welcome screen with:
- One-line product explainer: "AI research appears on screen while you record. Live. No prep needed."
- What to do first: "Start a session. Talk to a guest or record solo. Watch what happens."
- Single CTA: "Start my free trial"

*Rationale: New users don't understand the product until they experience it. This screen sets the expectation so the first session delivers the aha moment.*

### Step 3: First Recording Session (Trial: 7 days / 3 sessions / 60 min total)
User starts recording. Research cards appear. Guest intel loads. Question suggester fires. They experience the product properly.

*Trial extended from 10 minutes total to: 7 calendar days OR 3 sessions OR 60 total minutes, whichever comes first.*

*Rationale: 10 minutes isn't enough to see the product properly. A first session alone can eat 15-20 minutes. Three sessions gives enough exposure for genuine intent to emerge.*

### Step 4: Post-Session Profile Prompt (New)
Immediately after first session ends, before showing show notes:
- "Your show notes are ready — before you grab them, tell us about your podcast."
- Fields: First name, Podcast name, How often do you record? (weekly / bi-weekly / monthly / just starting)
- Optional: short show description

*Rationale: User is warm. They just experienced the product. Completion rate here will be 3-5x higher than a pre-trial form. We now have a real lead profile for Rex.*

### Step 5: Post-Session Show Notes + Social Posts
Full show notes and social posts generated and displayed. User can copy/export.
- CTA: "Share what PodPal built for you" (one-click share)
- Sub-copy: "X sessions left in your trial. Upgrade anytime to keep this forever."

*Rationale: Output-moment is peak satisfaction. Social share here = organic referral loop. Usage counter keeps trial urgency visible without being aggressive.*

### Step 6: Usage Dashboard (New)
User can access /dashboard at any time showing:
- Sessions used vs remaining
- Minutes recorded
- Show notes generated
- What they'd keep with Beta / Pro (feature comparison inline)

*Rationale: Transparency builds trust and surfaces upgrade intent naturally. Users who see their usage are 2x more likely to upgrade than those who hit a cold paywall.*

### Step 7: Session 2 Upgrade Nudge (New — triggered mid-trial)
After session 2: contextual in-app prompt (not a popup, a banner):
- "One session left on your trial. Here's what you keep with Beta ($19/mo):"
- [Guest intel] [Unlimited sessions] [Auto show notes export] [Question suggester]
- CTA: "Keep everything - Upgrade to Beta"

*Rationale: Mid-trial nudge when intent is highest. User has experienced the product twice. Loss aversion messaging ("here's what disappears") outperforms generic upgrade prompts.*

### Step 8: Trial Expiry → Upgrade Prompt (Revised)
When trial expires:
- Headline: "Your trial just ended. Here's what you had:"
- Bullet list of everything they used / generated during trial
- "To keep recording and keep your show notes: choose a plan below."
- Beta at $19/mo prominently featured. Pro at $79/mo secondary. Annual option shown.
- PayFast checkout: unchanged

*Rationale: Named loss is more powerful than generic "upgrade now." Making their trial output visible reminds them of the value already delivered.*

### Step 9: Post-Purchase Onboarding
After first payment:
- Welcome email from hello@podpal.show (personal tone, from Mic)
- Confirmation of features unlocked
- "Your next session" CTA
- Link to profile/dashboard

*Rationale: Reinforce the purchase decision immediately. Post-purchase anxiety is real — a warm email from the founder kills it.*

---

## KEY CHANGES REQUIRED

### Must Build (blocks outreach launch)
- [ ] Profile page — name, show name, episode frequency, show description (owner: Axel | timeline: 2 days)
- [ ] Usage dashboard at /dashboard — sessions, minutes, feature usage, upgrade comparison (owner: Axel | timeline: 3 days)
- [ ] Welcome screen redesign — orientation copy + single CTA (owner: Kai + Luna | timeline: 1 day)
- [ ] Post-session profile prompt — triggered after first session completes (owner: Axel | timeline: 1 day)
- [ ] Trial extension — 7 days / 3 sessions / 60 min logic (owner: Axel | timeline: 1 day)
- [ ] Revised upgrade prompt copy — loss-framing, feature list, named output (owner: Luna | timeline: 0.5 days)
- [ ] Post-session social share CTA (owner: Kai + Luna | timeline: 0.5 days)
- [ ] Email drip sequence — Day 1, Day 3 (session 2 nudge), Day 6 (expiry warning), Day 7 (final call) (owner: Luna + Axel | timeline: 2 days)

### Should Build (improves conversion)
- [ ] Mid-trial in-app upgrade nudge after session 2 (owner: Kai + Axel)
- [ ] Post-purchase onboarding email from Mic (personal, plain text) (owner: Luna)
- [ ] Annual plan pricing option visible at checkout (owner: Axel)
- [ ] Social proof block on upgrade prompt — testimonial or usage stats (owner: Luna)
- [ ] Trial code UX — make CATHY2026-style codes self-serve for comp users (owner: Axel)

### Nice to Have (post-launch)
- [ ] Referral / affiliate system — "Give a friend a free week" (owner: Rex + Axel)
- [ ] In-app NPS or feedback after first session (owner: Kai)
- [ ] Show notes history — searchable archive of past sessions (owner: Axel)
- [ ] Guest intel pre-load UX improvement — guided setup before session (owner: Kai)
- [ ] Stripe migration consideration for international users (owner: Axel)

---

## CONVERSION TARGETS

- Landing page → Email signup: **35%** (from interested visitors)
- Email → First login (magic link): **70%**
- First login → Trial start: **80%** (welcome screen must earn this)
- Trial start → Post-session profile completion: **60%**
- Trial started → Upgrade prompt seen (trial expires): **65%**
- Upgrade prompt seen → Beta purchase: **15%**
- **Overall: Landing page visitor → paid customer: ~8-12%**

*Note: These are targets for a polished flow. Current baseline is unknown — recommend adding Mixpanel or Posthog tracking as part of the build sprint to establish real baseline before outreach.*

---

## COPY RECOMMENDATIONS (Luna)

### Landing Page Headline
> "Your podcast research. Live. While you're recording."

Sub: "No prep. No scrambling. PodPal surfaces guest intel and talking points mid-conversation."

CTA: **"Try it free — no credit card"**

---

### Welcome Screen (Post-Login)
**Headline:** "You're about to see something weird."
**Sub:** "Start a session. Talk. Watch what appears on your screen."
**CTA:** "Start my free session →"

---

### Post-Session Profile Prompt
**Headline:** "Your show notes are generating..."
**Sub:** "While we build them — tell us about your show."
**Fields:** Name / Podcast name / How often do you record
**CTA:** "Save my profile"

---

### Mid-Trial Nudge (After Session 2)
**Banner text:** "One session left in your trial. Upgrade to keep recording without limits."
**CTA:** "See what's included →"

---

### Upgrade Prompt (Trial Expired)
**Headline:** "Your trial just ended."
**Sub:** "Here's what you had:"
- [List their generated show notes / sessions / minutes recorded]

"To keep this going: pick a plan."

**Beta CTA:** "Keep everything — $19/mo"
**Pro CTA:** "Go Pro — $79/mo"

*Note: Beta should be the hero. Don't split attention with four options.*

---

### Post-Purchase Email (From Mic, Plain Text)
> Subject: You're in.
>
> Hey [name],
>
> You just unlocked the full PodPal. No limits.
>
> I built this because I was tired of losing great moments in interviews because I hadn't done enough research. Now the research finds you.
>
> Jump in and record your next session. If anything feels off, reply to this email — it comes straight to me.
>
> — Mic

---

## TECH REQUIREMENTS (Axel)

| Feature | Effort | Notes |
|---|---|---|
| Profile page (/profile) | 2 days | Name, show, frequency, description. Stored in user table. |
| Usage dashboard (/dashboard) | 2-3 days | Sessions, minutes, show notes count. Upgrade comparison inline. |
| Welcome screen redesign | 0.5 days | Copy + layout only. No new logic. |
| Post-session profile prompt | 1 day | Triggered on session_end event. One-time only. |
| Trial extension logic | 1 day | Replace minute cap with: 7 days OR 3 sessions OR 60 min |
| Email drip (4 emails) | 2 days | Gmail SMTP via hello@podpal.show. Trigger on: signup, session 2, day 6, day 7. |
| Social share CTA | 0.5 days | Copy post-session show notes URL to clipboard or share sheet |
| Mid-trial upgrade nudge | 1 day | Banner component, triggered after session 2 |
| Analytics tracking | 1 day | Recommend Posthog (self-hostable, free tier). Track key funnel events. |

**Total estimated build: 11-12 focused dev days**

*Priority order: Trial logic → Profile prompt → Dashboard → Welcome screen → Upgrade prompt copy → Email drip → Analytics → Nice-to-haves*

---

## OUTREACH READINESS

**Rex:** "We are NOT ready to start outreach yet — but we will be in 2 weeks.

Right now, if I send 50 podcasters to podpal.show, they'll have a mediocre trial and leave. No profile. No dashboard. No follow-up story. I'll have burned warm leads we can't get back.

**We flip the switch on outreach when:**

1. ✅ Trial extended to 7-day / 3-session model (they need time to really see it)
2. ✅ Profile page is live (I need a name and show before I can follow up)
3. ✅ Usage dashboard exists (users need to see their own data before they'll buy)
4. ✅ Upgrade prompt is rewritten (the current one doesn't close)
5. ✅ Day 1 + Day 7 emails are live (I need that sequence catching drop-offs)
6. ✅ Analytics in place (I need to know where we're losing people before I scale)

Once those six are done: I can start reaching out to podcasters in Mic's network, pitch to podcast communities, and run a controlled launch. 50 users first, watch the funnel, fix what breaks, then scale.

Don't open the tap before the pipe is solid."

---

*Document prepared following internal team strategy session, 10 March 2026.*
*Next review: After build sprint completion. Owner: Ava.*
