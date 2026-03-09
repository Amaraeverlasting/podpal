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

# Frontend paths
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
frontend_src = frontend_dist / "index.html"
landing_src = Path(__file__).parent.parent / "landing" / "index.html"
frontend_dist.mkdir(exist_ok=True)

# Inject Deepgram key into app HTML at serve time (if key provided)
dg_key = os.getenv("DEEPGRAM_API_KEY", "")
if frontend_src.exists() and dg_key:
    html = frontend_src.read_text()
    html = html.replace("DEEPGRAM_KEY_PLACEHOLDER", dg_key)
    frontend_src.write_text(html)

PORT = int(os.getenv("PORT", 8765))

if __name__ == "__main__":
    print(f"PodPal running at http://localhost:{PORT}")
    print(f"Open your browser to get started")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
