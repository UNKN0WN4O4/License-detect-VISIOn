/**
 * God's Eye View - 3D Spatial Intelligence & Spy Satellite Surveillance Module
 * Inspired by bilawalsidhu/gods-eye-view
 * 
 * Features:
 * - High-fidelity 3D Globe with Photorealistic Satellite Imagery & 3D City Buildings
 * - 3D Volumetric Camera Sensor Cones (ANPR Field-of-View Frustums)
 * - 3D Neon Glowing Trajectory Ribbons & Vehicle Entity with Real-time Heading
 * - Satellite Lock-on Chase Camera & Cinematic Pursuit Modes
 * - Tactical Spy Satellite HUD (Orbital Telemetry, Azimuth, Pitch, Altitude, Targeting Reticles)
 * - Support for Google Photorealistic 3D Tiles & Cesium World Terrain
 */

class GodsEye3DMap {
  constructor(parentMapController) {
    this.parent = parentMapController; // Reference to CityGISMap
    this.viewer = null;
    this.isInitialized = false;
    this.activeMode = '2D'; // '2D' or '3D'

    // 3D Entities & Collections
    this.cameraNodesCollection = [];
    this.sensorConesCollection = [];
    this.trajectoryEntity = null;
    this.trajectoryPoints = [];
    this.vehicleEntity = null;
    this.targetReticleEntity = null;
    this.google3DTileset = null;
    this.osm3DTileset = null;

    // Satellite Tracking & View Modes
    this.cameraMode = 'tactical'; // 'topdown', 'tactical', 'street', 'chase'
    this.isTrackingVehicle = false;
    this.lastReplayProgress = 0;

    // Default Coordinates (Delhi-NCR / Cyber City Corridor)
    this.defaultCenter = {
      lat: 28.4900,
      lng: 77.0850,
      alt: 2200,
      heading: 25.0,
      pitch: -38.0,
      roll: 0.0
    };

    // Regional 3D Camera Presets
    this.regionViews = {
      cyber: { lat: 28.4986, lng: 77.0878, alt: 950, heading: 35, pitch: -35 },
      central: { lat: 28.4750, lng: 77.0750, alt: 1400, heading: 0, pitch: -42 },
      expressway: { lat: 28.4600, lng: 77.0400, alt: 3200, heading: 15, pitch: -30 },
      ringroad: { lat: 28.5800, lng: 77.1800, alt: 2800, heading: 270, pitch: -35 }
    };
  }

  /**
   * Initialize Cesium 3D Viewer Container
   */
  async init(containerId = 'gods-eye-3d-container') {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error(`3D Container #${containerId} not found.`);
      return;
    }

    // Set Cesium base URL
    window.CESIUM_BASE_URL = 'https://unpkg.com/cesium@1.114.0/Build/Cesium/';

