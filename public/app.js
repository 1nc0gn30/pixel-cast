/**
 * PixelCast Workstation Frontend Application
 * Real-time telemetry, scrcpy orchestration, and hardware control
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const meshLed = document.getElementById('meshLed');
  const meshStatusText = document.getElementById('meshStatusText');
  const meshPingText = document.getElementById('meshPingText');
  
  const deviceSelectDropdown = document.getElementById('deviceSelectDropdown');
  const deviceIpText = document.getElementById('deviceIpText');
  const adbStatusBadge = document.getElementById('adbStatusBadge');
  const hudBatteryVal = document.getElementById('hudBatteryVal');
  const hudTempVal = document.getElementById('hudTempVal');
  const hudHostVal = document.getElementById('hudHostVal');
  const hudPingVal = document.getElementById('hudPingVal');

  const btnLaunchScrcpy = document.getElementById('btnLaunchScrcpy');
  const launchBtnText = document.getElementById('launchBtnText');
  const btnStopScrcpy = document.getElementById('btnStopScrcpy');
  const btnTakeScreenshot = document.getElementById('btnTakeScreenshot');
  
  const liveScreenImage = document.getElementById('liveScreenImage');
  const streamIdleOverlay = document.getElementById('streamIdleOverlay');
  const livePill = document.getElementById('livePill');
  const btnFullscreenCanvas = document.getElementById('btnFullscreenCanvas');

  const typerInput = document.getElementById('typerInput');
  const btnSendText = document.getElementById('btnSendText');
  const btnPushClipboard = document.getElementById('btnPushClipboard');
  const btnPullClipboard = document.getElementById('btnPullClipboard');

  const mobileCastUrl = document.getElementById('mobileCastUrl');
  const qrCodeImg = document.getElementById('qrCodeImg');
  const btnCopyUrl = document.getElementById('btnCopyUrl');

  const prefResolution = document.getElementById('prefResolution');
  const prefBitrate = document.getElementById('prefBitrate');
  const prefFps = document.getElementById('prefFps');
  const prefAudio = document.getElementById('prefAudio');
  const prefScreenOff = document.getElementById('prefScreenOff');
  const prefRecord = document.getElementById('prefRecord');

  const pairPortInput = document.getElementById('pairPortInput');
  const pairCodeInput = document.getElementById('pairCodeInput');
  const btnPairSubmit = document.getElementById('btnPairSubmit');
  const btnScanPorts = document.getElementById('btnScanPorts');
  const btnReconnectAdb = document.getElementById('btnReconnectAdb');
  const pairResultMsg = document.getElementById('pairResultMsg');

  const solTipAddr = document.getElementById('solTipAddr');

  let currentTargetIp = '100.64.0.10';
  let isStreamActive = false;
  let ws = null;

  // =========================================================================
  // WebSocket Initialization
  // =========================================================================
  function initWebSocket() {
    const loc = window.location;
    const wsProtocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${loc.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[PixelCast] WebSocket connected to server');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'remote_frame' && msg.data) {
          // Live frame stream from mobile camera
          liveScreenImage.src = msg.data;
          streamIdleOverlay.classList.add('hidden');
          livePill.innerText = 'CAMERA LIVE';
          livePill.classList.add('active');
        } else if (msg.type === 'stream_status') {
          updateStreamUI(msg.active);
        }
      } catch (e) {
        // Raw frame or unparsed
      }
    };

    ws.onclose = () => {
      setTimeout(initWebSocket, 2500);
    };
  }
  initWebSocket();

  // =========================================================================
  // Telemetry & Status Polling
  // =========================================================================
  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();

      // Tailscale Self & Peer
      const ts = data.tailscale || {};
      const selfNode = ts.self || {};
      const pixel = ts.pixel;
      const androidList = ts.android_devices || [];

      hudHostVal.innerText = selfNode.ip || '127.0.0.1';

      // Update dropdown options if needed
      if (androidList.length > 0 && deviceSelectDropdown) {
        const currentVal = deviceSelectDropdown.value;
        const currentOptions = Array.from(deviceSelectDropdown.options).map(o => o.value);
        const newOptions = androidList.map(d => d.ip);
        if (JSON.stringify(currentOptions) !== JSON.stringify(newOptions)) {
          deviceSelectDropdown.innerHTML = '';
          androidList.forEach(dev => {
            const opt = document.createElement('option');
            opt.value = dev.ip;
            opt.innerText = `${dev.hostname} (${dev.ip})`;
            deviceSelectDropdown.appendChild(opt);
          });
          deviceSelectDropdown.value = currentVal || (pixel ? pixel.ip : androidList[0].ip);
        }
      }

      if (pixel && pixel.online) {
        currentTargetIp = pixel.ip;
        if (deviceSelectDropdown && deviceSelectDropdown.value !== pixel.ip) {
          deviceSelectDropdown.value = pixel.ip;
        }
        deviceIpText.innerText = pixel.ip;
        meshStatusText.innerText = `${pixel.hostname} Active`;
        meshPingText.innerText = pixel.ping_ms ? `~${pixel.ping_ms}ms` : 'Active';
        hudPingVal.innerText = pixel.ping_ms ? `${pixel.ping_ms} ms` : 'Active';
        meshLed.classList.add('online');
      } else {
        meshStatusText.innerText = 'Mesh Node Standby';
        meshPingText.innerText = 'Checking...';
      }

      // ADB Connection
      const adb = data.adb || {};
      if (adb.connected) {
        adbStatusBadge.innerText = 'ADB Connected';
        adbStatusBadge.style.color = 'var(--green-online)';
        adbStatusBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        adbStatusBadge.style.background = 'rgba(16, 185, 129, 0.15)';
      } else {
        adbStatusBadge.innerText = 'ADB Offline';
        adbStatusBadge.style.color = '#EF4444';
        adbStatusBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        adbStatusBadge.style.background = 'rgba(239, 68, 68, 0.15)';
      }

      // Battery & Thermals
      const bat = data.battery;
      if (bat && bat.success) {
        const chg = bat.charging ? ' ⚡' : '';
        hudBatteryVal.innerText = `${bat.percent}%${chg}`;
        hudTempVal.innerText = `${bat.temperature_c}°C`;
      }

      // Scrcpy Stream Status
      const stream = data.stream || {};
      updateStreamUI(Boolean(stream.active));

      // QR URL update
      const targetHost = selfNode.ip || window.location.hostname;
      const mUrl = `http://${targetHost}:8148/mobile`;
      if (mobileCastUrl.innerText !== mUrl) {
        mobileCastUrl.innerText = mUrl;
        qrCodeImg.src = `/api/qr?url=${encodeURIComponent(mUrl)}`;
      }

    } catch (err) {
      console.warn('Status poll warning:', err);
    }
  }

  function updateStreamUI(active) {
    isStreamActive = active;
    if (active) {
      btnLaunchScrcpy.classList.add('btn-running');
      launchBtnText.innerText = 'Mirror Active on Desktop';
      btnStopScrcpy.disabled = false;
      livePill.innerText = 'STREAM ACTIVE';
      livePill.classList.add('active');
      streamIdleOverlay.classList.add('hidden');
    } else {
      btnLaunchScrcpy.classList.remove('btn-running');
      launchBtnText.innerText = 'Launch 60fps Desktop Mirror';
      btnStopScrcpy.disabled = true;
      livePill.innerText = 'READY';
      livePill.classList.remove('active');
    }
  }

  // Poll status every 4 seconds
  fetchStatus();
  setInterval(fetchStatus, 4000);

  if (deviceSelectDropdown) {
    deviceSelectDropdown.addEventListener('change', async (e) => {
      const chosenIp = e.target.value;
      currentTargetIp = chosenIp;
      try {
        await fetch('/api/target', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ip: chosenIp })
        });
        fetchStatus();
      } catch (err) {
        console.error(err);
      }
    });
  }

  // =========================================================================
  // Scrcpy Streaming Controls
  // =========================================================================
  btnLaunchScrcpy.addEventListener('click', async () => {
    launchBtnText.innerText = 'Connecting & Launching...';
    try {
      const payload = {
        serial: `${currentTargetIp}:5555`,
        bitrate: prefBitrate.value,
        max_size: parseInt(prefResolution.value, 10),
        max_fps: parseInt(prefFps.value, 10),
        audio: prefAudio.checked,
        turn_screen_off: prefScreenOff.checked,
        stay_awake: true,
        record: prefRecord.checked,
      };

      const res = await fetch('/api/stream/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        updateStreamUI(true);
        refreshSnapshot();
      } else {
        alert('Could not start screen mirror: ' + (data.error || JSON.stringify(data)));
        updateStreamUI(false);
      }
    } catch (e) {
      alert('Launch failed: ' + e.message);
      updateStreamUI(false);
    }
  });

  btnStopScrcpy.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/stream/stop', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        updateStreamUI(false);
      }
    } catch (e) {
      console.error(e);
    }
  });

  // =========================================================================
  // Snapshot & Fullscreen
  // =========================================================================
  async function refreshSnapshot() {
    liveScreenImage.src = `/api/screenshot?t=${Date.now()}`;
    liveScreenImage.onload = () => {
      streamIdleOverlay.classList.add('hidden');
    };
  }

  btnTakeScreenshot.addEventListener('click', () => {
    refreshSnapshot();
  });

  btnFullscreenCanvas.addEventListener('click', () => {
    const stage = document.getElementById('viewportStage');
    if (!document.fullscreenElement) {
      stage.requestFullscreen().catch(err => alert(err.message));
    } else {
      document.exitFullscreen();
    }
  });

  // =========================================================================
  // Remote Hardware Keys & Navigation
  // =========================================================================
  document.querySelectorAll('.hw-btn, .mini-vol-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const key = btn.dataset.key;
      if (!key) return;
      try {
        await fetch('/api/control/key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key })
        });
        // Brief refresh of snapshot
        setTimeout(refreshSnapshot, 600);
      } catch (err) {
        console.error('Key event error:', err);
      }
    });
  });

  // Text Typer
  btnSendText.addEventListener('click', async () => {
    const text = typerInput.value.trim();
    if (!text) return;
    try {
      await fetch('/api/control/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      typerInput.value = '';
      setTimeout(refreshSnapshot, 600);
    } catch (err) {
      alert('Failed to type text: ' + err.message);
    }
  });

  typerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      btnSendText.click();
    }
  });

  // Clipboard sync
  btnPushClipboard.addEventListener('click', async () => {
    const text = prompt('Enter text to copy to Pixel clipboard:');
    if (!text) return;
    try {
      const res = await fetch('/api/control/clipboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const d = await res.json();
      if (d.success) alert('✓ Successfully set Pixel clipboard');
    } catch (err) {
      alert('Clipboard error: ' + err.message);
    }
  });

  btnPullClipboard.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/control/clipboard');
      const d = await res.json();
      if (d.success) {
        alert('Pixel Clipboard content:\n' + d.text);
      }
    } catch (err) {
      alert('Clipboard error: ' + err.message);
    }
  });

  // =========================================================================
  // Pairing & Port Scanner
  // =========================================================================
  btnPairSubmit.addEventListener('click', async () => {
    const port = parseInt(pairPortInput.value, 10);
    const code = pairCodeInput.value.trim();
    if (!port || !code) {
      pairResultMsg.innerText = 'Please enter both pair port and 6-digit code';
      return;
    }

    pairResultMsg.innerText = `Pairing with ${currentTargetIp}:${port}...`;
    try {
      const res = await fetch('/api/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: currentTargetIp, port, code })
      });
      const d = await res.json();
      if (d.success) {
        pairResultMsg.innerText = '✓ Paired successfully! Auto-connecting...';
        await fetch('/api/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ip: currentTargetIp, port: 5555 })
        });
        fetchStatus();
      } else {
        pairResultMsg.innerText = '✗ Pairing failed: ' + (d.output || d.error);
      }
    } catch (err) {
      pairResultMsg.innerText = 'Pair error: ' + err.message;
    }
  });

  btnScanPorts.addEventListener('click', async () => {
    pairResultMsg.innerText = 'Scanning open ADB ports on Pixel...';
    try {
      const res = await fetch('/api/scan', { method: 'POST' });
      const d = await res.json();
      if (d.open_ports && d.open_ports.length > 0) {
        pairResultMsg.innerText = `Found open ports: ${d.open_ports.join(', ')}`;
      } else {
        pairResultMsg.innerText = 'No standard open ports found. Try toggling Wireless Debugging.';
      }
    } catch (err) {
      pairResultMsg.innerText = 'Scan error: ' + err.message;
    }
  });

  btnReconnectAdb.addEventListener('click', async () => {
    pairResultMsg.innerText = `Reconnecting to ${currentTargetIp}:5555...`;
    try {
      const res = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: currentTargetIp, port: 5555 })
      });
      const d = await res.json();
      if (d.success) {
        pairResultMsg.innerText = '✓ Connected to 5555';
        fetchStatus();
      } else {
        pairResultMsg.innerText = '✗ Connect failed: ' + (d.output || d.error);
      }
    } catch (err) {
      pairResultMsg.innerText = 'Error: ' + err.message;
    }
  });

  // =========================================================================
  // Copy Helpers
  // =========================================================================
  btnCopyUrl.addEventListener('click', () => {
    navigator.clipboard.writeText(mobileCastUrl.innerText);
    btnCopyUrl.innerText = 'Copied!';
    setTimeout(() => { btnCopyUrl.innerText = 'Copy'; }, 1500);
  });

  if (solTipAddr && solTipAddr.parentElement) {
    solTipAddr.parentElement.addEventListener('click', () => {
      navigator.clipboard.writeText(solTipAddr.innerText);
      const originalText = solTipAddr.innerText;
      solTipAddr.innerText = 'Copied Address!';
      setTimeout(() => { solTipAddr.innerText = originalText; }, 1500);
    });
  }

});
