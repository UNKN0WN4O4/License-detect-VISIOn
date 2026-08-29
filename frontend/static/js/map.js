/**
 * GIS City Map & Vehicle Trajectory Replay Module
 * BEL / City Traffic Operations Command Center
 */

class CityGISMap {
  constructor() {
    this.map = null;
    this.cameraMarkers = new Map();
    this.cameraLayerGroup = L.layerGroup();
    this.trajectoryLayerGroup = L.layerGroup();
    this.heatLayer = null;
    this.vehicleMarker = null;

    // Active trajectory state
    this.activeTrajectory = null;
    this.playback = {
      isPlaying: false,
      progress: 0, // 0 to 1
      speedMultiplier: 1.0,
      animFrameId: null,
      lastTimestamp: null,
      durationMs: 18000 // total replay animation duration
    };

    // Camera Node Database (Delhi-NCR / Cyber City Corridor)
    this.cameras = [
      { id: "CAM-01", name: "Cyber Hub North Gate", lat: 28.4986, lng: 77.0878, region: "cyber", status: "normal", fps: 30, resolution: "4K", speedLimit: 60 },
      { id: "CAM-02", name: "MG Road Metro Junction", lat: 28.4796, lng: 77.0802, region: "central", status: "moderate", fps: 25, resolution: "1080p", speedLimit: 50 },
      { id: "CAM-03", name: "IFFCO Chowk Flyover", lat: 28.4721, lng: 77.0689, region: "central", status: "congested", fps: 30, resolution: "4K", speedLimit: 70 },
      { id: "CAM-04", name: "Golf Course Extn Road", lat: 28.4184, lng: 77.0945, region: "cyber", status: "normal", fps: 30, resolution: "4K", speedLimit: 65 },
      { id: "CAM-05", name: "Kherki Daula Toll Plaza", lat: 28.3842, lng: 76.9934, region: "expressway", status: "congested", fps: 30, resolution: "4K", speedLimit: 40 },
      { id: "CAM-06", name: "IGI Airport Expressway North", lat: 28.5562, lng: 77.1000, region: "expressway", status: "normal", fps: 30, resolution: "4K", speedLimit: 80 },
      { id: "CAM-07", name: "Ring Road - Dhaula Kuan", lat: 28.5912, lng: 77.1615, region: "ringroad", status: "moderate", fps: 30, resolution: "1080p", speedLimit: 60 },
      { id: "CAM-08", name: "AIIMS South Extn Crossing", lat: 28.5672, lng: 77.2100, region: "ringroad", status: "congested", fps: 30, resolution: "4K", speedLimit: 50 },
      { id: "CAM-09", name: "Connaught Place Inner Circle", lat: 28.6315, lng: 77.2167, region: "central", status: "moderate", fps: 30, resolution: "4K", speedLimit: 40 },
      { id: "CAM-10", name: "Noida-Greater Noida Link", lat: 28.5355, lng: 77.3910, region: "expressway", status: "normal", fps: 30, resolution: "4K", speedLimit: 90 },
      { id: "CAM-11", name: "Shankar Chowk Cloverleaf", lat: 28.5028, lng: 77.0898, region: "cyber", status: "moderate", fps: 30, resolution: "4K", speedLimit: 60 },
      { id: "CAM-12", name: "Sohna Road Badshahpur", lat: 28.3965, lng: 77.0520, region: "central", status: "normal", fps: 25, resolution: "1080p", speedLimit: 60 }
    ];

    // Mock Recent Detections for Cameras
    this.mockDetections = {
      "CAM-01": [
        { plate: "HR26DQ5551", time: "10:14:22", type: "Sedan (White)", conf: "99.4%" },
        { plate: "DL03CC8899", time: "10:13:50", type: "SUV (Black)", conf: "98.7%" },
        { plate: "HR29AZ1234", time: "10:12:10", type: "Hatchback (Silver)", conf: "99.1%" },
        { plate: "UP16BN4422", time: "10:11:05", type: "EV Cab (Blue)", conf: "97.8%" },
        { plate: "MH02CB4040", time: "10:09:40", type: "Luxury Sedan", conf: "99.6%" }
      ],
      "CAM-03": [
        { plate: "HR26DQ5551", time: "10:22:15", type: "Sedan (White)", conf: "99.2%" },
        { plate: "DL01AB9999", time: "10:21:40", type: "Truck (Commercial)", conf: "96.5%" },
        { plate: "HR51AU7711", time: "10:20:00", type: "SUV (Grey)", conf: "98.9%" }
      ]
    };

    // Preloaded Trajectories for instant search demo
    this.trajectoriesDatabase = {
      "HR26DQ5551": {
        plate: "HR26DQ5551",
        vehicle: "Hyundai Verna (Polar White)",
        owner: "R. Sharma / TechCorp Fleet",
        status: "TRACKED - ACTIVE",
        isWatchlist: false,
        hops: [
          { camId: "CAM-06", camName: "IGI Airport Expressway North", time: "10:02:14", speed: "78 km/h", lat: 28.5562, lng: 77.1000 },
          { camId: "CAM-01", camName: "Cyber Hub North Gate", time: "10:14:22", speed: "64 km/h", lat: 28.4986, lng: 77.0878 },
          { camId: "CAM-11", camName: "Shankar Chowk Cloverleaf", time: "10:17:45", speed: "52 km/h", lat: 28.5028, lng: 77.0898 },
          { camId: "CAM-02", camName: "MG Road Metro Junction", time: "10:20:05", speed: "48 km/h", lat: 28.4796, lng: 77.0802 },
          { camId: "CAM-03", camName: "IFFCO Chowk Flyover", time: "10:25:30", speed: "62 km/h", lat: 28.4721, lng: 77.0689 },
          { camId: "CAM-04", camName: "Golf Course Extn Road", time: "10:34:10", speed: "58 km/h", lat: 28.4184, lng: 77.0945 }
        ],
        totalDistance: "21.4 km",
        avgSpeed: "60.3 km/h",
        travelDuration: "31m 56s",
        violations: 0
      },
      "DL01AB1234": {
        plate: "DL01AB1234",
        vehicle: "Toyota Fortuner (Phantom Black)",
        owner: "UNKNOWN - STOLEN REPORT #4092",
        status: "ALERT: CRITICAL WATCHLIST",
        isWatchlist: true,
        alertReason: "Stolen Vehicle / Fast Corridor Breach",
        hops: [
          { camId: "CAM-09", camName: "Connaught Place Inner Circle", time: "09:45:10", speed: "42 km/h", lat: 28.6315, lng: 77.2167 },
          { camId: "CAM-08", camName: "AIIMS South Extn Crossing", time: "09:56:30", speed: "55 km/h", lat: 28.5672, lng: 77.2100 },
          { camId: "CAM-07", camName: "Ring Road - Dhaula Kuan", time: "10:08:12", speed: "74 km/h", lat: 28.5912, lng: 77.1615 },
          { camId: "CAM-06", camName: "IGI Airport Expressway North", time: "10:19:40", speed: "92 km/h", lat: 28.5562, lng: 77.1000 },
          { camId: "CAM-01", camName: "Cyber Hub North Gate", time: "10:30:15", speed: "84 km/h", lat: 28.4986, lng: 77.0878 }
        ],
        totalDistance: "29.8 km",
        avgSpeed: "69.4 km/h",
        travelDuration: "45m 05s",
        violations: 3
      },
      "KA03MG8899": {
        plate: "KA03MG8899",
        vehicle: "Tata Nexon EV (Daytona Grey)",
        owner: "S. Varma / Green Logistics",
        status: "TRACKED - NORMAL",
        isWatchlist: false,
        hops: [
          { camId: "CAM-12", camName: "Sohna Road Badshahpur", time: "10:10:00", speed: "45 km/h", lat: 28.3965, lng: 77.0520 },
          { camId: "CAM-05", camName: "Kherki Daula Toll Plaza", time: "10:18:20", speed: "38 km/h", lat: 28.3842, lng: 76.9934 },
          { camId: "CAM-03", camName: "IFFCO Chowk Flyover", time: "10:32:45", speed: "65 km/h", lat: 28.4721, lng: 77.0689 }
        ],
        totalDistance: "14.6 km",
        avgSpeed: "49.3 km/h",
        travelDuration: "22m 45s",
        violations: 0
      }
    };
  }

