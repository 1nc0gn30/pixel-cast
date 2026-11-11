"""Automated Test Suite for PixelCast Sovereign Bridge (`pixel-cast`)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pixel_cast.core import PixelCastManager, PixelDevice, StreamOptions
from pixel_cast.server import KEYMAP, app


client = TestClient(app)


def test_pixel_device_dataclass():
    dev = PixelDevice(
        name="pixel-9-pro",
        tailscale_ip="100.64.0.10",
        os_name="android",
        online=True,
        ping_ms=4.2,
        adb_connected=True,
        adb_serial="100.64.0.10:5555",
        battery_level=94,
        battery_charging=True,
    )
    assert dev.name == "pixel-9-pro"
    assert dev.tailscale_ip == "100.64.0.10"
    assert dev.online is True
    assert dev.battery_level == 94


def test_stream_options_defaults():
    opts = StreamOptions()
    assert opts.bitrate == "8M"
    assert opts.max_size == 1080
    assert opts.max_fps == 60
    assert opts.audio is True
    assert opts.stay_awake is True


def test_manager_initialization_and_status():
    mgr = PixelCastManager()
    assert mgr.known_pixel_ip == "100.64.0.10"
    stream_st = mgr.get_stream_status()
    assert "active" in stream_st
    assert "uptime_seconds" in stream_st


def test_manager_tailscale_status_schema():
    mgr = PixelCastManager()
    ts = mgr.get_tailscale_status()
    assert "self" in ts
    assert "peers" in ts
    assert isinstance(ts["peers"], list)


def test_manager_adb_devices_list():
    mgr = PixelCastManager()
    devices = mgr.get_adb_devices()
    assert isinstance(devices, list)


def test_api_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pixel-cast"
    assert "adb_installed" in data


def test_api_system_status_endpoint():
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "tailscale" in data
    assert "adb" in data
    assert "stream" in data


def test_api_set_target_endpoint():
    res = client.post("/api/target", json={"ip": "100.64.0.10"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["target_ip"] == "100.64.0.10"


def test_api_stream_status_endpoint():
    res = client.get("/api/stream/status")
    assert res.status_code == 200
    data = res.json()
    assert "active" in data


def test_keymap_navigation_constants():
    assert KEYMAP["home"] == 3
    assert KEYMAP["back"] == 4
    assert KEYMAP["power"] == 26
    assert KEYMAP["recents"] == 187
    assert KEYMAP["volup"] == 24
    assert KEYMAP["voldown"] == 25
