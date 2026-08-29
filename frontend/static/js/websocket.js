/**
 * Live Surveillance Feed, WebSocket Stream & Watchlist Alert Engine
 * BEL / City Traffic Operations Command Center
 */

class SurveillanceStream {
  constructor() {
    this.socket = null;
    this.isMuted = false;
    this.audioCtx = null;
    this.currentFilter = 'all';
    this.feedContainer = null;
    this.activeAlertCount = 3;
    this.simTimer = null;

    // Watchlist Database
    this.watchlist = new Map([
      ["DL01AB1234", { reason: "CRITICAL: Reported Stolen (FIR #4092)", level: "red" }],
      ["HR26CY9999", { reason: "ALERT: Multiple Red-Light Violations & Evading Toll", level: "amber" }],
      ["UP16EF7788", { reason: "SUSPECT: Banned Commercial Transit Corridor", level: "amber" }]
    ]);

    // Simulated plate stream pool
    this.samplePlates = [
      { plate: "HR26DQ5551", camId: "CAM-01", camName: "Cyber Hub North Gate", type: "Sedan (White)", speed: "64 km/h", isWatchlist: false },
      { plate: "DL03CC8899", camId: "CAM-02", camName: "MG Road Metro Jct", type: "SUV (Black)", speed: "52 km/h", isWatchlist: false },
      { plate: "DL01AB1234", camId: "CAM-06", camName: "IGI Airport Expressway North", type: "SUV (Black)", speed: "94 km/h", isWatchlist: true, reason: "Reported Stolen (FIR #4092)" },
      { plate: "HR29AZ1234", camId: "CAM-03", camName: "IFFCO Chowk Flyover", type: "Hatchback (Silver)", speed: "68 km/h", isWatchlist: false },
      { plate: "UP16BN4422", camId: "CAM-04", camName: "Golf Course Extn Rd", type: "EV Cab (Blue)", speed: "58 km/h", isWatchlist: false },
      { plate: "HR26CY9999", camId: "CAM-05", camName: "Kherki Daula Toll", type: "Heavy Truck", speed: "78 km/h", isWatchlist: true, reason: "Multiple Toll Violations" },
      { plate: "MH02CB4040", camId: "CAM-07", camName: "Ring Road - Dhaula Kuan", type: "Luxury Sedan", speed: "65 km/h", isWatchlist: false },
      { plate: "KA03MG8899", camId: "CAM-12", camName: "Sohna Road Badshahpur", type: "EV SUV", speed: "48 km/h", isWatchlist: false },
      { plate: "DL08AK1122", camId: "CAM-08", camName: "AIIMS South Extn", type: "Two-Wheeler", speed: "42 km/h", isWatchlist: false }
    ];
  }

  init() {
    this.feedContainer = document.getElementById('live-detections-feed');
    this.setupAudio();
    this.setupEventListeners();
    this.connectWebSocket();
  }

