"""PixelCast Core Engine.

Tailscale mesh device discovery, ADB wireless bridge management,
and scrcpy stream orchestration for Google Pixel on ZothOS.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pixel_cast.core")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class PixelDevice:
    name: str
    tailscale_ip: str
    os_name: str
    online: bool
    ping_ms: Optional[float] = None
    adb_connected: bool = False
    adb_serial: Optional[str] = None
    battery_level: Optional[int] = None
    battery_charging: Optional[bool] = None
    battery_temp_c: Optional[float] = None
    model: Optional[str] = None


DEFAULT_TARGET_IP = os.environ.get("PIXEL_CAST_TARGET_IP", "100.64.0.10")


@dataclass
class StreamOptions:
    serial: str = f"{DEFAULT_TARGET_IP}:5555"
    bitrate: str = "8M"
    max_size: int = 1080
    max_fps: int = 60
    audio: bool = True
    turn_screen_off: bool = False
    stay_awake: bool = True
    fullscreen: bool = False
    record_path: Optional[str] = None
    borderless: bool = False


class PixelCastManager:
    """Manages Tailscale peer discovery, ADB sessions, and Scrcpy mirroring."""

    def __init__(self):
        self.active_stream_process: Optional[subprocess.Popen] = None
        self.stream_start_time: Optional[float] = None
        self.last_screenshot_path: Optional[str] = None
        self.known_pixel_ip: str = os.environ.get("PIXEL_CAST_TARGET_IP", DEFAULT_TARGET_IP)

    # =========================================================================
    # Tailscale Peer Discovery & Telemetry
    # =========================================================================

    def get_tailscale_status(self) -> Dict[str, Any]:
        """Query tailscale status --json to detect self node and all connected peers."""
        result = {
            "self": {"hostname": "unknown", "ip": "127.0.0.1"},
            "peers": [],
            "pixel": None,
            "tailscale_active": False,
        }

        try:
            cmd = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if cmd.returncode != 0 and not cmd.stdout:
                logger.warning(f"tailscale status failed: {cmd.stderr}")
                return result

            data = json.loads(cmd.stdout)
            result["tailscale_active"] = True

            # Self node
            self_node = data.get("Self", {})
            ips = self_node.get("TailscaleIPs", [])
            ipv4 = next((ip for ip in ips if ":" not in ip), ips[0] if ips else "127.0.0.1")
            result["self"] = {
                "hostname": self_node.get("HostName", "ghost"),
                "dns_name": self_node.get("DNSName", "").rstrip("."),
                "ip": ipv4,
                "ips": ips,
                "os": self_node.get("OS", "linux"),
                "online": self_node.get("Online", True),
            }

            # Peers
            peers_dict = data.get("Peer", {})
            detected_pixel = None
            android_devices = []

            for _, peer in peers_dict.items():
                p_ips = peer.get("TailscaleIPs", [])
                p_ipv4 = next((ip for ip in p_ips if ":" not in ip), p_ips[0] if p_ips else None)
                p_hostname = peer.get("HostName", "")
                p_os = (peer.get("OS") or "").lower()
                is_online = bool(peer.get("Online", False))

                peer_info = {
                    "hostname": p_hostname,
                    "dns_name": peer.get("DNSName", "").rstrip("."),
                    "ip": p_ipv4,
                    "ips": p_ips,
                    "os": p_os,
                    "online": is_online,
                    "is_android": (p_os == "android" or "pixel" in p_hostname.lower() or "android" in p_hostname.lower()),
                }
                result["peers"].append(peer_info)

                if peer_info["is_android"] and is_online:
                    peer_info["ping_ms"] = self.ping_peer(p_ipv4)
                    android_devices.append(peer_info)
                    if p_ipv4 == self.known_pixel_ip:
                        detected_pixel = peer_info

            result["android_devices"] = android_devices

            if not detected_pixel and android_devices:
                # Default to selected or first
                detected_pixel = android_devices[0]

            if detected_pixel:
                result["pixel"] = detected_pixel
                if detected_pixel.get("ip"):
                    self.known_pixel_ip = detected_pixel["ip"]

        except Exception as e:
            logger.error(f"Error inspecting tailscale: {e}")

        return result

    def ping_peer(self, ip: str, timeout: float = 1.0) -> Optional[float]:
        """Pings peer IP and returns round-trip time in milliseconds."""
        if not ip:
            return None
        try:
            cmd = subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout)), ip],
                capture_output=True,
                text=True,
                timeout=timeout + 0.5,
            )
            if cmd.returncode == 0:
                match = re.search(r"time=([\d\.]+)\s*ms", cmd.stdout)
                if match:
                    return float(match.group(1))
        except Exception:
            pass
        return None

    # =========================================================================
    # ADB Device & Wireless Bridge Control
    # =========================================================================

    def get_adb_devices(self) -> List[Dict[str, Any]]:
        """List attached adb devices via adb devices -l."""
        devices = []
        try:
            cmd = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
            lines = cmd.stdout.strip().split("\n")
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    info = {"serial": serial, "state": state, "raw": line}
                    for part in parts[2:]:
                        if ":" in part:
                            k, v = part.split(":", 1)
                            info[k] = v
                    devices.append(info)
        except Exception as e:
            logger.error(f"Error checking adb devices: {e}")
        return devices

    def is_pixel_connected_adb(self, target_ip: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Check if Pixel is currently connected via ADB (by IP or model)."""
        ip = target_ip or self.known_pixel_ip
        devices = self.get_adb_devices()
        # 1. Check IP:port match
        for d in devices:
            if d.get("state") == "device" and ip in d["serial"]:
                return True, d["serial"]
        # 2. Check model match (Pixel)
        for d in devices:
            if d.get("state") == "device" and ("pixel" in (d.get("model") or "").lower() or "blazer" in (d.get("product") or "").lower()):
                return True, d["serial"]
        return False, None

    def adb_connect(self, ip: str, port: int = 5555) -> Dict[str, Any]:
        """Connect ADB to wireless endpoint."""
        target = f"{ip}:{port}"
        try:
            cmd = subprocess.run(["adb", "connect", target], capture_output=True, text=True, timeout=8)
            output = cmd.stdout.strip() or cmd.stderr.strip()
            success = "connected to" in output.lower() or "already connected" in output.lower()
            return {"success": success, "output": output, "target": target}
        except Exception as e:
            return {"success": False, "error": str(e), "target": target}

    def adb_disconnect(self, ip: str, port: int = 5555) -> Dict[str, Any]:
        """Disconnect ADB endpoint."""
        target = f"{ip}:{port}"
        try:
            cmd = subprocess.run(["adb", "disconnect", target], capture_output=True, text=True, timeout=5)
            return {"success": True, "output": cmd.stdout.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def adb_pair(self, ip: str, port: int, code: str) -> Dict[str, Any]:
        """Pair ADB with Wireless Debugging pair port and 6-digit code."""
        target = f"{ip}:{port}"
        try:
            cmd = subprocess.run(["adb", "pair", target, str(code).strip()], capture_output=True, text=True, timeout=10)
            output = cmd.stdout.strip() or cmd.stderr.strip()
            success = "successfully paired" in output.lower()
            return {"success": success, "output": output, "target": target}
        except Exception as e:
            return {"success": False, "error": str(e), "target": target}

    def enable_tcpip_mode(self, port: int = 5555) -> Dict[str, Any]:
        """Switch attached USB device to TCP/IP listening mode."""
        try:
            cmd = subprocess.run(["adb", "tcpip", str(port)], capture_output=True, text=True, timeout=5)
            output = cmd.stdout.strip() or cmd.stderr.strip()
            return {"success": cmd.returncode == 0, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scan_adb_ports(self, ip: str) -> List[int]:
        """Fast parallel TCP scan for active ADB ports (5555, common ranges)."""
        ports_to_check = [5555] + list(range(37000, 45000, 50))  # Sample common dynamic ports
        open_ports = []

        def check_port(port: int):
            try:
                with socket.create_connection((ip, port), timeout=0.3):
                    open_ports.append(port)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=30) as executor:
            executor.map(check_port, ports_to_check)

        return sorted(open_ports)

    # =========================================================================
    # Scrcpy Mirroring Orchestration
    # =========================================================================

    def start_scrcpy(self, options: Optional[StreamOptions] = None) -> Dict[str, Any]:
        """Launch scrcpy process targeting the Pixel over Tailscale or USB."""
        if self.is_scrcpy_running():
            return {
                "success": True,
                "already_running": True,
                "pid": self.active_stream_process.pid,
                "message": "Scrcpy stream is already active",
            }

        opts = options or StreamOptions()
        connected, serial = self.is_pixel_connected_adb(self.known_pixel_ip)

        if not connected:
            # Try auto-connecting to Tailscale IP:5555
            conn_res = self.adb_connect(self.known_pixel_ip, 5555)
            if conn_res.get("success"):
                serial = f"{self.known_pixel_ip}:5555"
            else:
                return {
                    "success": False,
                    "error": f"Device not connected on ADB. Connect to {self.known_pixel_ip}:5555 or pair first.",
                    "details": conn_res,
                }

        target_serial = serial or opts.serial

        # Construct scrcpy args
        cmd = ["scrcpy", "-s", target_serial]
        cmd.extend(["--video-bit-rate", str(opts.bitrate)])
        cmd.extend(["--max-size", str(opts.max_size)])
        cmd.extend(["--max-fps", str(opts.max_fps)])

        if opts.audio:
            cmd.extend(["--audio", "--audio-codec=opus", "--audio-dup"])
        else:
            cmd.append("--no-audio")

        if opts.turn_screen_off:
            cmd.append("--turn-screen-off")

        if opts.stay_awake:
            cmd.append("--stay-awake")

        if opts.fullscreen:
            cmd.append("--fullscreen")

        if opts.borderless:
            cmd.append("--window-borderless")

        if opts.record_path:
            cmd.append(f"--record={opts.record_path}")

        # Set environment for Wayland/X11
        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "WAYLAND_DISPLAY" not in env:
            env["WAYLAND_DISPLAY"] = "wayland-0"
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"

        try:
            logger.info(f"Launching scrcpy: {' '.join(cmd)}")
            self.active_stream_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            self.stream_start_time = time.time()
            return {
                "success": True,
                "pid": self.active_stream_process.pid,
                "target": target_serial,
                "command": " ".join(cmd),
            }
        except Exception as e:
            logger.error(f"Failed to launch scrcpy: {e}")
            return {"success": False, "error": str(e)}

    def stop_scrcpy(self) -> Dict[str, Any]:
        """Terminate the running scrcpy process."""
        if not self.is_scrcpy_running():
            return {"success": True, "message": "Scrcpy is not currently running"}

        try:
            pid = self.active_stream_process.pid
            self.active_stream_process.terminate()
            try:
                self.active_stream_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.active_stream_process.kill()
            self.active_stream_process = None
            self.stream_start_time = None
            return {"success": True, "stopped_pid": pid}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_scrcpy_running(self) -> bool:
        """Check if internal scrcpy process is alive or external scrcpy is active."""
        if self.active_stream_process is not None:
            if self.active_stream_process.poll() is None:
                return True
            else:
                self.active_stream_process = None
                self.stream_start_time = None

        # Check pgrep for system-wide scrcpy
        try:
            cmd = subprocess.run(["pgrep", "-x", "scrcpy"], capture_output=True, text=True)
            return cmd.returncode == 0
        except Exception:
            return False

    def get_stream_status(self) -> Dict[str, Any]:
        """Get live stream telemetry and uptime."""
        running = self.is_scrcpy_running()
        uptime = 0.0
        if running and self.stream_start_time:
            uptime = round(time.time() - self.stream_start_time, 1)

        return {
            "active": running,
            "pid": self.active_stream_process.pid if self.active_stream_process else None,
            "uptime_seconds": uptime,
        }

    # =========================================================================
    # Device Remote Control HUD (Keyevents, Text, Battery, Screenshot)
    # =========================================================================

    def _get_target_serial(self) -> str:
        connected, serial = self.is_pixel_connected_adb(self.known_pixel_ip)
        return serial or f"{self.known_pixel_ip}:5555"

    def send_keyevent(self, keycode: int) -> Dict[str, Any]:
        """Send Android keyevent (e.g. 3=HOME, 4=BACK, 26=POWER, 187=APP_SWITCH)."""
        serial = self._get_target_serial()
        try:
            cmd = subprocess.run(
                ["adb", "-s", serial, "shell", "input", "keyevent", str(keycode)],
                capture_output=True,
                text=True,
                timeout=4,
            )
            return {"success": cmd.returncode == 0, "keycode": keycode}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_text(self, text: str) -> Dict[str, Any]:
        """Type text on Pixel via ADB."""
        serial = self._get_target_serial()
        escaped = shlex.quote(text)
        try:
            cmd = subprocess.run(
                ["adb", "-s", serial, "shell", f"input text {escaped}"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=4,
            )
            return {"success": cmd.returncode == 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_battery_info(self) -> Dict[str, Any]:
        """Read battery level, temperature, and charging status via dumpsys battery."""
        serial = self._get_target_serial()
        result = {
            "level": 0,
            "scale": 100,
            "percent": 0,
            "charging": False,
            "temperature_c": 0.0,
            "health": "Good",
            "voltage_mv": 0,
        }
        try:
            cmd = subprocess.run(
                ["adb", "-s", serial, "shell", "dumpsys", "battery"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            for line in cmd.stdout.split("\n"):
                line = line.strip()
                if line.startswith("level:"):
                    result["level"] = int(line.split(":")[1].strip())
                elif line.startswith("scale:"):
                    result["scale"] = int(line.split(":")[1].strip())
                elif line.startswith("status:"):
                    # 2 is charging
                    result["charging"] = int(line.split(":")[1].strip()) == 2
                elif line.startswith("temperature:"):
                    raw_t = int(line.split(":")[1].strip())
                    result["temperature_c"] = round(raw_t / 10.0, 1)
                elif line.startswith("voltage:"):
                    result["voltage_mv"] = int(line.split(":")[1].strip())

            if result["scale"] > 0:
                result["percent"] = int((result["level"] / result["scale"]) * 100)
            result["success"] = True
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        return result

    def capture_screenshot(self, out_path: Optional[str] = None) -> Dict[str, Any]:
        """Capture screenshot from Pixel using screencap."""
        serial = self._get_target_serial()
        target_path = out_path or f"/tmp/pixel_shot_{int(time.time())}.png"
        try:
            with open(target_path, "wb") as f:
                cmd = subprocess.run(
                    ["adb", "-s", serial, "exec-out", "screencap", "-p"],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=8,
                )
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                self.last_screenshot_path = target_path
                return {"success": True, "path": target_path, "size_bytes": os.path.getsize(target_path)}
            else:
                return {"success": False, "error": "Captured screenshot file was empty"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_clipboard(self, text: Optional[str] = None) -> Dict[str, Any]:
        """Get or set clipboard text on Pixel."""
        serial = self._get_target_serial()
        if text:
            # Set clipboard via broadcast or am command
            try:
                # Use standard adb shell cmd clipboard set-text
                cmd = subprocess.run(
                    ["adb", "-s", serial, "shell", "cmd", "clipboard", "set-text", text],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                return {"success": True, "text": text}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            try:
                cmd = subprocess.run(
                    ["adb", "-s", serial, "shell", "cmd", "clipboard", "get-text"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                return {"success": True, "text": cmd.stdout.strip()}
            except Exception as e:
                return {"success": False, "error": str(e)}
