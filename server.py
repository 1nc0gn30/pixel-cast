#!/usr/bin/env python3
"""PixelCast Production Server Runner.

Starts FastAPI/Uvicorn on port 8148 (default) bound to 127.0.0.1 (or a custom
Tailscale interface via --host / PIXEL_CAST_HOST).
"""

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn
from pixel_cast.core import PixelCastManager

if __name__ == "__main__":
    default_host = os.environ.get("PIXEL_CAST_HOST", "127.0.0.1")
    parser = argparse.ArgumentParser(description="PixelCast Bridge Server")
    parser.add_argument("--host", default=default_host, help=f"Host interface (default: {default_host})")
    parser.add_argument("--port", type=int, default=8148, help="Port to listen on (default: 8148)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")
    args = parser.parse_args()

    ts = PixelCastManager().get_tailscale_status()
    ts_ip = ts.get("self", {}).get("ip") or "<tailscale-ip>"

    print("===========================================================")
    print(f" PixelCast Bridge Server launching on http://{args.host}:{args.port}")
    print(f" Tailscale endpoint: http://{ts_ip}:{args.port}")
    print(f" Mobile companion:  http://{ts_ip}:{args.port}/mobile")
    print("===========================================================")

    uvicorn.run("pixel_cast.server:app", host=args.host, port=args.port, reload=args.reload)