  setupAudio() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AudioContext();
    } catch (e) {
      console.warn("Web Audio API not supported", e);
    }
  }

  playAlertChime(type = 'danger') {
    if (this.isMuted || !this.audioCtx) return;

    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    const osc1 = this.audioCtx.createOscillator();
    const osc2 = this.audioCtx.createOscillator();
    const gainNode = this.audioCtx.createGain();

    osc1.type = type === 'danger' ? 'sawtooth' : 'sine';
    osc2.type = 'sine';

    if (type === 'danger') {
      osc1.frequency.setValueAtTime(880, this.audioCtx.currentTime); // A5
      osc1.frequency.exponentialRampToValueAtTime(440, this.audioCtx.currentTime + 0.3);
      osc2.frequency.setValueAtTime(1174, this.audioCtx.currentTime); // D6
      osc2.frequency.exponentialRampToValueAtTime(587, this.audioCtx.currentTime + 0.3);
    } else {
      osc1.frequency.setValueAtTime(523.25, this.audioCtx.currentTime); // C5
      osc1.frequency.exponentialRampToValueAtTime(659.25, this.audioCtx.currentTime + 0.2);
    }

    gainNode.gain.setValueAtTime(0.15, this.audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.35);

    osc1.connect(gainNode);
    osc2.connect(gainNode);
    gainNode.connect(this.audioCtx.destination);

    osc1.start();
    osc2.start();
    osc1.stop(this.audioCtx.currentTime + 0.35);
    osc2.stop(this.audioCtx.currentTime + 0.35);
  }

  connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live-feed`;

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.updateConnectionStatus(true);
        if (this.simTimer) clearInterval(this.simTimer);
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleIncomingDetection(data);
        } catch (e) {
          console.error("Failed to parse websocket message", e);
        }
      };

      this.socket.onerror = () => {
        this.fallbackToSimulation();
      };

      this.socket.onclose = () => {
        this.updateConnectionStatus(false);
        this.fallbackToSimulation();
      };
    } catch (e) {
      this.fallbackToSimulation();
    }
  }

  fallbackToSimulation() {
    this.updateConnectionStatus(true, "SIMULATED STREAM ACTIVE");
    if (this.simTimer) return;

    // Feed a new detection every 2.8 to 4.5 seconds
    this.simTimer = setInterval(() => {
      const item = this.samplePlates[Math.floor(Math.random() * this.samplePlates.length)];
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0];

      const detection = {
        ...item,
        timestamp: timeStr,
        id: "det_" + Math.random().toString(36).substr(2, 9)
      };

      this.handleIncomingDetection(detection);
    }, 3200);
  }

  updateConnectionStatus(connected, text = null) {
    const statusDot = document.getElementById('ws-status-dot');
    const statusText = document.getElementById('ws-status-text');
    if (statusDot) {
      statusDot.style.background = connected ? 'var(--accent-green)' : 'var(--accent-amber)';
      statusDot.style.boxShadow = connected ? '0 0 8px var(--accent-green)' : '0 0 8px var(--accent-amber)';
    }
    if (statusText) {
      statusText.textContent = text || (connected ? 'LIVE TELEMETRY FEED' : 'RECONNECTING...');
    }
  }

  handleIncomingDetection(data) {
    const isWatchlistHit = data.isWatchlist || this.watchlist.has(data.plate);
    const alertInfo = isWatchlistHit ? (this.watchlist.get(data.plate) || { reason: data.reason || "Hotlist Vehicle", level: "red" }) : null;

    if (isWatchlistHit) {
      this.triggerWatchlistToast(data, alertInfo);
      this.playAlertChime('danger');
      this.incrementAlertCounter();
    }

    this.prependDetectionCard(data, isWatchlistHit, alertInfo);
  }

  prependDetectionCard(data, isWatchlist, alertInfo) {
    if (!this.feedContainer) return;

    // Filter check
    if (this.currentFilter === 'alerts' && !isWatchlist) return;
    if (this.currentFilter === 'speeding' && parseInt(data.speed) < 75) return;

    const card = document.createElement('div');
    card.className = `detection-card ${isWatchlist ? 'flagged-alert' : ''}`;
    card.id = `det-card-${data.id || Date.now()}`;

    // Synthesize vehicle plate preview svg
    const plateSvg = this.createPlateSvgDataUri(data.plate);

    card.innerHTML = `
      <div class="detection-top-row">
        <span class="detected-plate">${data.plate}</span>
        <span class="detection-cam-badge">${data.camName || data.camId}</span>
      </div>
      <div class="detection-media-row">
        <img class="detection-crop-img" src="${plateSvg}" alt="Plate Crop" />
        <div class="detection-info">
          <span class="detection-veh-type">${data.type || 'Passenger Vehicle'}</span>
          <span class="detection-time">TIME: ${data.timestamp || 'JUST NOW'} | SPEED: <b style="color: var(--accent-cyan);">${data.speed || '55 km/h'}</b></span>
          ${isWatchlist ? `<span style="color: var(--accent-red); font-size: 0.72rem; font-weight: 700;">⚠️ ${alertInfo.reason}</span>` : ''}
        </div>
      </div>
      <div class="detection-card-actions">
        <button class="mini-action-btn track-btn" onclick="window.cityMap.loadTrajectory('${data.plate}')">
          📍 Track Trajectory
        </button>
      </div>
    `;

    this.feedContainer.insertBefore(card, this.feedContainer.firstChild);

    // Keep max 35 cards in DOM
    if (this.feedContainer.children.length > 35) {
      this.feedContainer.removeChild(this.feedContainer.lastChild);
    }
  }

  createPlateSvgDataUri(plateText) {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="130" height="84" viewBox="0 0 130 84">
        <rect width="130" height="84" fill="#111827"/>
        <rect x="5" y="8" width="120" height="68" rx="4" fill="#facc15" stroke="#000" stroke-width="2"/>
        <rect x="8" y="11" width="16" height="62" fill="#1e3a8a"/>
        <text x="16" y="44" fill="#ffffff" font-size="8" font-weight="bold" text-anchor="middle" font-family="monospace">IND</text>
        <circle cx="16" cy="52" r="3" fill="#ffffff"/>
        <text x="70" y="50" fill="#000000" font-size="14" font-weight="900" text-anchor="middle" font-family="monospace" letter-spacing="1">${plateText}</text>
      </svg>
    `;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  }

  triggerWatchlistToast(data, alertInfo) {
    const toast = document.getElementById('watchlist-alert-banner');
    if (!toast) return;

    document.getElementById('alert-toast-plate').textContent = data.plate;
    document.getElementById('alert-toast-location').textContent = `${data.camName || data.camId} (Speed: ${data.speed || '88 km/h'})`;
    document.getElementById('alert-toast-reason').textContent = alertInfo ? alertInfo.reason : 'Security Hotlist Match';

    const trackBtn = document.getElementById('btn-toast-track');
    if (trackBtn) {
      trackBtn.onclick = () => {
        window.cityMap.loadTrajectory(data.plate);
        this.dismissAlertToast();
      };
    }

    toast.classList.add('active');

    // Auto dismiss after 9 seconds if not clicked
    setTimeout(() => {
      this.dismissAlertToast();
    }, 9000);
  }

  dismissAlertToast() {
    const toast = document.getElementById('watchlist-alert-banner');
    if (toast) toast.classList.remove('active');
  }

  incrementAlertCounter() {
    this.activeAlertCount++;
    const badge = document.getElementById('active-alerts-count');
    if (badge) badge.textContent = this.activeAlertCount;
  }

  setupEventListeners() {
    // Filter chips
    document.querySelectorAll('.filter-chip').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.currentFilter = e.target.getAttribute('data-filter') || 'all';
      });
    });

    // Mute toggle button
    const muteBtn = document.getElementById('btn-toggle-sound');
    if (muteBtn) {
      muteBtn.addEventListener('click', () => {
        this.isMuted = !this.isMuted;
        muteBtn.innerHTML = this.isMuted ? '🔇' : '🔔';
        muteBtn.title = this.isMuted ? 'Audio Alerts Muted' : 'Audio Alerts Active';
      });
    }

    // Dismiss button on alert toast
    const dismissBtn = document.getElementById('btn-toast-dismiss');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', () => this.dismissAlertToast());
    }
  }
}

window.SurveillanceStream = SurveillanceStream;
