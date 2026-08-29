import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models import Base, Camera, Watchlist, Detection, Alert
from backend.database import get_db, DEFAULT_CAMERAS, DEFAULT_WATCHLIST
from backend.alert_manager import levenshtein_distance, is_ocr_equivalent_or_similar, normalize_plate
from backend.trajectory_service import haversine_distance_km
from backend.app import app

# In-memory SQLite database for testing
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(autouse=True)
async def setup_test_db():
    app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default cameras and watchlist
    async with TestSessionLocal() as session:
        for cam_data in DEFAULT_CAMERAS:
            session.add(Camera(**cam_data))
        for wl_data in DEFAULT_WATCHLIST:
            session.add(Watchlist(**wl_data))
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_levenshtein_and_ocr_matching():
    # Normalization
    assert normalize_plate("dl 01 ab 1234") == "DL01AB1234"
    assert levenshtein_distance("DL01AB1234", "DL01AB1234") == 0
    assert levenshtein_distance("HR26DQ5551", "HR26DQ5550") == 1

    # Exact match
    is_match, mtype, score = is_ocr_equivalent_or_similar("HR26DQ5551", "HR26DQ5551")
    assert is_match is True
    assert mtype == "exact"
    assert score == 1.0

    # OCR character substitution (e.g. 0 vs O)
    is_match, mtype, score = is_ocr_equivalent_or_similar("DL01AB1234", "DLO1AB1234")
    assert is_match is True
    assert mtype in ["fuzzy_ocr", "fuzzy"]


@pytest.mark.asyncio
async def test_haversine_distance():
    # CP to India Gate approx 2.0 km
    lat1, lon1 = 28.6315, 77.2167
    lat2, lon2 = 28.6145, 77.2295
    dist = haversine_distance_km(lat1, lon1, lat2, lon2)
    assert 1.5 < dist < 3.0


@pytest.mark.asyncio
async def test_camera_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List cameras
        resp = await client.get("/api/cameras")
        assert resp.status_code == 200
        cams = resp.json()
        assert len(cams) >= 10
        assert any(c["id"] == "CAM_001" for c in cams)

        # Create new camera
        new_cam = {
            "id": "CAM_999",
            "name": "Noida Sector 62 Gateway",
            "latitude": 28.6280,
            "longitude": 77.3649,
            "zone": "East",
            "direction": "Inbound",
            "status": "active"
        }
        resp = await client.post("/api/cameras", json=new_cam)
        assert resp.status_code == 201
        assert resp.json()["id"] == "CAM_999"

        # Get specific camera
        resp = await client.get("/api/cameras/CAM_999")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Noida Sector 62 Gateway"


