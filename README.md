# PixelCast

[![Zoth Studio v2](https://img.shields.io/badge/Zoth_Studio_v2-Dossier-D4AF37?style=for-the-badge)](https://zoth.nullai.tech/tools/pixel-cast)
[![Workstation](https://img.shields.io/badge/Workstation-127.0.0.1:8148-38BDF8?style=for-the-badge)](http://127.0.0.1:8148)
[![Scrcpy](https://img.shields.io/badge/scrcpy-3.x-10B981?style=for-the-badge)](https://github.com/Genymobile/scrcpy)
[![Support](https://img.shields.io/badge/Support-Buy_Us_a_Coffee-FFDD00?style=for-the-badge)](https://buy.stripe.com/3cIfZg27PdKo2D64Ocfw40X)
[![License: MIT](https://img.shields.io/badge/License-MIT-gold?style=for-the-badge)](LICENSE)

Low-latency Google Pixel wireless ADB bridge, `scrcpy 3.x` desktop mirroring orchestrator, and Tailscale WireGuard camera/file companion (`127.0.0.1:8148`). Built for ZothOS v3.4.0 and Zoth Studio v2 with zero third-party cloud relays.

## Overview

| Property | Specification |
| :--- | :--- |
| **Tool ID** | `pixel-cast` |
| **Category** | `Hardware & OS` |
| **Loopback Workstation** | `http://127.0.0.1:8148` (`python3 server.py --host 127.0.0.1 --port 8148`) |
| **Tailscale Companion** | `http://<tailscale-ip>:8148/mobile` |
| **Zoth Studio v2 Dossier** | [`https://zoth.nullai.tech/tools/pixel-cast`](https://zoth.nullai.tech/tools/pixel-cast) (`http://127.0.0.1:3000/tools/pixel-cast`) |
| **ZothOS v3.4.0 CLI** | `pixel-cast` (`bin/pixel-cast`) and `pixel-cast-tui` (`bin/pixel-cast-tui`) |
| **Video & Audio Engine** | `scrcpy 3.x` (H.264 video + Opus `--audio-codec=opus --audio-dup`) |
| **License** | MIT — 100% Free & Open-Source |

## Architecture

```text
+-----------------------------------+                 +------------------------------------+
|       Google Pixel (Android)      |                 |        ZothOS Host Desktop         |
|          (<tailscale-ip>)         |                 |   (127.0.0.1 / <tailscale-ip>)     |
|                                   |                 |                                    |
|  * Wireless Debugging (ADB)       |<-- Tailscale -->|  * tailscale status --json         |
|  * Port 5555 / 6-Digit Pairing    |    WireGuard    |  * scrcpy 3.x H.264 + Opus Bridge  |
|  * /mobile WebSocket Camera & Drop|                 |  * FastAPI + WebSocket (:8148)     |
+-----------------------------------+                 +------------------------------------+
```

1. **Dynamic Tailscale Mesh Discovery (`src/pixel_cast/core.py`)**
   - Queries `tailscale status --json` to auto-detect the local host node and online Android/Pixel peers, measuring live ICMP round-trip latency (`ping -c 1`).
   - Supports environment configuration via `PIXEL_CAST_TARGET_IP` (defaults to RFC 6598 placeholder `100.64.0.10` when Tailscale is offline) and `PIXEL_CAST_HOST_IP`.
2. **ADB Wireless Bridge & `scrcpy 3.x` Orchestrator**
   - Handles Android Wireless Debugging 6-digit pairing (`adb pair`), TCP/IP bridge connection (`adb connect`), parallel dynamic port scanning (`37000–45000`), hardware keyevents (`KEYMAP`), text injection, clipboard sync, `dumpsys battery` telemetry, and `screencap -p` PNG capture.
   - Spawns `scrcpy 3.x` with configurable resolution (`--max-size`), bitrate (`--video-bit-rate`), frame rate (`--max-fps`), Opus audio duplication, `--turn-screen-off`, `--stay-awake`, and MP4 session recording (`--record`).
3. **FastAPI Workstation & WebSocket Relay (`src/pixel_cast/server.py`)**
   - Serves the desktop control deck at `/` and the mobile camera/file-drop companion at `/mobile`, relaying live frames over `/ws` and pushing uploaded files directly to `/sdcard/Download/` when ADB is active.

## Quickstart

```bash
git clone https://github.com/1nc0gn30/pixel-cast.git
cd pixel-cast
python3 -m pip install fastapi uvicorn pydantic httpx pytest

# Start the loopback workstation on 127.0.0.1:8148
./bin/pixel-cast serve --host 127.0.0.1 --port 8148

# Optional: bind to your Tailscale interface IP so /mobile is reachable from your Pixel
./bin/pixel-cast serve --host <tailscale-ip> --port 8148
```

## CLI & MCP Usage

### ZothOS v3.4.0 CLI (`bin/pixel-cast`)

| Command | Description |
| :--- | :--- |
| `./bin/pixel-cast status` | Show Tailscale host/peer discovery, ICMP ping, ADB serial, `scrcpy` PID, and battery telemetry |
| `./bin/pixel-cast --json status` | Emit deterministic JSON status payload for scripts and local agents |
| `./bin/pixel-cast pair <port> <code> [--ip <tailscale-ip>]` | Pair with Android Wireless Debugging 6-digit pairing code |
| `./bin/pixel-cast connect [5555] [--ip <tailscale-ip>]` | Connect wireless ADB over Tailscale |
| `./bin/pixel-cast disconnect [5555]` | Disconnect active wireless ADB target |
| `./bin/pixel-cast stream [--max-size 1440 --bitrate 16M --max-fps 60]` | Launch `scrcpy 3.x` desktop mirror window |
| `./bin/pixel-cast stop` | Terminate running `scrcpy` session |
| `./bin/pixel-cast screenshot [out.png]` | Capture PNG screenshot from the Pixel via `adb exec-out screencap -p` |
| `./bin/pixel-cast battery` | Query battery percentage, charging state, temperature (`°C`), and voltage (`mV`) |
| `./bin/pixel-cast key <home\|back\|power\|recents\|volup\|voldown\|mute>` | Send Android hardware navigation keyevent |
| `./bin/pixel-cast text "<string>"` | Type escaped text into the focused Android input field |
| `./bin/pixel-cast qr` | Render ANSI UTF-8 QR code in the terminal for `http://<tailscale-ip>:8148/mobile` |
| `./bin/pixel-cast serve --host 127.0.0.1 --port 8148` | Run the FastAPI + WebSocket server |
| `./bin/pixel-cast --tui` | Launch the ZothOS Unicode `U+2800` Braille TUI (`pixel-cast-tui`) |

### REST & WebSocket Endpoints (`127.0.0.1:8148`)

- `GET /health`, `GET /api/health` — Service health and binary presence (`scrcpy`, `adb`, `tailscale`).
- `GET /api/status` — Combined Tailscale peer discovery, ADB device state, `scrcpy` uptime, and battery telemetry.
- `POST /api/target` — Set active target IP (`{ "ip": "<tailscale-ip>" }`).
- `POST /api/pair`, `POST /api/connect`, `POST /api/disconnect`, `POST /api/tcpip`, `POST /api/scan` — Wireless ADB lifecycle controls.
- `POST /api/stream/start`, `POST /api/stream/stop`, `GET /api/stream/status` — `scrcpy 3.x` stream controls.
- `POST /api/control/key`, `POST /api/control/text`, `GET|POST /api/control/clipboard` — Remote input and clipboard sync.
- `GET /api/battery`, `GET /api/screenshot`, `GET /api/qr`, `POST /api/upload`, `WS /ws` — Telemetry, QR PNG generation, file push, and live camera frame relay.

## Testing & Verification

```bash
# Run automated FastAPI & core unit tests
python3 -m pytest -q

# Verify CLI help and JSON telemetry
./bin/pixel-cast --help
./bin/pixel-cast --json status
```

## Support

PixelCast is 100% free and open-source with zero paywalls. Optional support: [Buy Us a Coffee via Stripe](https://buy.stripe.com/3cIfZg27PdKo2D64Ocfw40X).

## License

Released under the [MIT License](LICENSE). Engineered by [1nc0gn30](https://1nc0gn30.si) (`@1nc0gn30`) and [NullAI](https://nullai.tech).
