/**
 * Live Surveillance Feed, WebSocket Stream & Watchlist Alert Engine
 * BEL / City Traffic Operations Command Center
 */

class SurveillanceStream {
  constructor() {
    this.socket = null;
    this.isMuted = false;
    this.audioCtx = null;
    this.currentFilter = 'all'; // 'all', 'alerts', 'speeding'
    this.feedContainer = null;
    this.activeAlertCount = 3;
    this.simTimer = null;
    this.allDetections = [];

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
      { plate: "DL01AB1234", camId: "CAM-06", camName: "IGI Airport Expressway North", type: "Toyota Fortuner (Black)", speed: "94 km/h", isWatchlist: true, reason: "Reported Stolen (FIR #4092)" },
      { plate: "HR29AZ1234", camId: "CAM-03", camName: "IFFCO Chowk Flyover", type: "Hatchback (Silver)", speed: "68 km/h", isWatchlist: false },
      { plate: "UP16BN4422", camId: "CAM-04", camName: "Golf Course Extn Rd", type: "EV Cab (Blue)", speed: "82 km/h", isWatchlist: false },
      { plate: "HR26CY9999", camId: "CAM-05", camName: "Kherki Daula Toll", type: "Heavy Truck", speed: "78 km/h", isWatchlist: true, reason: "Multiple Toll Violations" },
      { plate: "MH02CB4040", camId: "CAM-07", camName: "Ring Road - Dhaula Kuan", type: "Luxury Sedan", speed: "88 km/h", isWatchlist: false },
      { plate: "KA03MG8899", camId: "CAM-12", camName: "Sohna Road Badshahpur", type: "EV SUV", speed: "48 km/h", isWatchlist: false },
      { plate: "UP16EF7788", camId: "CAM-03", camName: "IFFCO Chowk Flyover", type: "Commercial Tanker", speed: "62 km/h", isWatchlist: true, reason: "Banned Corridor Transit" },
      { plate: "DL08AK1122", camId: "CAM-08", camName: "AIIMS South Extn", type: "Two-Wheeler", speed: "42 km/h", isWatchlist: false },
      { plate: "HR10X1001", camId: "CAM-06", camName: "IGI Airport Expressway North", type: "Motorcycle (Sports)", speed: "102 km/h", isWatchlist: false }
    ];
  }

  init() {
    this.feedContainer = document.getElementById('live-detections-feed');
    this.setupAudio();
    this.seedInitialDetections();
    this.setupEventListeners();
    this.connectWebSocket();
  }

  seedInitialDetections() {
    const now = new Date();
    this.allDetections = this.samplePlates.map((item, idx) => {
      const pastTime = new Date(now.getTime() - idx * 45000);
      const timeStr = pastTime.toTimeString().split(' ')[0];
      const isWatchlistHit = item.isWatchlist || this.watchlist.has(item.plate);
      const alertInfo = isWatchlistHit ? (this.watchlist.get(item.plate) || { reason: item.reason || "Hotlist Vehicle", level: "red" }) : null;
      return {
        ...item,
        timestamp: timeStr,
        id: `det_seed_${idx}_${Date.now()}`,
        isWatchlist: isWatchlistHit,
        alertInfo: alertInfo
      };
    });
    this.renderFeed();
  }

  parseSpeed(speedVal) {
    if (typeof speedVal === 'number') return speedVal;
    if (!speedVal) return 50;
    const match = String(speedVal).match(/\d+/);
    return match ? parseInt(match[0], 10) : 50;
  }

  isItemMatchingFilter(item, filter) {
    if (filter === 'all') return true;
    if (filter === 'alerts') {
      return Boolean(item.isWatchlist || this.watchlist.has(item.plate));
    }
    if (filter === 'speeding') {
      return this.parseSpeed(item.speed) >= 75;
    }
    return true;
  }

  setFilter(filter) {
    this.currentFilter = filter;
    document.querySelectorAll('.filter-chip').forEach(btn => {
      if (btn.getAttribute('data-filter') === filter) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    this.renderFeed();
  }

  renderFeed() {
    if (!this.feedContainer) return;
    this.feedContainer.innerHTML = '';

    const filtered = this.allDetections.filter(d => this.isItemMatchingFilter(d, this.currentFilter));

    if (filtered.length === 0) {
      const filterLabel = this.currentFilter === 'alerts' ? 'Hotlist Alerts' : this.currentFilter === 'speeding' ? 'Speeding (> 75 km/h)' : 'All Traffic';
      this.feedContainer.innerHTML = `
        <div style="text-align: center; padding: 40px 15px; color: var(--text-muted); font-family: var(--font-mono); font-size: 0.8rem;">
          <div style="font-size: 1.8rem; margin-bottom: 8px;">📡</div>
          <div style="color: var(--text-secondary); font-weight: 700;">No ${filterLabel} detections</div>
          <div style="font-size: 0.72rem; margin-top: 4px;">Live telemetry stream buffer is monitoring...</div>
        </div>
      `;
      return;
    }

    filtered.slice(0, 35).forEach(data => {
      const card = this.createDetectionCardElement(data);
      this.feedContainer.appendChild(card);
    });
  }

  createDetectionCardElement(data) {
    const isWatchlist = Boolean(data.isWatchlist || this.watchlist.has(data.plate));
    const alertInfo = data.alertInfo || (isWatchlist ? (this.watchlist.get(data.plate) || { reason: data.reason || "Hotlist Vehicle", level: "red" }) : null);

    const card = document.createElement('div');
    card.className = `detection-card ${isWatchlist ? 'flagged-alert' : ''}`;
    card.id = `det-card-${data.id || Date.now()}`;

    const plateSvg = this.createPlateSvgDataUri(data.plate);
    const speedNum = this.parseSpeed(data.speed);
    const speedColor = speedNum >= 75 ? 'var(--accent-red)' : 'var(--accent-cyan)';

    card.innerHTML = `
      <div class="detection-top-row">
        <span class="detected-plate">${data.plate}</span>
        <span class="detection-cam-badge">${data.camName || data.camId}</span>
      </div>
      <div class="detection-media-row">
        <img class="detection-crop-img" src="${plateSvg}" alt="Plate Crop" />
        <div class="detection-info">
          <span class="detection-veh-type">${data.type || 'Passenger Vehicle'}</span>
          <span class="detection-time">TIME: ${data.timestamp || 'JUST NOW'} | SPEED: <b style="color: ${speedColor};">${data.speed || (speedNum + ' km/h')}</b></span>
          ${isWatchlist && alertInfo ? `<span style="color: var(--accent-red); font-size: 0.72rem; font-weight: 700;">⚠️ ${alertInfo.reason}</span>` : ''}
        </div>
      </div>
      <div class="detection-card-actions">
        <button class="mini-action-btn track-btn" onclick="window.cityMap.loadTrajectory('${data.plate}')">
          📍 Track Trajectory
        </button>
      </div>
    `;
    return card;
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
      osc1.frequency.setValueAtTime(880, this.audioCtx.currentTime);
      osc1.frequency.exponentialRampToValueAtTime(440, this.audioCtx.currentTime + 0.3);
      osc2.frequency.setValueAtTime(1174, this.audioCtx.currentTime);
      osc2.frequency.exponentialRampToValueAtTime(587, this.audioCtx.currentTime + 0.3);
    } else {
      osc1.frequency.setValueAtTime(523.25, this.audioCtx.currentTime);
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

    // Feed a new detection every 3.2 seconds
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
    const isWatchlistHit = Boolean(data.isWatchlist || this.watchlist.has(data.plate));
    const alertInfo = isWatchlistHit ? (this.watchlist.get(data.plate) || { reason: data.reason || "Hotlist Vehicle", level: "red" }) : null;

    const enriched = {
      ...data,
      isWatchlist: isWatchlistHit,
      alertInfo: alertInfo,
      id: data.id || `det_${Date.now()}_${Math.floor(Math.random() * 1000)}`
    };

    // Store in all detections list
    this.allDetections.unshift(enriched);
    if (this.allDetections.length > 100) {
      this.allDetections.pop();
    }

    if (isWatchlistHit) {
      this.triggerWatchlistToast(enriched, alertInfo);
      this.playAlertChime('danger');
      this.incrementAlertCounter();
    }

    // If matches active filter, prepend to DOM smoothly
    if (this.isItemMatchingFilter(enriched, this.currentFilter)) {
      if (!this.feedContainer) return;
      
      // If empty notice is showing, clear it first
      if (this.feedContainer.querySelector('.empty-feed-hud') || this.feedContainer.children.length === 1 && !this.feedContainer.children[0].classList.contains('detection-card')) {
        this.feedContainer.innerHTML = '';
      }

      const card = this.createDetectionCardElement(enriched);
      this.feedContainer.insertBefore(card, this.feedContainer.firstChild);

      // Keep max 35 cards in DOM
      if (this.feedContainer.children.length > 35) {
        this.feedContainer.removeChild(this.feedContainer.lastChild);
      }
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
    // Filter chips - delegate on click
    document.querySelectorAll('.filter-chip').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const chip = e.currentTarget;
        const filterType = chip.getAttribute('data-filter') || 'all';
        this.setFilter(filterType);
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

