#!/usr/bin/env python3
"""PixelCast Production Server Runner.

Starts FastAPI/Uvicorn on port 8148 (default) listening on all interfaces (0.0.0.0)
so both localhost and Google Pixel over Tailscale mesh can connect instantly.
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PixelCast Sovereign Bridge Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8148, help="Port to listen on (default: 8148)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")
    args = parser.parse_args()

    print(f"===========================================================")
    print(f" PixelCast Bridge Server launching on http://{args.host}:{args.port}")
    print(f" Tailscale endpoint: http://100.106.132.5:{args.port}")
    print(f" Mobile companion:  http://100.106.132.5:{args.port}/mobile")
    print(f"===========================================================")

    uvicorn.run("pixel_cast.server:app", host=args.host, port=args.port, reload=args.reload)