  init() {
    // Center around Delhi-NCR / Cyber City Corridor
    this.map = L.map('gis-map', {
      center: [28.4850, 77.0800],
      zoom: 12,
      zoomControl: false,
      attributionControl: false
    });

    // Custom Dark Tiles (CartoDB Dark Matter via Fastly CDN - no watermark)
    L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png', {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }).addTo(this.map);


    // Zoom control at bottom right
    L.control.zoom({ position: 'bottomright' }).addTo(this.map);

    // Add Layer Groups
    this.cameraLayerGroup.addTo(this.map);
    this.trajectoryLayerGroup.addTo(this.map);

    // Render Camera Nodes
    this.renderCameraNodes();

    // Setup Heatmap Layer
    this.initHeatmapLayer();

    // Setup Event Listeners
    this.setupControls();

    // Init live WebSocket for real-time alerts
    this.initWebSocket();

    // Load default demo trajectory
    this.loadTrajectory("HR26DQ5551");
  }

  renderCameraNodes() {
    this.cameraLayerGroup.clearLayers();
    this.cameraMarkers.clear();

    this.cameras.forEach(cam => {
      const colorClass = cam.status === 'normal' ? 'green' : cam.status === 'moderate' ? 'amber' : 'red';
      
      const customIcon = L.divIcon({
        className: 'camera-pulse-icon',
        html: `<div class="camera-pulse-dot ${colorClass}" title="${cam.name}"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
      });

      const marker = L.marker([cam.lat, cam.lng], { icon: customIcon });

      marker.bindPopup(() => this.createCameraPopupHtml(cam), {
        maxWidth: 320,
        className: 'custom-cam-popup'
      });

      marker.addTo(this.cameraLayerGroup);
      this.cameraMarkers.set(cam.id, marker);
    });
  }

  createCameraPopupHtml(cam) {
    const detections = this.mockDetections[cam.id] || [
      { plate: "HR26DQ5551", time: "10:14:22", type: "Sedan (White)", conf: "99.4%" },
      { plate: "DL09CD3344", time: "10:12:11", type: "SUV (Black)", conf: "98.1%" },
      { plate: "UP14AK7722", time: "10:08:45", type: "Commercial Van", conf: "97.5%" },
      { plate: "KA03MG8899", time: "10:05:00", type: "EV Taxi", conf: "99.0%" },
      { plate: "HR10X1001", time: "09:59:30", type: "Motorcycle", conf: "95.8%" }
    ];

    const detectionsRows = detections.map(d => `
      <div class="popup-detection-row">
        <span class="popup-plate-mini">${d.plate}</span>
        <span style="color: var(--text-secondary);">${d.type}</span>
        <span style="font-family: var(--font-mono); color: var(--accent-cyan);">${d.time}</span>
        <button class="mini-action-btn" onclick="window.cityMap.loadTrajectory('${d.plate}')" style="padding: 1px 5px; font-size: 0.65rem;">Track</button>
      </div>
    `).join('');

    return `
      <div class="cam-popup-hud">
        <div class="cam-popup-header">
          <div>
            <div class="cam-popup-title">${cam.id}: ${cam.name}</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); font-family: var(--font-mono);">
              LAT: ${cam.lat.toFixed(4)} | LNG: ${cam.lng.toFixed(4)}
            </div>
          </div>
          <span class="cam-popup-status ${cam.status}">${cam.status}</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-secondary); font-family: var(--font-mono);">
          <span>FPS: ${cam.fps} | RES: ${cam.resolution}</span>
          <span>SPEED LIMIT: ${cam.speedLimit} km/h</span>
        </div>
        <div style="font-size: 0.72rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; margin-top: 4px;">
          Recent 5 Detections (AI OCR)
        </div>
        <div class="cam-popup-detections-list">
          ${detectionsRows}
        </div>
      </div>
    `;
  }

  initHeatmapLayer() {
    if (typeof L.heatLayer === 'function') {
      const heatPoints = [];
      this.cameras.forEach(cam => {
        const intensity = cam.status === 'congested' ? 0.95 : cam.status === 'moderate' ? 0.6 : 0.3;
        heatPoints.push([cam.lat, cam.lng, intensity]);
        for (let i = 0; i < 5; i++) {
          const dLat = (Math.random() - 0.5) * 0.015;
          const dLng = (Math.random() - 0.5) * 0.015;
          heatPoints.push([cam.lat + dLat, cam.lng + dLng, intensity * (0.4 + Math.random() * 0.5)]);
        }
      });

      this.heatLayer = L.heatLayer(heatPoints, {
        radius: 35,
        blur: 25,
        maxZoom: 15,
        gradient: { 0.2: '#00f2fe', 0.5: '#10b981', 0.7: '#f59e0b', 1.0: '#ef4444' }
      });
    }
  }

  toggleHeatmap(enabled) {
    if (!this.heatLayer) return;
    if (enabled) {
      this.heatLayer.addTo(this.map);
    } else {
      this.map.removeLayer(this.heatLayer);
    }
  }

  toggleCameras(enabled) {
    if (enabled) {
      this.cameraLayerGroup.addTo(this.map);
    } else {
      this.map.removeLayer(this.cameraLayerGroup);
    }
  }

  initWebSocket() {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host || 'localhost:8000';
      const wsUrl = `${protocol}//${host}/ws/alerts`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        const dot = document.getElementById('ws-status-dot');
        const text = document.getElementById('ws-status-text');
        if (dot) dot.className = 'camera-pulse-dot green';
        if (text) text.textContent = 'WS CONNECTED';
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event_type === 'WATCHLIST_ALERT' || payload.event_type === 'SPEED_ALERT') {
            this.handleLiveAlert(payload);
          }
        } catch (err) {
          console.warn('WS parse error:', err);
        }
      };

