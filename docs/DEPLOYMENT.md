# PodPal Deployment Guide
## Domain: podpal.show

---

## Step 1: Register podpal.show
- Register at namecheap.com
- Cost: ~$20-30/year

---

## Step 2: Deploy to Railway
1. Go to railway.app → New Project → Deploy from GitHub
2. Select: `Amaraeverlasting/podpal`
3. Railway auto-detects Dockerfile
4. Add environment variables:
   - `ANTHROPIC_API_KEY` = your Anthropic key
   - `BRAVE_API_KEY` = your Brave Search key (optional)
   - `PORT` = 8765 (Railway sets this automatically)
5. Deploy → Railway gives you a URL like `podpal-production.up.railway.app`

---

## Step 3: Connect podpal.show to Railway

### In Railway dashboard:
1. Go to your service → Settings → Domains
2. Click "Add Custom Domain"
3. Enter: `podpal.show`
4. Enter: `app.podpal.show`
5. Railway shows you CNAME values to add

### In Namecheap DNS (Advanced DNS tab):
Add these records:

| Type  | Host | Value                              |
|-------|------|------------------------------------|
| CNAME | @    | podpal-production.up.railway.app   |
| CNAME | app  | podpal-production.up.railway.app   |
| CNAME | www  | podpal-production.up.railway.app   |

DNS propagates in 5-30 minutes.

---

## Step 4: Routing (already configured in main.py)
- `podpal.show` → landing page
- `podpal.show/app` → live PodPal tool
- `podpal.show/history` → session history
- `podpal.show/api/*` → backend API
- `podpal.show/health` → health check

---

## Step 5: Verify
- `curl https://podpal.show/health` → should return `{"status":"ok"}`
- Open `https://podpal.show` → landing page
- Open `https://podpal.show/app` → PodPal app (mic works on HTTPS!)

---

## Environment Variables Reference
| Variable | Required | Description |
|----------|----------|-------------|
| ANTHROPIC_API_KEY | Yes | Claude API for topic detection + research |
| BRAVE_API_KEY | No | Brave Search for guest intel (Claude fallback if missing) |
| PORT | Auto | Set by Railway automatically |

---

## Updating the deployment
Just push to GitHub main branch - Railway auto-deploys.
```bash
cd ~/.openclaw/workspace/podpal
git push origin main
```
