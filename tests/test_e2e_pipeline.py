"""
End-to-End Test Suite for City-Wide ANPR Simulation, Ingestion, and Trajectory Pipeline.
Tests: Camera Topology, Scenario Generator, Ingestion API, DB Persistence, Watchlist Intercepts,
Trajectory Graph Reconstruction, and Live WebSocket Broadcasts.
"""

import os
import sys
import json
import pytest
import sqlite3
from datetime import datetime, timedelta

# Ensure project root is in python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from database.db import DatabaseManager
from backend.app import app
from simulation.scenario_generator import generate_baseline_dataset
from simulation.plate_renderer import PlateCropRenderer

TEST_DB_PATH = os.path.join(PROJECT_ROOT, "database", "test_anpr_city.db")


@pytest.fixture(scope="module")
def setup_test_environment():
    """Initializes a fresh isolated SQLite database for E2E testing."""
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    db = DatabaseManager(db_path=TEST_DB_PATH)
    cameras_config_file = os.path.join(PROJECT_ROOT, "config", "cameras.json")
    db.sync_cameras(cameras_config_file)
    
    yield db

    # Cleanup after test suite
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture(scope="module")
def client(setup_test_environment):
    """FastAPI TestClient with isolated test database."""
    from backend import app as backend_module
    backend_module.db_manager = setup_test_environment
    with TestClient(app) as c:
        yield c