      ws.onclose = () => {
        setTimeout(() => this.initWebSocket(), 4000);
      };
    } catch (e) {
      console.warn('WebSocket unavailable:', e);
    }
  }

  handleLiveAlert(payload) {
    const alertData = payload.data;
    if (!alertData) return;

    // Pulse camera node on map
    const marker = this.cameraMarkers.get(alertData.camera_id);
    if (marker) {
      this.map.panTo(marker.getLatLng(), { animate: true, duration: 0.8 });
    }

    // If watchlist alert, auto-load and update trajectory
    if (alertData.is_watchlist_hit) {
      this.loadTrajectory(alertData.plate_number);
    }
  }

  // Load and visualize trajectory for a plate
  async loadTrajectory(plateNumber) {
    const plate = plateNumber.toUpperCase().trim();
    
    // Attempt backend API fetch
    try {
      const resp = await fetch(`/api/v1/trajectories/${plate}`);
      if (resp.ok) {
        const apiData = await resp.json();
        if (apiData.found && apiData.hops && apiData.hops.length > 0) {
          this.trajectoriesDatabase[plate] = apiData;
        }
      }
    } catch (err) {
      // Backend offline, fallback to cached or synthetic
    }

    let data = this.trajectoriesDatabase[plate];

    // If custom/arbitrary plate queried, synthesize a realistic multi-cam corridor
    if (!data) {
      const randomCams = [...this.cameras].sort(() => 0.5 - Math.random()).slice(0, 5);
      data = {
        plate: plate,
        vehicle: "Private Vehicle (Classified)",
        owner: "Regional Transport Record Verified",
        status: "TRACKED - QUERY MATCH",
        isWatchlist: false,
        hops: randomCams.map((c, idx) => ({
          camId: c.id,
          camName: c.name,
          time: `10:${10 + idx * 4}:${Math.floor(10 + Math.random() * 45)}`,
          speed: `${Math.floor(45 + Math.random() * 35)} km/h`,
          lat: c.lat,
          lng: c.lng
        })),
        totalDistance: "18.2 km",
        avgSpeed: "56.8 km/h",
        travelDuration: "28m 10s",
        violations: 0
      };
      this.trajectoriesDatabase[plate] = data;
    }

    this.activeTrajectory = data;
    this.renderTrajectoryOnMap(data);
    this.updateInspectorSidebar(data);
    this.resetPlayback();

    // Fly to first hop
    if (data.hops.length > 0) {
      const bounds = L.latLngBounds(data.hops.map(h => [h.lat, h.lng]));
      this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
    }
  }

  renderTrajectoryOnMap(data) {
    this.trajectoryLayerGroup.clearLayers();

    const latLngs = data.hops.map(h => [h.lat, h.lng]);

    // 1. Glowing background polyline
    const glowLine = L.polyline(latLngs, {
      color: data.isWatchlist ? '#ef4444' : '#00f2fe',
      weight: 8,
      opacity: 0.35,
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(this.trajectoryLayerGroup);

    // 2. Animated dashed neon core line
    const coreLine = L.polyline(latLngs, {
      color: data.isWatchlist ? '#ff4d4d' : '#ffffff',
      weight: 3,
      opacity: 0.9,
      dashArray: '8, 8',
      className: 'animated-trajectory-line'
    }).addTo(this.trajectoryLayerGroup);

    // 3. Numbered waypoint pins at each hop
    data.hops.forEach((hop, index) => {
      const nodeIndex = index + 1;
      const waypointIcon = L.divIcon({
        className: 'waypoint-marker-container',
        html: `
          <div class="waypoint-node-pin ${index === 0 ? 'active' : ''}" id="wp-pin-${index}">
            ${nodeIndex}
          </div>
        `,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });

      const wpMarker = L.marker([hop.lat, hop.lng], { icon: waypointIcon });
      wpMarker.bindTooltip(`
        <div style="font-family: var(--font-mono); font-size: 0.78rem; color: #fff;">
          <b style="color: var(--accent-cyan);">Hop #${nodeIndex}: ${hop.camName}</b><br/>
          Arrival: ${hop.time} | Speed: ${hop.speed}
        </div>
      `, { direction: 'top', offset: [0, -10] });

      wpMarker.addTo(this.trajectoryLayerGroup);
    });

    // 4. Moving Vehicle Marker
    const vehicleIcon = L.divIcon({
      className: 'vehicle-marker-wrapper',
      html: `
        <svg class="vehicle-marker-icon" id="live-vehicle-svg" width="36" height="36" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="20" fill="rgba(0, 242, 254, 0.2)" stroke="#00f2fe" stroke-width="2"/>
          <path d="M24 10L32 32L24 27L16 32L24 10Z" fill="#00f2fe" stroke="#ffffff" stroke-width="1.5"/>
          <circle cx="24" cy="24" r="3" fill="#ffffff"/>
        </svg>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    this.vehicleMarker = L.marker([data.hops[0].lat, data.hops[0].lng], {
      icon: vehicleIcon,
      zIndexOffset: 1000
    }).addTo(this.trajectoryLayerGroup);
  }

  updateInspectorSidebar(data) {
    const card = document.getElementById('target-summary-card');
    if (!card) return;

    if (data.isWatchlist) {
      card.classList.add('alert-flagged');
    } else {
      card.classList.remove('alert-flagged');
    }

    document.getElementById('inspector-plate').textContent = data.plate;
    document.getElementById('inspector-status').textContent = data.status;
    document.getElementById('inspector-status').className = `target-status-tag ${data.isWatchlist ? 'watchlist' : 'tracked'}`;
    document.getElementById('inspector-vehicle').textContent = data.vehicle;
    document.getElementById('inspector-owner').textContent = data.owner;
    document.getElementById('inspector-distance').textContent = data.totalDistance;
    document.getElementById('inspector-avg-speed').textContent = data.avgSpeed;
    document.getElementById('inspector-duration').textContent = data.travelDuration;
    document.getElementById('inspector-violations').textContent = `${data.violations} Detected`;

    // Render Hops list
    const hopsContainer = document.getElementById('timeline-hops-list');
    if (!hopsContainer) return;

    hopsContainer.innerHTML = data.hops.map((h, i) => `
      <div class="hop-item ${i === 0 ? 'active' : ''}" id="hop-item-${i}" onclick="window.cityMap.jumpToHop(${i})">
        <div class="hop-node-index">${i + 1}</div>
        <div class="hop-content">
          <div class="hop-cam-name">
            <span>${h.camName}</span>
            <span class="hop-speed-badge">${h.speed}</span>
          </div>
          <div class="hop-timestamp">DETECTED: ${h.time}</div>
        </div>
      </div>
    `).join('');

    // Update bottom replay telemetry plate
    const replayPlate = document.getElementById('replay-plate-tag');
    if (replayPlate) replayPlate.textContent = data.plate;
  }

  // =========================================================================
  // Trajectory Timeline Playback & Animation
  // =========================================================================
  resetPlayback() {
    this.playback.isPlaying = false;
    this.playback.progress = 0;
    if (this.playback.animFrameId) {
      cancelAnimationFrame(this.playback.animFrameId);
      this.playback.animFrameId = null;
    }
    const playBtn = document.getElementById('btn-play-pause');
    if (playBtn) playBtn.innerHTML = '&#9658;'; // Play icon
    this.updateVehiclePositionAtProgress(0);
    const slider = document.getElementById('replay-slider');
    if (slider) slider.value = 0;
  }

  togglePlayPause() {
    if (!this.activeTrajectory || this.activeTrajectory.hops.length < 2) return;

    this.playback.isPlaying = !this.playback.isPlaying;
    const playBtn = document.getElementById('btn-play-pause');

    if (this.playback.isPlaying) {
      if (playBtn) playBtn.innerHTML = '&#10074;&#10074;'; // Pause icon
      this.playback.lastTimestamp = performance.now();
      this.animateStep(performance.now());
    } else {
      if (playBtn) playBtn.innerHTML = '&#9658;'; // Play icon
      if (this.playback.animFrameId) {
        cancelAnimationFrame(this.playback.animFrameId);
      }
    }
  }

  animateStep(timestamp) {
    if (!this.playback.isPlaying) return;

    const delta = timestamp - this.playback.lastTimestamp;
    this.playback.lastTimestamp = timestamp;

    const effectiveDuration = this.playback.durationMs / this.playback.speedMultiplier;
    this.playback.progress += delta / effectiveDuration;

    if (this.playback.progress >= 1.0) {
      this.playback.progress = 1.0;
      this.playback.isPlaying = false;
      const playBtn = document.getElementById('btn-play-pause');
      if (playBtn) playBtn.innerHTML = '&#9658;';
    }

    this.updateVehiclePositionAtProgress(this.playback.progress);

    const slider = document.getElementById('replay-slider');
    if (slider) slider.value = Math.floor(this.playback.progress * 100);

    if (this.playback.isPlaying) {
      this.playback.animFrameId = requestAnimationFrame(ts => this.animateStep(ts));
    }
  }

  setPlaybackProgress(progressFraction) {
    this.playback.progress = Math.max(0, Math.min(1, progressFraction));
    this.updateVehiclePositionAtProgress(this.playback.progress);
  }

  updateVehiclePositionAtProgress(progress) {
    if (!this.activeTrajectory || !this.vehicleMarker) return;

    const hops = this.activeTrajectory.hops;
    const numSegments = hops.length - 1;
    if (numSegments <= 0) return;

    const scaledProgress = progress * numSegments;
    const currentSegmentIndex = Math.min(Math.floor(scaledProgress), numSegments - 1);
    const segmentProgress = scaledProgress - currentSegmentIndex;

    const startHop = hops[currentSegmentIndex];
    const endHop = hops[currentSegmentIndex + 1];

    // Linear Interpolation for Lat/Lng
    const currentLat = startHop.lat + (endHop.lat - startHop.lat) * segmentProgress;
    const currentLng = startHop.lng + (endHop.lng - startHop.lng) * segmentProgress;

    // Calculate Bearing Angle (degrees)
    const y = Math.sin((endHop.lng - startHop.lng) * Math.PI / 180) * Math.cos(endHop.lat * Math.PI / 180);
    const x = Math.cos(startHop.lat * Math.PI / 180) * Math.sin(endHop.lat * Math.PI / 180) -
              Math.sin(startHop.lat * Math.PI / 180) * Math.cos(endHop.lat * Math.PI / 180) * Math.cos((endHop.lng - startHop.lng) * Math.PI / 180);
    const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;

    this.vehicleMarker.setLatLng([currentLat, currentLng]);

    // Rotate vehicle icon
    const iconElem = document.getElementById('live-vehicle-svg');
    if (iconElem) {
      iconElem.style.transform = `rotate(${bearing}deg)`;
    }

    // Highlight active hop in sidebar
    document.querySelectorAll('.hop-item').forEach((elem, idx) => {
      if (idx === currentSegmentIndex) {
        elem.classList.add('active');
      } else {
        elem.classList.remove('active');
      }
    });

    // Update Telemetry display in bottom bar
    const teleTime = document.getElementById('replay-current-time');
    const teleSpeed = document.getElementById('replay-current-speed');
    const teleCam = document.getElementById('replay-current-cam');

    if (teleTime) teleTime.textContent = startHop.time;
    if (teleSpeed) teleSpeed.textContent = startHop.speed;
    if (teleCam) teleCam.textContent = startHop.camName;
  }

  jumpToHop(index) {
    if (!this.activeTrajectory) return;
    const hops = this.activeTrajectory.hops;
    if (index >= 0 && index < hops.length) {
      const fraction = index / (hops.length - 1);
      this.setPlaybackProgress(fraction);
      const slider = document.getElementById('replay-slider');
      if (slider) slider.value = Math.floor(fraction * 100);
      this.map.panTo([hops[index].lat, hops[index].lng], { animate: true, duration: 0.5 });
    }
  }

  flyToRegion(region) {
    const coords = {
      cyber: { center: [28.4986, 77.0878], zoom: 14 },
      central: { center: [28.4721, 77.0689], zoom: 13 },
      expressway: { center: [28.5562, 77.1000], zoom: 13 },
      ringroad: { center: [28.5800, 77.1800], zoom: 13 }
    };
    const target = coords[region] || coords.cyber;
    this.map.flyTo(target.center, target.zoom, { duration: 1.2 });
  }

  setupControls() {
    // Replay buttons
    const playBtn = document.getElementById('btn-play-pause');
    if (playBtn) playBtn.addEventListener('click', () => this.togglePlayPause());

    const prevBtn = document.getElementById('btn-step-back');
    if (prevBtn) prevBtn.addEventListener('click', () => {
      const cur = this.playback.progress;
      this.setPlaybackProgress(Math.max(0, cur - 0.2));
    });

    const nextBtn = document.getElementById('btn-step-fwd');
    if (nextBtn) nextBtn.addEventListener('click', () => {
      const cur = this.playback.progress;
      this.setPlaybackProgress(Math.min(1, cur + 0.2));
    });

    const slider = document.getElementById('replay-slider');
    if (slider) {
      slider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value) / 100;
        this.setPlaybackProgress(val);
      });
    }

    const speedSelect = document.getElementById('replay-speed-select');
    if (speedSelect) {
      speedSelect.addEventListener('change', (e) => {
        this.playback.speedMultiplier = parseFloat(e.target.value);
      });
    }

    // Map Layer Toggles
    const heatCheck = document.getElementById('toggle-heatmap');
    if (heatCheck) {
      heatCheck.addEventListener('change', (e) => this.toggleHeatmap(e.target.checked));
    }

    const camsCheck = document.getElementById('toggle-cameras');
    if (camsCheck) {
      camsCheck.addEventListener('change', (e) => this.toggleCameras(e.target.checked));
    }
  }
}

// Global instance exposure
window.CityGISMap = CityGISMap;
