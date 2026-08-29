import os
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func

from backend.models import Base, Camera, Watchlist, Detection, Alert

DB_PATH = os.getenv("ANPR_DB_PATH", "anpr_platform.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Predefined realistic Smart City ANPR cameras (e.g. Delhi NCR / Metro Corridor)
DEFAULT_CAMERAS = [
    {
        "id": "CAM_001",
        "name": "Connaught Place Inner Ring Node 1",
        "latitude": 28.6315,
        "longitude": 77.2167,
        "zone": "Central",
        "direction": "Clockwise",
        "status": "active"
    },
    {
        "id": "CAM_002",
        "name": "Barakhamba Road Junction",
        "latitude": 28.6290,
        "longitude": 77.2280,
        "zone": "Central",
        "direction": "Eastbound",
        "status": "active"
    },
    {
        "id": "CAM_003",
        "name": "India Gate C-Hexagon North",
        "latitude": 28.6145,
        "longitude": 77.2295,
        "zone": "South",
        "direction": "Southbound",
        "status": "active"
    },
    {
        "id": "CAM_004",
        "name": "Khan Market Roundabout",
        "latitude": 28.5983,
        "longitude": 77.2312,
        "zone": "South",
        "direction": "Southbound",
        "status": "active"
    },
    {
        "id": "CAM_005",
        "name": "AIIMS Flyover Entrance",
        "latitude": 28.5672,
        "longitude": 77.2100,
        "zone": "South",
        "direction": "Inbound",
        "status": "active"
    },
    {
        "id": "CAM_006",
        "name": "DND Flyway Toll Plaza",
        "latitude": 28.5714,
        "longitude": 77.2847,
        "zone": "East",
        "direction": "Eastbound",
        "status": "active"
    },
    {
        "id": "CAM_007",
        "name": "Akshardham Setu Junction",
        "latitude": 28.6186,
        "longitude": 77.2773,
        "zone": "East",
        "direction": "Northbound",
        "status": "active"
    },
    {
        "id": "CAM_008",
        "name": "Kashmere Gate ISBT Interchange",
        "latitude": 28.6675,
        "longitude": 77.2285,
        "zone": "North",
        "direction": "Northbound",
        "status": "active"
    },
    {
        "id": "CAM_009",
        "name": "Cyber City Express Gateway",
        "latitude": 28.4950,
        "longitude": 77.0890,
        "zone": "West",
        "direction": "Outbound",
        "status": "active"
    },
    {
        "id": "CAM_010",
        "name": "IGI Airport T3 Approach Road",
        "latitude": 28.5562,
        "longitude": 77.0999,
        "zone": "West",
        "direction": "Inbound",
        "status": "active"
    }
]

DEFAULT_WATCHLIST = [
    {
        "plate_number": "DL01AB1234",
        "reason": "Stolen Luxury Sedan (FIR-2026/894)",
        "severity": "high",
        "notes": "Red sedan reported stolen from central district."
    },
    {
        "plate_number": "HR26DQ5551",
        "reason": "Wanted - Hit & Run Suspect",
        "severity": "high",
        "notes": "White SUV linked to intersection incident."
    },
    {
        "plate_number": "UP16XY9999",
        "reason": "Suspicious Activity / Smuggling",
        "severity": "medium",
        "notes": "Black pickup monitored across highway corridors."
    }
]


async def init_db(seed: bool = True):
    """Initializes database tables and seeds base camera grid and watchlist if empty."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if seed:
        async with AsyncSessionLocal() as session:
            # Check if cameras exist
            cam_count_res = await session.execute(select(func.count()).select_from(Camera))
            cam_count = cam_count_res.scalar() or 0

            if cam_count == 0:
                for cam_data in DEFAULT_CAMERAS:
                    cam = Camera(**cam_data)
                    session.add(cam)
                await session.commit()

            # Check if watchlist exists
            wl_count_res = await session.execute(select(func.count()).select_from(Watchlist))
            wl_count = wl_count_res.scalar() or 0

            if wl_count == 0:
                for wl_data in DEFAULT_WATCHLIST:
                    wl = Watchlist(**wl_data)
                    session.add(wl)
                await session.commit()


async def seed_demo_data():
    """Seeds realistic sample detections and multi-hop trajectories for demo and testing."""
    async with AsyncSessionLocal() as session:
        # Check if detections already exist
        det_count_res = await session.execute(select(func.count()).select_from(Detection))
        det_count = det_count_res.scalar() or 0
        if det_count > 0:
            return

        now = datetime.now(timezone.utc)
        sample_trajectories = [
            # Trajectory for Wanted Vehicle HR26DQ5551 across Delhi South to Central to East
            ("HR26DQ5551", "suv", 0.98, [
                ("CAM_005", now - timedelta(minutes=45)),
                ("CAM_004", now - timedelta(minutes=32)),
                ("CAM_003", now - timedelta(minutes=20)),
                ("CAM_002", now - timedelta(minutes=10)),
                ("CAM_001", now - timedelta(minutes=2)),
            ]),
            # Trajectory for DL01AB1234 from West to South
            ("DL01AB1234", "sedan", 0.99, [
                ("CAM_010", now - timedelta(hours=2, minutes=15)),
                ("CAM_009", now - timedelta(hours=1, minutes=50)),
                ("CAM_005", now - timedelta(hours=1, minutes=10)),
                ("CAM_004", now - timedelta(minutes=35)),
            ]),
            # Normal vehicle MH02CC4321
            ("MH02CC4321", "sedan", 0.96, [
                ("CAM_008", now - timedelta(hours=3)),
                ("CAM_001", now - timedelta(hours=2, minutes=30)),
                ("CAM_002", now - timedelta(hours=2, minutes=15)),
                ("CAM_007", now - timedelta(hours=1, minutes=45)),
                ("CAM_006", now - timedelta(hours=1, minutes=10)),
            ]),
            # Normal vehicle KA05MN7890
            ("KA05MN7890", "truck", 0.94, [
                ("CAM_006", now - timedelta(hours=4)),
                ("CAM_007", now - timedelta(hours=3, minutes=20)),
                ("CAM_008", now - timedelta(hours=2, minutes=40)),
            ])
        ]

        # Additional random city traffic across cameras
        plates = ["DL3CAB4411", "DL8CY2020", "HR51BL1234", "UP14AZ7788", "DL10CD9900", "HR29EE5050", "DL4CAG1122"]
        vtypes = ["car", "suv", "car", "truck", "motorcycle", "car", "bus"]
        cam_ids = [c["id"] for c in DEFAULT_CAMERAS]

        for plate, vtype, conf, hops in sample_trajectories:
            for cam_id, t_stamp in hops:
                det = Detection(
                    plate_number=plate,
                    camera_id=cam_id,
                    timestamp=t_stamp,
                    confidence=conf,
                    vehicle_type=vtype
                )
                session.add(det)

        import random
        for i in range(120):
            plate = random.choice(plates)
            vtype = random.choice(vtypes)
            cam_id = random.choice(cam_ids)
            mins_ago = random.randint(5, 720)
            det = Detection(
                plate_number=plate,
                camera_id=cam_id,
                timestamp=now - timedelta(minutes=mins_ago),
                confidence=round(random.uniform(0.88, 0.99), 2),
                vehicle_type=vtype
            )
            session.add(det)

        await session.commit()