# =============================================================================
# 1. Camera Network Configuration Tests
# =============================================================================
def test_camera_network_config():
    cameras_path = os.path.join(PROJECT_ROOT, "config", "cameras.json")
    assert os.path.exists(cameras_path), "cameras.json must exist"

    with open(cameras_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "cameras" in data, "cameras.json must have 'cameras' array"
    cameras = data["cameras"]
    assert len(cameras) >= 6, "Must configure between 6 to 12 interconnected cameras"

    # Validate coordinate boundaries around Delhi-NCR / Urban corridor
    cam_ids = set()
    for cam in cameras:
        assert "id" in cam and cam["id"].startswith("CAM-")
        assert cam["id"] not in cam_ids, f"Duplicate camera ID: {cam['id']}"
        cam_ids.add(cam["id"])

        assert 28.0 <= cam["lat"] <= 29.5, f"Latitude {cam['lat']} out of NCR bounds"
        assert 76.5 <= cam["lng"] <= 77.8, f"Longitude {cam['lng']} out of NCR bounds"
        assert cam.get("speedLimit", 0) in [40, 50, 60, 65, 70, 80, 90]
        assert "adjacentCameras" in cam and isinstance(cam["adjacentCameras"], list)


# =============================================================================
# 2. Synthetic Scenario Generator & Peak-Hour Tests
# =============================================================================
def test_scenario_generator(setup_test_environment):
    db = setup_test_environment
    
    # Generate 550 synthetic events
    result = generate_baseline_dataset(
        total_events=550,
        db_path=TEST_DB_PATH,
        export_json=True,
        render_crops=False
    )

    assert result["total_records"] == 550
    assert os.path.exists(result["fixture_path"])

    with open(result["fixture_path"], "r", encoding="utf-8") as f:
        fixture_data = json.load(f)
        assert len(fixture_data["detections"]) == 550

    # Query DB to verify distribution & peak hours
    analytics = db.get_analytics_kpis()
    assert analytics["totalDetections"] >= 550
    assert analytics["uniqueVehicles"] > 50
    assert 30.0 <= analytics["avgSpeedKmh"] <= 90.0

    # Verify vehicle types populated
    v_dist = analytics["vehicleDistribution"]
    assert "Sedan" in v_dist and v_dist["Sedan"] > 0
    assert "SUV" in v_dist and v_dist["SUV"] > 0
    assert "Two-Wheeler" in v_dist and v_dist["Two-Wheeler"] > 0


# =============================================================================
# 3. Ingestion API & Database Persistence Tests
# =============================================================================
def test_ingest_detection_api(client):
    payload = {
        "camera_id": "CAM-01",
        "plate_number": "DL09CD9988",
        "timestamp": "2026-08-29 14:30:00",
        "speed_kmh": 54.2,
        "vehicle_type": "Sedan",
        "confidence": 0.991,
        "crop_path": "crops/test_sample.jpg"
    }

    response = client.post("/api/v1/ingest", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["plate_number"] == "DL09CD9988"
    assert data["result"]["detection_id"] > 0
    assert data["result"]["is_watchlist_hit"] is False


# =============================================================================
# 4. Watchlist Matching & Alert Trigger Tests
# =============================================================================
def test_watchlist_registration_and_trigger(client):
    suspect_plate = "HR26DQ5551"

    # 1. Register to Watchlist via API
    wl_payload = {
        "plate_number": suspect_plate,
        "vehicle_model": "Hyundai Verna (Polar White)",
        "owner_name": "R. Sharma / TechCorp Fleet",
        "alert_reason": "CRITICAL: Flagged Suspect Chase",
        "severity": "CRITICAL",
        "fir_number": "FIR-2026-0941"
    }
    wl_resp = client.post("/api/v1/watchlist", json=wl_payload)
    assert wl_resp.status_code == 200

    # 2. Ingest detection of this suspect plate
    det_payload = {
        "camera_id": "CAM-06",
        "plate_number": suspect_plate,
        "timestamp": "2026-08-29 10:02:14",
        "speed_kmh": 82.0,
        "vehicle_type": "Sedan",
        "confidence": 0.996
    }
    det_resp = client.post("/api/v1/ingest", json=det_payload)
    assert det_resp.status_code == 201
    det_data = det_resp.json()["result"]

    assert det_data["is_watchlist_hit"] is True
    assert det_data["alert"] is not None
    assert det_data["alert"]["alert_type"] == "WATCHLIST_MATCH"
    assert det_data["alert"]["severity"] == "CRITICAL"


# =============================================================================
# 5. Over-speeding Violation Detection Tests
# =============================================================================
def test_speed_violation_trigger(client):
    # CAM-05 has speed limit 40 km/h
    speeding_plate = "UP16BN8888"
    det_payload = {
        "camera_id": "CAM-05",
        "plate_number": speeding_plate,
        "timestamp": "2026-08-29 16:45:00",
        "speed_kmh": 85.0, # 85 in 40 zone (+45 km/h)
        "vehicle_type": "SUV",
        "confidence": 0.985
    }
    det_resp = client.post("/api/v1/ingest", json=det_payload)
    assert det_resp.status_code == 201
    det_data = det_resp.json()["result"]

    assert det_data["is_speed_violation"] is True
    assert det_data["alert"] is not None
    assert det_data["alert"]["alert_type"] == "SPEED_VIOLATION"
    assert det_data["alert"]["severity"] in ["MODERATE", "HIGH"]


# =============================================================================
# 6. Multi-Camera Trajectory Reconstruction Tests
# =============================================================================
def test_trajectory_reconstruction_pipeline(client):
    tracked_plate = "DL03CC7777"

    # Simulate vehicle crossing 4 cameras sequentially in 20 minutes
    hops = [
        {"cam": "CAM-06", "time": "2026-08-29 11:00:00", "speed": 78.0},
        {"cam": "CAM-01", "time": "2026-08-29 11:08:00", "speed": 62.0},
        {"cam": "CAM-02", "time": "2026-08-29 11:14:00", "speed": 48.0},
        {"cam": "CAM-03", "time": "2026-08-29 11:20:00", "speed": 65.0}
    ]

    for h in hops:
        client.post("/api/v1/ingest", json={
            "camera_id": h["cam"],
            "plate_number": tracked_plate,
            "timestamp": h["time"],
            "speed_kmh": h["speed"],
            "vehicle_type": "Sedan",
            "confidence": 0.99
        })

    # Query trajectory reconstruction endpoint
    resp = client.get(f"/api/v1/trajectories/{tracked_plate}")
    assert resp.status_code == 200
    traj = resp.json()

    assert traj["found"] is True
    assert traj["plate"] == tracked_plate
    assert len(traj["hops"]) == 4

    # Verify chronological ordering
    assert traj["hops"][0]["camId"] == "CAM-06"
    assert traj["hops"][1]["camId"] == "CAM-01"
    assert traj["hops"][2]["camId"] == "CAM-02"
    assert traj["hops"][3]["camId"] == "CAM-03"

    # Verify calculated GIS metrics
    assert "km" in traj["totalDistance"]
    distance_val = float(traj["totalDistance"].replace(" km", ""))
    assert distance_val > 5.0, f"Distance {distance_val} km should be calculated accurately"

    assert "km/h" in traj["avgSpeed"]
    avg_spd_val = float(traj["avgSpeed"].replace(" km/h", ""))
    assert 55.0 <= avg_spd_val <= 70.0

    assert traj["travelDuration"] == "20m 00s"

    # Check GPS coordinates match registered camera positions
    for hop in traj["hops"]:
        assert 28.0 <= hop["lat"] <= 29.5
        assert 76.5 <= hop["lng"] <= 77.8


# =============================================================================
# 7. Synthetic Plate Crop Renderer Tests
# =============================================================================
def test_plate_crop_renderer():
    renderer = PlateCropRenderer()
    filepath, b64_str = renderer.generate_plate_crop(
        plate_number="HR26DQ5551",
        vehicle_type="Sedan",
        is_commercial=False,
        night_mode=False
    )

    assert os.path.exists(filepath), f"Generated crop file should exist: {filepath}"
    assert os.path.getsize(filepath) > 2000, "Crop file should be valid non-empty JPEG"
    assert b64_str.startswith("data:image/jpeg;base64,")


# =============================================================================
# 8. WebSocket Broadcast Endpoint Tests
# =============================================================================
def test_websocket_broadcast(client):
    with client.websocket_connect("/ws/alerts") as ws:
        # Receive connection handshake
        data = ws.receive_json()
        assert data["event_type"] == "CONNECTED"

        # Send ping
        ws.send_text(json.dumps({"action": "PING"}))
        pong = ws.receive_json()
        assert pong["event_type"] == "PONG"