    try {
      // 1. Initialize Cesium Viewer without baseLayerPicker
      this.viewer = new Cesium.Viewer(containerId, {
        animation: false,
        baseLayerPicker: false,
        fullscreenButton: false,
        geocoder: false,
        homeButton: false,
        infoBox: false,
        sceneModePicker: false,
        selectionIndicator: false,
        timeline: false,
        navigationHelpButton: false,
        navigationInstructionsInitiallyVisible: false,
        scene3DOnly: true,
        shadows: false,
        baseLayer: false
      });

      // 2. Add Photorealistic Satellite Imagery & Reference Roads/Labels
      this.initImageryLayers('satellite');

      // 3. Globe Tuning: NEVER pitch black at night, bright daylight illumination 24/7
      const scene = this.viewer.scene;
      scene.globe.show = true;
      scene.globe.enableLighting = false; // CRITICAL: false so the map is never black during nighttime
      scene.globe.depthTestAgainstTerrain = false;
      scene.globe.baseColor = Cesium.Color.fromCssColorString('#0f172a');
      scene.backgroundColor = Cesium.Color.fromCssColorString('#030712');
      
      // High-DPI & Anti-aliasing
      scene.postProcessStages.fxaa.enabled = true;
      if (Cesium.FeatureDetection.supportsImageRenderingPixelated()) {
        this.viewer.resolutionScale = window.devicePixelRatio || 1.0;
      }

      // Hide default Cesium credit container for clean HUD look
      if (this.viewer.cesiumWidget.creditContainer) {
        this.viewer.cesiumWidget.creditContainer.style.display = 'none';
      }

      // 4. Load 3D City Buildings & Google 3D Tiles (if key configured)
      await this.init3DTiles();

      // 5. Render 3D ANPR Surveillance Nodes & Volumetric Sensor Cones
      this.render3DCameraNodes();

      // 6. Setup Live Orbital Telemetry HUD listeners
      this.setupTelemetryHUD();

      // 7. Setup 3D Click Interaction for Camera Nodes
      this.setupClickHandlers();

      // 8. Fly to default reconnaissance perspective
      this.flyToDefaultView();

      this.isInitialized = true;
      console.log('✅ 3D "God\'s Eye" Spatial Intelligence Engine Initialized');

    } catch (err) {
      console.error('Failed to initialize Cesium 3D viewer:', err);
    }
  }

  /**
   * Initialize or Switch Basemap Imagery Layers
   */
  initImageryLayers(type = 'satellite') {
    if (!this.viewer) return;
    this.viewer.imageryLayers.removeAll();

    if (type === 'satellite') {
      // 1. Esri World Imagery (High-Resolution Real Satellite)
      const satelliteProvider = new Cesium.UrlTemplateImageryProvider({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 19,
        credit: 'Esri World Imagery'
      });
      this.viewer.imageryLayers.addImageryProvider(satelliteProvider);

      // 2. Reference Roads, Highways & Place Names Overlay
      const labelsProvider = new Cesium.UrlTemplateImageryProvider({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 19,
        credit: 'Esri Boundaries'
      });
      this.viewer.imageryLayers.addImageryProvider(labelsProvider);

    } else if (type === 'dark') {
      // CartoDB Dark Matter
      const darkProvider = new Cesium.UrlTemplateImageryProvider({
        url: 'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
        maximumLevel: 19,
        credit: 'CARTO, OpenStreetMap'
      });
      this.viewer.imageryLayers.addImageryProvider(darkProvider);

    } else if (type === 'streets') {
      // OpenStreetMap Standard
      const osmProvider = new Cesium.UrlTemplateImageryProvider({
        url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        maximumLevel: 19,
        credit: 'OpenStreetMap'
      });
      this.viewer.imageryLayers.addImageryProvider(osmProvider);
    }
  }

  /**
   * Initialize 3D City Building Tilesets
   */
  async init3DTiles() {
    const googleApiKey = localStorage.getItem('GODS_EYE_GOOGLE_3D_KEY');
    const cesiumIonToken = localStorage.getItem('GODS_EYE_CESIUM_ION_TOKEN');

    if (cesiumIonToken) {
      Cesium.Ion.defaultAccessToken = cesiumIonToken;
    }

    if (googleApiKey) {
      try {
        console.log('Loading Google Photorealistic 3D Tiles...');
        this.google3DTileset = await Cesium.createGooglePhotorealistic3DTileset({
          key: googleApiKey
        });
        this.viewer.scene.primitives.add(this.google3DTileset);
        const tileStatus = document.getElementById('hud-tile-source');
        if (tileStatus) tileStatus.textContent = 'GOOGLE 3D PHOTOREALISTIC';
        return;
      } catch (err) {
        console.warn('Google 3D Tiles failed, falling back to OSM 3D:', err);
      }
    }

    // Default: OpenStreetMap 3D Buildings / Tactical Cyberpunk shader
    try {
      this.osm3DTileset = await Cesium.createOsmBuildingsAsync({
        style: new Cesium.Cesium3DTileStyle({
          color: {
            conditions: [
              ['${feature["building"]} === "commercial"', 'color("cyan", 0.7)'],
              ['${feature["building"]} === "hospital"', 'color("red", 0.7)'],
              ['true', 'color("#1e293b", 0.85)']
            ]
          }
        })
      });
      this.viewer.scene.primitives.add(this.osm3DTileset);
      const tileStatus = document.getElementById('hud-tile-source');
      if (tileStatus) tileStatus.textContent = 'TACTICAL OSM 3D BUILDINGS';
    } catch (e) {
      console.log('OSM 3D tiles default loaded with globe satellite imagery.');
    }
  }

  /**
   * Fly to default surveillance coordinate
   */
  flyToDefaultView(duration = 2.0) {
    if (!this.viewer) return;
    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(
        this.defaultCenter.lng,
        this.defaultCenter.lat,
        this.defaultCenter.alt
      ),
      orientation: {
        heading: Cesium.Math.toRadians(this.defaultCenter.heading),
        pitch: Cesium.Math.toRadians(this.defaultCenter.pitch),
        roll: Cesium.Math.toRadians(this.defaultCenter.roll)
      },
      duration: duration
    });
  }

  /**
   * Render 3D ANPR Camera Nodes & Volumetric Sensor Cones
   */
  render3DCameraNodes() {
    if (!this.viewer || !this.parent || !this.parent.cameras) return;

    // Clear previous entities
    this.cameraNodesCollection.forEach(entity => this.viewer.entities.remove(entity));
    this.cameraNodesCollection = [];
    this.sensorConesCollection.forEach(entity => this.viewer.entities.remove(entity));
    this.sensorConesCollection = [];

    this.parent.cameras.forEach(cam => {
      const position = Cesium.Cartesian3.fromDegrees(cam.lng, cam.lat, 35);
      const groundPosition = Cesium.Cartesian3.fromDegrees(cam.lng, cam.lat, 0);

      const statusColor = cam.status === 'congested' 
        ? Cesium.Color.fromCssColorString('#ef4444') 
        : cam.status === 'moderate' 
          ? Cesium.Color.fromCssColorString('#f59e0b') 
          : Cesium.Color.fromCssColorString('#00f2fe');

      // 1. 3D Surveillance Tower Pole
      const poleEntity = this.viewer.entities.add({
        name: cam.id,
        polyline: {
          positions: [groundPosition, position],
          width: 2,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.25,
            color: statusColor.withAlpha(0.6)
          })
        }
      });
      this.cameraNodesCollection.push(poleEntity);

      // 2. 3D Camera Node Beacon (Pulsing Point & Label)
      const beaconEntity = this.viewer.entities.add({
        name: `Node: ${cam.id}`,
        position: position,
        cameraData: cam,
        point: {
          pixelSize: 12,
          color: statusColor,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text: `[${cam.id}] ${cam.name}`,
          font: '10px "Share Tech Mono", monospace',
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 5000),
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        }
      });
      this.cameraNodesCollection.push(beaconEntity);

      // 3. 3D Volumetric Sensor Frustum / Cone of Vision
      const coneHeight = 35.0;
      const coneRadius = 25.0;
      const conePosition = Cesium.Cartesian3.fromDegrees(cam.lng, cam.lat, coneHeight / 2);

      const coneEntity = this.viewer.entities.add({
        name: `SensorCone: ${cam.id}`,
        position: conePosition,
        cylinder: {
          length: coneHeight,
          topRadius: 0.0,
          bottomRadius: coneRadius,
          material: statusColor.withAlpha(0.12),
          outline: true,
          outlineColor: statusColor.withAlpha(0.4),
          numberOfVerticalLines: 4
        }
      });
      this.sensorConesCollection.push(coneEntity);
    });
  }

  /**
   * Load and Render 3D Trajectory for a Tracked Target
   */
  render3DTrajectory(data) {
    if (!this.viewer || !data || !data.hops || data.hops.length === 0) return;

    // Remove previous trajectory & vehicle
    if (this.trajectoryEntity) {
      this.viewer.entities.remove(this.trajectoryEntity);
      this.trajectoryEntity = null;
    }
    if (this.vehicleEntity) {
      this.viewer.entities.remove(this.vehicleEntity);
      this.vehicleEntity = null;
    }
    if (this.targetReticleEntity) {
      this.viewer.entities.remove(this.targetReticleEntity);
      this.targetReticleEntity = null;
    }

    const isWatchlist = data.isWatchlist;
    const pathColor = isWatchlist
      ? Cesium.Color.fromCssColorString('#ef4444')
      : Cesium.Color.fromCssColorString('#00f2fe');

    // Build Cartesian positions along real street roadway points (elevated 8m above ground)
    if (data.roadGeometry && data.roadGeometry.points && data.roadGeometry.points.length > 1) {
      this.trajectoryPoints = data.roadGeometry.points.map(p => Cesium.Cartesian3.fromDegrees(p.lng, p.lat, 8));
    } else {
      this.trajectoryPoints = data.hops.map(h => Cesium.Cartesian3.fromDegrees(h.lng, h.lat, 8));
    }

    // 1. 3D Glowing Trajectory Ribbon
    this.trajectoryEntity = this.viewer.entities.add({
      name: `Trajectory: ${data.plate}`,
      polyline: {
        positions: this.trajectoryPoints,
        width: 8,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.4,
          color: pathColor
        }),
        clampToGround: false
      }
    });

    // 2. 3D Waypoint Markers along trajectory
    if (this.waypointEntities) {
      this.waypointEntities.forEach(e => this.viewer.entities.remove(e));
    }
    this.waypointEntities = [];

    data.hops.forEach((h, idx) => {
      const wpPos = Cesium.Cartesian3.fromDegrees(h.lng, h.lat, 18);
      const wpEntity = this.viewer.entities.add({
        name: `Hop-${idx+1}: ${h.camName || h.camId}`,
        position: wpPos,
        point: {
          pixelSize: 10,
          color: pathColor,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text: `[#${idx+1}] ${h.camName || h.camId}\n${h.time} | ${h.speed}`,
          font: '10px "Share Tech Mono", monospace',
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -12),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 10000),
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        }
      });
      this.waypointEntities.push(wpEntity);
    });

    // 3. 3D Target Vehicle Entity
    const startHop = data.hops[0];
    const initialPosition = Cesium.Cartesian3.fromDegrees(startHop.lng, startHop.lat, 10);

    this.vehicleEntity = this.viewer.entities.add({
      name: `Target: ${data.plate}`,
      position: initialPosition,
      point: {
        pixelSize: 18,
        color: isWatchlist ? Cesium.Color.RED : Cesium.Color.CYAN,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 3,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      },
      billboard: {
        image: this.createVehicleSvgIcon(isWatchlist),
        width: 36,
        height: 36,
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      },
      label: {
        text: `🎯 TARGET: ${data.plate}\n${data.vehicle || ''}`,
        font: '12px "Share Tech Mono", monospace',
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        fillColor: isWatchlist ? Cesium.Color.fromCssColorString('#fca5a5') : Cesium.Color.fromCssColorString('#67e8f9'),
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 3,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -26),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    });

    // 4. Update HUD Target Telemetry
    this.updateTargetHUD(data, startHop);

    // 5. Auto-Focus Camera on Trajectory Extent
    this.fitTrajectoryBounds(data.hops);
  }

  /**
   * Helper to create inline SVG vehicle icon
   */
  createVehicleSvgIcon(isAlert = false) {
    const color = isAlert ? '#ef4444' : '#00f2fe';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="12 6 16 14 12 11 8 14 12 6"/></svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  /**
   * Fit 3D Camera to view entire trajectory corridor
   */
  fitTrajectoryBounds(hops) {
    if (!this.viewer || !hops || hops.length === 0) return;

    let minLat = 90, maxLat = -90, minLng = 180, maxLng = -180;
    hops.forEach(h => {
      minLat = Math.min(minLat, h.lat);
      maxLat = Math.max(maxLat, h.lat);
      minLng = Math.min(minLng, h.lng);
      maxLng = Math.max(maxLng, h.lng);
    });

    const centerLat = (minLat + maxLat) / 2;
    const centerLng = (minLng + maxLng) / 2;
    
    // Estimate appropriate altitude based on span
    const spanKm = Math.max(
      Math.abs(maxLat - minLat) * 111,
      Math.abs(maxLng - minLng) * 111
    );
    const altitude = Math.max(1800, spanKm * 1500);

    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(centerLng, centerLat, altitude),
      orientation: {
        heading: Cesium.Math.toRadians(25.0),
        pitch: Cesium.Math.toRadians(-40.0),
        roll: 0.0
      },
      duration: 1.8
    });
  }

  /**
   * Update 3D Vehicle Position during Playback / Scrubber events
   */
  updatePlaybackPosition(progress, currentHop, nextHop, interpolatedPos) {
    if (!this.vehicleEntity || !interpolatedPos) return;

    const vehiclePos = Cesium.Cartesian3.fromDegrees(
      interpolatedPos.lng,
      interpolatedPos.lat,
      8.0
    );

    this.vehicleEntity.position = vehiclePos;

    // Update targeting reticle in HUD
    this.updateScreenTargetReticle(vehiclePos);

    // If "Target Lock" or "Chase Mode" is active, smoothly follow with satellite camera
    if (this.isTrackingVehicle || this.cameraMode === 'chase') {
      const cameraAlt = this.cameraMode === 'chase' ? 450 : 1200;
      const cameraPitch = this.cameraMode === 'chase' ? -25 : -55;

      this.viewer.camera.lookAt(
        vehiclePos,
        new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(interpolatedPos.bearing || 25),
          Cesium.Math.toRadians(cameraPitch),
          cameraAlt
        )
      );
      // Unlock transform so user can still rotate
      this.viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    }
  }

  /**
   * Update Screen Reticle Overlay Position
   */
  updateScreenTargetReticle(cartesianPos) {
    const reticleElem = document.getElementById('spy-target-reticle');
    if (!reticleElem || !this.viewer) return;

    if (this.activeMode !== '3D') {
      reticleElem.style.display = 'none';
      return;
    }

    const canvasPos = Cesium.SceneTransforms.wgs84ToWindowCoordinates(
      this.viewer.scene,
      cartesianPos
    );

    if (canvasPos) {
      reticleElem.style.display = 'block';
      reticleElem.style.transform = `translate(${canvasPos.x}px, ${canvasPos.y}px)`;
    } else {
      reticleElem.style.display = 'none';
    }
  }

  /**
   * Set 3D Camera Perspective Preset
   */
  setCameraPreset(mode, btn) {
    this.cameraMode = mode;
    if (btn) {
      document.querySelectorAll('.sat-cam-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }
    if (!this.viewer) return;

    let targetLat = this.defaultCenter.lat;
    let targetLng = this.defaultCenter.lng;

    if (this.vehicleEntity) {
      const posVal = this.vehicleEntity.position.getValue(Cesium.JulianDate.now());
      if (posVal) {
        const carto = Cesium.Cartographic.fromCartesian(posVal);
        targetLat = Cesium.Math.toDegrees(carto.latitude);
        targetLng = Cesium.Math.toDegrees(carto.longitude);
      }
    }

    if (mode === 'topdown') {
      // Nadiral High-Altitude Spy Satellite
      this.isTrackingVehicle = false;
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(targetLng, targetLat, 3500),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(-89.9),
          roll: 0
        },
        duration: 1.2
      });
    } else if (mode === 'tactical') {
      // 45° Tactical Drone Orbit
      this.isTrackingVehicle = false;
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(targetLng, targetLat - 0.012, 1400),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-45),
          roll: 0
        },
        duration: 1.2
      });
    } else if (mode === 'street') {
      // Low-Altitude CCTV Intercept Level
      this.isTrackingVehicle = false;
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(targetLng, targetLat - 0.003, 320),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-22),
          roll: 0
        },
        duration: 1.2
      });
    } else if (mode === 'chase') {
      // Lock-On Pursuit Mode
      this.isTrackingVehicle = true;
    }
  }

  /**
   * Setup Live Telemetry HUD calculation
   */
  setupTelemetryHUD() {
    if (!this.viewer) return;

    const altElem = document.getElementById('hud-sat-alt');
    const pitchElem = document.getElementById('hud-sat-pitch');
    const hdgElem = document.getElementById('hud-sat-heading');
    const latElem = document.getElementById('hud-sat-lat');
    const lngElem = document.getElementById('hud-sat-lng');

    const updateHUD = () => {
      if (this.activeMode !== '3D') return;

      const camera = this.viewer.camera;
      const carto = camera.positionCartographic;

      if (altElem) altElem.textContent = `${Math.round(carto.height)}m`;
      if (pitchElem) pitchElem.textContent = `${Math.round(Cesium.Math.toDegrees(camera.pitch))}°`;
      if (hdgElem) hdgElem.textContent = `${Math.round(Cesium.Math.toDegrees(camera.heading))}°`;
      if (latElem) latElem.textContent = Cesium.Math.toDegrees(carto.latitude).toFixed(4) + '° N';
      if (lngElem) lngElem.textContent = Cesium.Math.toDegrees(carto.longitude).toFixed(4) + '° E';
    };

    this.viewer.camera.changed.addEventListener(updateHUD);
    this.viewer.clock.onTick.addEventListener(updateHUD);
  }

  /**
   * Update HUD Target Card
   */
  updateTargetHUD(data, currentHop) {
    const plateElem = document.getElementById('hud-target-plate');
    const modelElem = document.getElementById('hud-target-model');
    const statusElem = document.getElementById('hud-target-status');
    const speedElem = document.getElementById('hud-target-speed');

    if (plateElem) plateElem.textContent = data.plate;
    if (modelElem) modelElem.textContent = data.vehicle || 'Target Vehicle';
    if (statusElem) {
      statusElem.textContent = data.isWatchlist ? 'HOTLIST LOCK' : 'NORMAL TRACK';
      statusElem.className = data.isWatchlist ? 'hud-badge red' : 'hud-badge cyan';
    }
    if (speedElem && currentHop) speedElem.textContent = currentHop.speed || '65 km/h';
  }

  /**
   * Handle 3D Raycast Clicks on Camera Nodes
   */
  setupClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);

    handler.setInputAction(movement => {
      const pickedObject = this.viewer.scene.pick(movement.position);
      if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.cameraData) {
        const cam = pickedObject.id.cameraData;
        console.log('Selected 3D Camera Node:', cam);
        
        // Fly camera directly to node
        this.viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(cam.lng, cam.lat - 0.004, 350),
          orientation: {
            heading: 0,
            pitch: Cesium.Math.toRadians(-28),
            roll: 0
          },
          duration: 1.0
        });
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  }

  /**
   * Switch View Mode between 2D Tactical GIS & 3D God's Eye
   */
  setMode(mode) {
    this.activeMode = mode;
    const container2D = document.getElementById('gis-map');
    const container3D = document.getElementById('gods-eye-3d-container');
    const hudOverlay = document.getElementById('gods-eye-hud-overlay');

    if (mode === '3D') {
      if (container2D) container2D.style.display = 'none';
      if (container3D) {
        container3D.style.display = 'block';
        if (this.viewer) {
          this.viewer.resize();
        }
      }
      if (hudOverlay) hudOverlay.style.display = 'block';

      // Sync active trajectory to 3D
      if (this.parent && this.parent.activeTrajectory) {
        this.render3DTrajectory(this.parent.activeTrajectory);
      }
    } else {
      if (container2D) container2D.style.display = 'block';
      if (container3D) container3D.style.display = 'none';
      if (hudOverlay) hudOverlay.style.display = 'none';

      if (this.parent && this.parent.map) {
        this.parent.map.invalidateSize();
      }
    }
  }

  flyToDefaultView() {
    if (!this.viewer) return;
    this.isTrackingVehicle = false;
    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(this.defaultCenter.lng, this.defaultCenter.lat, this.defaultCenter.alt),
      orientation: {
        heading: Cesium.Math.toRadians(this.defaultCenter.heading),
        pitch: Cesium.Math.toRadians(this.defaultCenter.pitch),
        roll: Cesium.Math.toRadians(this.defaultCenter.roll)
      },
      duration: 1.2
    });
  }

  zoomIn(amountRatio = 0.35) {
    if (!this.viewer) return;
    const camera = this.viewer.camera;
    const height = camera.positionCartographic ? camera.positionCartographic.height : 1000;
    const zoomAmount = Math.max(60, height * amountRatio);
    camera.zoomIn(zoomAmount);
  }

  zoomOut(amountRatio = 0.35) {
    if (!this.viewer) return;
    const camera = this.viewer.camera;
    const height = camera.positionCartographic ? camera.positionCartographic.height : 1000;
    const zoomAmount = Math.max(60, height * amountRatio);
    camera.zoomOut(zoomAmount);
  }
}

window.GodsEye3DMap = GodsEye3DMap;
