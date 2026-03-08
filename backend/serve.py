#!/usr/bin/env python3
"""
PodPal server - serves both API and frontend from one process.
Run: python3 serve.py
"""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

load_dotenv()

# Copy frontend + landing to dist
frontend_src = Path(__file__).parent.parent / "frontend" / "index.html"
landing_src = Path(__file__).parent.parent / "landing" / "index.html"
dist_dir = Path(__file__).parent.parent / "frontend" / "dist"
dist_dir.mkdir(exist_ok=True)

# Inject Deepgram key into app HTML at serve time
dg_key = os.getenv("DEEPGRAM_API_KEY", "")
html = frontend_src.read_text()
html = html.replace("DEEPGRAM_KEY_PLACEHOLDER", dg_key)
(dist_dir / "index.html").write_text(html)

# Copy landing page as root
shutil.copy2(landing_src, dist_dir / "landing.html")

PORT = int(os.getenv("PORT", 8765))

if __name__ == "__main__":
    print(f"PodPal running at http://localhost:{PORT}")
    print(f"Open your browser to get started")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