@pytest.mark.asyncio
async def test_ingest_and_alert_trigger():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest normal vehicle
        resp = await client.post("/api/detections/ingest", json={
            "plate_number": "UP14TEST11",
            "camera_id": "CAM_001",
            "confidence": 0.97,
            "vehicle_type": "car"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["plate_number"] == "UP14TEST11"

        # Ingest Watchlist Exact Match (HR26DQ5551)
        resp = await client.post("/api/detections/ingest", json={
            "plate_number": "HR26DQ5551",
            "camera_id": "CAM_003",
            "confidence": 0.99,
            "vehicle_type": "suv"
        })
        assert resp.status_code == 201

        # Check alerts table
        alerts_resp = await client.get("/api/alerts")
        assert alerts_resp.status_code == 200
        alerts = alerts_resp.json()
        assert len(alerts) >= 1
        matched_alert = next((a for a in alerts if a["plate_number"] == "HR26DQ5551"), None)
        assert matched_alert is not None
        assert matched_alert["severity"] == "high"
        assert matched_alert["acknowledged"] is False

        # Ingest Fuzzy Match (e.g. DL01AB1234 typed as DLO1AB1234)
        resp = await client.post("/api/detections/ingest", json={
            "plate_number": "DLO1AB1234",
            "camera_id": "CAM_002",
            "confidence": 0.93,
            "vehicle_type": "sedan"
        })
        assert resp.status_code == 201

        # Acknowledge Alert
        ack_resp = await client.put(f"/api/alerts/{matched_alert['id']}/acknowledge")
        assert ack_resp.status_code == 200
        assert ack_resp.json()["acknowledged"] is True


@pytest.mark.asyncio
async def test_trajectory_reconstruction():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        now = datetime.now(timezone.utc)
        test_plate = "KA01TRACK99"

        # Ingest a 3-hop journey
        hops_data = [
            ("CAM_001", now - timedelta(minutes=30)),
            ("CAM_002", now - timedelta(minutes=20)),
            ("CAM_003", now - timedelta(minutes=5))
        ]

        for cam_id, t_stamp in hops_data:
            await client.post("/api/detections/ingest", json={
                "plate_number": test_plate,
                "camera_id": cam_id,
                "timestamp": t_stamp.isoformat(),
                "confidence": 0.98,
                "vehicle_type": "sedan"
            })

        # Query Trajectory
        resp = await client.get(f"/api/trajectory/{test_plate}")
        assert resp.status_code == 200
        traj = resp.json()

        assert traj["plate_number"] == test_plate
        assert traj["total_detections"] == 3
        assert traj["total_hops"] == 2
        assert traj["total_distance_km"] > 0
        assert traj["total_duration_minutes"] >= 20.0
        assert len(traj["hops"]) == 2
        assert len(traj["route_coordinates"]) == 3
        assert traj["hops"][0]["from_camera"]["id"] == "CAM_001"
        assert traj["hops"][0]["to_camera"]["id"] == "CAM_002"
        assert traj["hops"][0]["speed_kmh"] > 0


@pytest.mark.asyncio
async def test_analytics_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest several detections to populate stats
        plates = ["DL11AA1111", "HR22BB2222", "UP33CC3333"]
        cams = ["CAM_001", "CAM_002", "CAM_003"]
        for p, c in zip(plates, cams):
            await client.post("/api/detections/ingest", json={
                "plate_number": p,
                "camera_id": c,
                "confidence": 0.95,
                "vehicle_type": "car"
            })

        # Summary
        summary_resp = await client.get("/api/analytics/summary")
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["total_cameras"] >= 10
        assert summary["active_cameras"] >= 10
        assert summary["total_detections_today"] >= 3

        # Congestion
        congestion_resp = await client.get("/api/analytics/congestion")
        assert congestion_resp.status_code == 200
        congestion = congestion_resp.json()
        assert len(congestion["top_congested_junctions"]) <= 5
        assert len(congestion["hourly_trends"]) == 24
        assert len(congestion["vehicle_breakdown"]) >= 1

        # Heatmap
        heatmap_resp = await client.get("/api/analytics/heatmap")
        assert heatmap_resp.status_code == 200
        heatmap = heatmap_resp.json()
        assert "points" in heatmap
        assert "geojson" in heatmap
        assert heatmap["geojson"]["type"] == "FeatureCollection"
        assert len(heatmap["geojson"]["features"]) >= 10


@pytest.mark.asyncio
async def test_watchlist_management():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add to watchlist
        resp = await client.post("/api/watchlist", json={
            "plate_number": "WB02ZZ8888",
            "reason": "Suspected narcotics transport",
            "severity": "high",
            "notes": "Silver hatchback"
        })
        assert resp.status_code == 201
        assert resp.json()["plate_number"] == "WB02ZZ8888"

        # List watchlist
        get_resp = await client.get("/api/watchlist")
        assert get_resp.status_code == 200
        items = get_resp.json()
        assert any(i["plate_number"] == "WB02ZZ8888" for i in items)

        # Delete from watchlist
        del_resp = await client.delete("/api/watchlist/WB02ZZ8888")
        assert del_resp.status_code == 200
        assert "removed" in del_resp.json()["message"]


@pytest.mark.asyncio
async def test_street_routing_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Route between Cyber City and IGI Airport corridor
        coords = "77.1000,28.5562;77.0878,28.4986"
        resp = await client.get(f"/api/routing/route?coordinates={coords}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["coordinates"]) >= 2
        assert data["distance_km"] > 0
        assert data["duration_minutes"] > 0
        assert data["source"] in ["osrm_real_road_network", "fallback_interpolated_network"]

