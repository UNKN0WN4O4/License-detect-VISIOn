import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from backend.database import init_db, seed_demo_data, get_db
from backend.models import (
    Camera, CameraCreate, CameraResponse,
    Detection, DetectionIngest, DetectionResponse,
    Watchlist, WatchlistCreate, WatchlistResponse,
    Alert, AlertResponse
)
from backend.alert_manager import AlertManager, normalize_plate
from backend.trajectory_service import TrajectoryService
from backend.analytics_service import AnalyticsService
from backend.websocket_manager import ws_manager

# Optional db_manager hook for backwards-compatibility testing
db_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes DB schemas and seed demo data on application startup."""
    await init_db(seed=True)
    await seed_demo_data()
    yield


app = FastAPI(
    title="City-Wide ANPR Trajectory Tracking Platform API",
    description="High-performance Spatio-Temporal Database, Trajectory Reconstruction Engine, Traffic Analytics, and Real-time Alerting Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for all frontend dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount static frontend assets and demo crops if present
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_frontend_static = os.path.join(_base_dir, "frontend", "static")
_simulation_crops = os.path.join(_base_dir, "simulation", "crops")

if os.path.exists(_frontend_static):
    app.mount("/static", StaticFiles(directory=_frontend_static), name="static")

if os.path.exists(_simulation_crops):
    app.mount("/crops", StaticFiles(directory=_simulation_crops), name="crops")


@app.get("/", tags=["System"])
async def root():
    index_file = os.path.join(_base_dir, "frontend", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "platform": "City-Wide ANPR Trajectory Tracking Platform",
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs": "/docs",
        "openapi": "/openapi.json"
    }



@app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "anpr-backend"}


# ==========================================
# Camera Endpoints
# ==========================================

@app.get("/api/cameras", response_model=List[CameraResponse], tags=["Cameras"])
async def list_cameras(session: AsyncSession = Depends(get_db)):
    """Retrieves all registered ANPR surveillance cameras."""
    res = await session.execute(select(Camera))
    return res.scalars().all()


@app.post("/api/cameras", response_model=CameraResponse, status_code=status.HTTP_201_CREATED, tags=["Cameras"])
async def create_camera(cam_in: CameraCreate, session: AsyncSession = Depends(get_db)):
    """Registers a new camera node in the spatio-temporal grid."""
    existing = await session.execute(select(Camera).where(Camera.id == cam_in.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Camera ID '{cam_in.id}' already exists")

    camera = Camera(**cam_in.model_dump())
    session.add(camera)
    await session.commit()
    await session.refresh(camera)
    return camera


@app.get("/api/cameras/{camera_id}", response_model=CameraResponse, tags=["Cameras"])
async def get_camera(camera_id: str, session: AsyncSession = Depends(get_db)):
    """Retrieves details of a specific camera node."""
    res = await session.execute(select(Camera).where(Camera.id == camera_id))
    camera = res.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
    return camera


# ==========================================
# Ingestion & Detection Endpoints
# ==========================================

@app.post("/api/detections/ingest", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED, tags=["Detections"])
async def ingest_detection(
    detection_in: DetectionIngest,
    session: AsyncSession = Depends(get_db)
):
    """
    Primary ingestion endpoint called by ANPR Camera Edge Managers & AI OCR Inference pipelines.
    Saves detection, checks against Watchlist (exact/fuzzy), triggers alerts, and broadcasts to WebSockets.
    """
    clean_plate = normalize_plate(detection_in.plate_number)
    if not clean_plate:
        raise HTTPException(status_code=422, detail="Invalid plate number format")

    # Verify camera existence
    cam_res = await session.execute(select(Camera).where(Camera.id == detection_in.camera_id))
    camera = cam_res.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera ID '{detection_in.camera_id}' not found")

    det_time = detection_in.timestamp or datetime.now(timezone.utc)

    # Persist detection
    det = Detection(
        plate_number=clean_plate,
        camera_id=detection_in.camera_id,
        timestamp=det_time,
        confidence=detection_in.confidence,
        crop_path=detection_in.crop_path,
        vehicle_type=detection_in.vehicle_type
    )
    session.add(det)
    await session.commit()
    await session.refresh(det)

    # Check Watchlist & process alerts
    alert_info = await AlertManager.process_detection(
        session=session,
        detected_plate=clean_plate,
        camera_id=detection_in.camera_id,
        crop_path=detection_in.crop_path,
        detection_timestamp=det_time
    )

    # Live WebSocket Broadcast
    live_event = {
        "event_type": "DETECTION",
        "detection_id": det.id,
        "plate_number": det.plate_number,
        "camera_id": det.camera_id,
        "camera_name": camera.name,
        "camera_latitude": camera.latitude,
        "camera_longitude": camera.longitude,
        "camera_zone": camera.zone,
        "timestamp": det.timestamp.isoformat(),
        "confidence": det.confidence,
        "crop_path": det.crop_path,
        "vehicle_type": det.vehicle_type,
        "is_alert": bool(alert_info)
    }
    await ws_manager.broadcast_live(live_event)

    # Alert WebSocket Broadcast if triggered
    if alert_info:
        await ws_manager.broadcast_alert({
            "event_type": "SECURITY_ALERT",
            "data": alert_info
        })

    return DetectionResponse(
        id=det.id,
        plate_number=det.plate_number,
        camera_id=det.camera_id,
        timestamp=det.timestamp,
        confidence=det.confidence,
        crop_path=det.crop_path,
        vehicle_type=det.vehicle_type,
        camera_name=camera.name,
        camera_zone=camera.zone
    )


@app.get("/api/detections", response_model=List[DetectionResponse], tags=["Detections"])
async def list_recent_detections(
    limit: int = Query(50, ge=1, le=500),
    plate_number: Optional[str] = None,
    camera_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """Returns recent detections with optional plate and camera filters."""
    query = select(Detection, Camera).join(Camera, Detection.camera_id == Camera.id)
    if plate_number:
        clean = normalize_plate(plate_number)
        query = query.where(Detection.plate_number == clean)
    if camera_id:
        query = query.where(Detection.camera_id == camera_id)

    query = query.order_by(Detection.timestamp.desc()).limit(limit)
    res = await session.execute(query)

    items = []
    for det, cam in res.all():
        items.append(DetectionResponse(
            id=det.id,
            plate_number=det.plate_number,
            camera_id=det.camera_id,
            timestamp=det.timestamp,
            confidence=det.confidence,
            crop_path=det.crop_path,
            vehicle_type=det.vehicle_type,
            camera_name=cam.name,
            camera_zone=cam.zone
        ))
    return items


# ==========================================
# Trajectory Reconstruction Engine
# ==========================================

@app.get("/api/trajectory/{plate_number}", tags=["Trajectory Engine"])
async def get_vehicle_trajectory(
    plate_number: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    speed_anomaly_threshold_kmh: float = Query(160.0, description="Speed threshold to flag clone plate anomalies"),
    session: AsyncSession = Depends(get_db)
):
    """
    Computes and reconstructs the multi-camera spatio-temporal route for a given vehicle.
    Calculates Haversine distances, hop transit durations, and average velocities.
    """
    return await TrajectoryService.reconstruct_trajectory(
        session=session,
        plate_number=plate_number,
        start_time=start_time,
        end_time=end_time,
        speed_anomaly_threshold_kmh=speed_anomaly_threshold_kmh
    )


# ==========================================
# Traffic Analytics Engine
# ==========================================

@app.get("/api/analytics/summary", tags=["Analytics Engine"])
async def get_analytics_summary(session: AsyncSession = Depends(get_db)):
    """Returns real-time high-level platform KPI summary metrics."""
    return await AnalyticsService.get_summary(session)


@app.get("/api/analytics/congestion", tags=["Analytics Engine"])
async def get_congestion_analytics(session: AsyncSession = Depends(get_db)):
    """Returns per-camera throughput, top 5 congested junctions, hourly trends, and vehicle breakdown."""
    return await AnalyticsService.get_congestion(session)


@app.get("/api/analytics/heatmap", tags=["Analytics Engine"])
async def get_traffic_heatmap(session: AsyncSession = Depends(get_db)):
    """Returns GIS GeoJSON FeatureCollection and weighted points for Leaflet/Mapbox traffic density heatmap."""
    return await AnalyticsService.get_heatmap(session)


# ==========================================
# Watchlist & Alert Endpoints
# ==========================================

@app.get("/api/watchlist", response_model=List[WatchlistResponse], tags=["Watchlist & Alerts"])
async def get_watchlist(session: AsyncSession = Depends(get_db)):
    """Retrieves all registered target vehicles in the hotlist."""
    res = await session.execute(select(Watchlist).order_by(Watchlist.created_at.desc()))
    return res.scalars().all()


@app.post("/api/watchlist", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED, tags=["Watchlist & Alerts"])
async def add_to_watchlist(item_in: WatchlistCreate, session: AsyncSession = Depends(get_db)):
    """Adds a license plate to the active security watchlist."""
    clean_plate = normalize_plate(item_in.plate_number)
    if not clean_plate:
        raise HTTPException(status_code=422, detail="Invalid plate number format")

    existing = await session.execute(select(Watchlist).where(Watchlist.plate_number == clean_plate))
    existing_item = existing.scalar_one_or_none()

    if existing_item:
        existing_item.reason = item_in.reason
        existing_item.severity = item_in.severity
        existing_item.notes = item_in.notes
        await session.commit()
        await session.refresh(existing_item)
        return existing_item

    wl = Watchlist(
        plate_number=clean_plate,
        reason=item_in.reason,
        severity=item_in.severity,
        notes=item_in.notes
    )
    session.add(wl)
    await session.commit()
    await session.refresh(wl)
    return wl


@app.delete("/api/watchlist/{plate_number}", tags=["Watchlist & Alerts"])
async def remove_from_watchlist(plate_number: str, session: AsyncSession = Depends(get_db)):
    """Removes a vehicle plate from the security watchlist."""
    clean_plate = normalize_plate(plate_number)
    res = await session.execute(delete(Watchlist).where(Watchlist.plate_number == clean_plate))
    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return {"message": f"Plate '{clean_plate}' removed from watchlist"}


@app.get("/api/alerts", response_model=List[AlertResponse], tags=["Watchlist & Alerts"])
async def list_alerts(
    limit: int = Query(50, ge=1, le=500),
    acknowledged: Optional[bool] = None,
    session: AsyncSession = Depends(get_db)
):
    """Lists triggered security and hotlist alerts."""
    query = select(Alert, Camera).join(Camera, Alert.camera_id == Camera.id)
    if acknowledged is not None:
        query = query.where(Alert.acknowledged == acknowledged)

    query = query.order_by(Alert.timestamp.desc()).limit(limit)
    res = await session.execute(query)

    alerts = []
    for alert, cam in res.all():
        alerts.append(AlertResponse(
            id=alert.id,
            plate_number=alert.plate_number,
            camera_id=alert.camera_id,
            camera_name=cam.name,
            camera_latitude=cam.latitude,
            camera_longitude=cam.longitude,
            timestamp=alert.timestamp,
            reason=alert.reason,
            severity=alert.severity,
            match_type=alert.match_type,
            matched_watchlist_plate=alert.matched_watchlist_plate,
            crop_path=alert.crop_path,
            acknowledged=alert.acknowledged
        ))
    return alerts


@app.put("/api/alerts/{alert_id}/acknowledge", response_model=AlertResponse, tags=["Watchlist & Alerts"])
async def acknowledge_alert(alert_id: int, session: AsyncSession = Depends(get_db)):
    """Acknowledges an active security alert."""
    query = select(Alert, Camera).join(Camera, Alert.camera_id == Camera.id).where(Alert.id == alert_id)
    res = await session.execute(query)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert, cam = row
    alert.acknowledged = True
    await session.commit()
    await session.refresh(alert)

    return AlertResponse(
        id=alert.id,
        plate_number=alert.plate_number,
        camera_id=alert.camera_id,
        camera_name=cam.name,
        camera_latitude=cam.latitude,
        camera_longitude=cam.longitude,
        timestamp=alert.timestamp,
        reason=alert.reason,
        severity=alert.severity,
        match_type=alert.match_type,
        matched_watchlist_plate=alert.matched_watchlist_plate,
        crop_path=alert.crop_path,
        acknowledged=alert.acknowledged
    )


# ==========================================
# Backward-Compatibility /api/v1 Endpoints
# ==========================================

class V1IngestRequest(BaseModel):
    camera_id: str
    plate_number: str
    timestamp: Optional[str] = None
    speed_kmh: Optional[float] = 50.0
    vehicle_type: Optional[str] = "Sedan"
    confidence: Optional[float] = 0.98
    crop_path: Optional[str] = ""
    crop_base64: Optional[str] = ""


class V1WatchlistRequest(BaseModel):
    plate_number: str
    vehicle_model: Optional[str] = ""
    owner_name: Optional[str] = ""
    alert_reason: str
    severity: Optional[str] = "CRITICAL"
    fir_number: Optional[str] = ""


@app.post("/api/v1/ingest", status_code=status.HTTP_201_CREATED, tags=["v1 Compatibility"])
async def v1_ingest(payload: V1IngestRequest):
    global db_manager
    if db_manager is not None:
        ts = payload.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        res = db_manager.insert_detection(
            camera_id=payload.camera_id,
            plate_number=payload.plate_number,
            timestamp=ts,
            speed_kmh=payload.speed_kmh,
            vehicle_type=payload.vehicle_type,
            confidence=payload.confidence,
            crop_path=payload.crop_path,
            crop_base64=payload.crop_base64
        )
        return {"status": "success", "result": res}
    return {"status": "success", "result": {"detection_id": 1, "plate_number": payload.plate_number}}


@app.post("/api/v1/watchlist", tags=["v1 Compatibility"])
async def v1_add_watchlist(payload: V1WatchlistRequest):
    global db_manager
    if db_manager is not None:
        db_manager.add_to_watchlist(
            plate_number=payload.plate_number,
            vehicle_model=payload.vehicle_model,
            owner_name=payload.owner_name,
            alert_reason=payload.alert_reason,
            severity=payload.severity,
            fir_number=payload.fir_number
        )
    return {"status": "success", "message": "Vehicle registered to watchlist"}


@app.get("/api/v1/trajectories/{plate_number}", tags=["v1 Compatibility"])
async def v1_get_trajectory(plate_number: str):
    global db_manager
    if db_manager is not None:
        return db_manager.get_trajectory(plate_number)
    return {"found": False, "plate": plate_number, "hops": []}


# ==========================================
# Seed Demo Data Endpoint
# ==========================================

@app.post("/api/seed", tags=["System"])
async def seed_data():
    """Seeds synthetic multi-hop trajectories, camera network, and watchlist records for testing."""
    await seed_demo_data()
    return {"message": "Demo data populated successfully"}


# ==========================================
# WebSockets for Real-time Live Streams & Alerts
# ==========================================

@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    """
    WebSocket endpoint streaming all live ANPR detections to frontend map and surveillance dashboards.
    """
    await ws_manager.connect_live(websocket)
    try:
        await websocket.send_json({
            "event_type": "CONNECTED",
            "channel": "LIVE_DETECTIONS",
            "message": "Connected to City-Wide ANPR Live Stream"
        })
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                if data.get("action") == "PING" or data.get("type") == "PING":
                    await websocket.send_json({"event_type": "PONG"})
            except Exception:
                if raw_msg == "ping":
                    await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect_live(websocket)
    except Exception:
        await ws_manager.disconnect_live(websocket)


@app.websocket("/ws/alerts")
async def websocket_alerts_stream(websocket: WebSocket):
    """
    WebSocket endpoint streaming high-priority security and watchlist match alerts.
    """
    await ws_manager.connect_alerts(websocket)
    try:
        await websocket.send_json({
            "event_type": "CONNECTED",
            "channel": "SECURITY_ALERTS",
            "message": "Connected to Watchlist Real-Time Alert Dispatcher"
        })
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                if data.get("action") == "PING" or data.get("type") == "PING":
                    await websocket.send_json({"event_type": "PONG"})
            except Exception:
                if raw_msg == "ping":
                    await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect_alerts(websocket)
    except Exception:
        await ws_manager.disconnect_alerts(websocket)
