"""
Synthetic Scenario & Baseline Traffic Dataset Generator.
Populates the ANPR system database with 600+ realistic timestamped detection events
across 12 cameras over the last 24 hours with authentic peak-hour traffic spikes
(8 AM - 10 AM, 6 PM - 9 PM), realistic speeds, vehicle distributions, and crops.
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Ensure project root is in python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database.db import DatabaseManager, DEFAULT_DB_PATH
from simulation.plate_renderer import PlateCropRenderer

# State & RTO prefix pools for NCR / Metro Corridor
STATE_CODES = ["HR26", "HR51", "HR10", "DL01", "DL03", "DL08", "DL09", "UP16", "UP14", "KA03", "MH02"]
SERIES_LETTERS = ["AB", "AU", "AZ", "BN", "CC", "DQ", "DX", "EA", "EV", "MG", "ZZ"]
VEHICLE_TYPES = [
    ("Sedan", 0.38, False),
    ("SUV", 0.24, False),
    ("Two-Wheeler", 0.18, False),
    ("Commercial Truck", 0.10, True),
    ("EV Cab / Auto", 0.07, True),
    ("Bus", 0.03, True)
]


def generate_random_plate() -> str:
    state = random.choice(STATE_CODES)
    series = random.choice(SERIES_LETTERS)
    num = random.randint(1000, 9999)
    return f"{state}{series}{num}"


def sample_vehicle_type() -> tuple[str, bool]:
    r = random.random()
    cumulative = 0.0
    for v_type, prob, is_comm in VEHICLE_TYPES:
        cumulative += prob
        if r <= cumulative:
            return v_type, is_comm
    return "Sedan", False


def sample_event_time(now: datetime, hours_back: int = 24) -> datetime:
    """
    Generates a timestamp within the last 24 hours with realistic bimodal peak traffic:
    Peak 1: 08:00 - 10:30 (Morning Office Rush)
    Peak 2: 17:30 - 21:00 (Evening Rush)
    Moderate: 11:00 - 17:00
    Low: 22:00 - 06:00
    """
    # Pick a target hour based on probability weights
    hour_weights = [
        0.015, 0.008, 0.005, 0.005, 0.010, 0.025, # 00:00 - 05:00 (Night)
        0.050, 0.085, 0.140, 0.130, 0.070, 0.055, # 06:00 - 11:00 (Morning Rush)
        0.050, 0.045, 0.045, 0.055, 0.070, 0.110, # 12:00 - 17:00 (Midday to Evening)
        0.135, 0.120, 0.080, 0.045, 0.025, 0.015  # 18:00 - 23:00 (Evening Rush to Night)
    ]
    
    # Normalize weights
    total_w = sum(hour_weights)
    norm_weights = [w / total_w for w in hour_weights]

    selected_hour = random.choices(range(24), weights=norm_weights, k=1)[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    # Determine date
    event_time = now.replace(hour=selected_hour, minute=minute, second=second, microsecond=0)
    if event_time > now:
        event_time -= timedelta(days=1)
        
    return event_time


def generate_baseline_dataset(total_events: int = 650, db_path: str = DEFAULT_DB_PATH,
                              export_json: bool = True, render_crops: bool = True) -> Dict[str, Any]:
    print(f"================================================================")
    print(f"🚀 GENERATING SYNTHETIC ANPR BASELINE DATASET ({total_events} EVENTS)")
    print(f"================================================================")

    db = DatabaseManager(db_path=db_path)
    cameras_config_file = os.path.join(PROJECT_ROOT, "config", "cameras.json")
    db.sync_cameras(cameras_config_file)

    # Load camera objects
    with open(cameras_config_file, "r", encoding="utf-8") as f:
        cam_data = json.load(f)
        cameras = cam_data.get("cameras", [])

    cam_dict = {c["id"]: c for c in cameras}
    cam_ids = list(cam_dict.keys())

    # Pre-seed realistic recurring vehicles & fleet pools
    vehicle_pool = [generate_random_plate() for _ in range(120)]
    
    # Also add key benchmark plates
    benchmark_plates = ["HR26DQ5551", "DL01AB1234", "KA03MG8899", "UP16BN4422", "MH02CB4040", "DL03CC8899"]
    for bp in benchmark_plates:
        if bp not in vehicle_pool:
            vehicle_pool.append(bp)

    # Initialize Watchlist in DB
    db.add_to_watchlist(
        plate_number="DL01AB1234",
        vehicle_model="Toyota Fortuner (Phantom Black)",
        owner_name="UNKNOWN - STOLEN REPORT #4092",
        alert_reason="Stolen Vehicle / Fast Corridor Breach",
        severity="CRITICAL",
        fir_number="FIR/DL-2026/0941"
    )
    db.add_to_watchlist(
        plate_number="HR26DQ5551",
        vehicle_model="Hyundai Verna (Polar White)",
        owner_name="R. Sharma / TechCorp Fleet",
        alert_reason="Flagged Suspect Vehicle / Armed Transit",
        severity="CRITICAL",
        fir_number="FIR/HR-2026/1842"
    )

    renderer = PlateCropRenderer() if render_crops else None
    now = datetime.now()

    generated_records = []
    crops_cached = {}

    print(f"[*] Generating {total_events} realistic detection events across {len(cameras)} cameras...")

    for i in range(total_events):
        cam_id = random.choice(cam_ids)
        camera = cam_dict[cam_id]
        speed_limit = camera.get("speedLimit", 60)

        # 70% from fleet pool, 30% random unique
        if random.random() < 0.70:
            plate = random.choice(vehicle_pool)
        else:
            plate = generate_random_plate()

        v_type, is_comm = sample_vehicle_type()
        timestamp = sample_event_time(now)

        # Realistic Speed calculation: mean around speed_limit - 5, standard deviation 12
        # ~10% overspeeding violations
        speed = round(random.gauss(speed_limit - 4, 9), 1)
        if random.random() < 0.12:
            # High speed violator
            speed = round(speed_limit + random.uniform(15, 45), 1)
        speed = max(18.0, speed) # Minimum realistic urban crawling speed

        confidence = round(random.uniform(0.945, 0.998), 4)

        crop_path = ""
        crop_base64 = ""
        if render_crops:
            # Generate or reuse crop for speed
            if plate in crops_cached:
                crop_path, crop_base64 = crops_cached[plate]
            else:
                is_night = timestamp.hour < 6 or timestamp.hour > 19
                crop_path, crop_base64 = renderer.generate_plate_crop(
                    plate_number=plate,
                    vehicle_type=v_type,
                    is_commercial=is_comm,
                    night_mode=is_night
                )
                crops_cached[plate] = (crop_path, crop_base64)

        # Insert to DB
        res = db.insert_detection(
            camera_id=cam_id,
            plate_number=plate,
            timestamp=timestamp,
            speed_kmh=speed,
            vehicle_type=v_type,
            confidence=confidence,
            crop_path=crop_path,
            crop_base64=crop_base64
        )

        record = {
            "id": res["detection_id"],
            "camera_id": cam_id,
            "camera_name": camera["name"],
            "lat": camera["lat"],
            "lng": camera["lng"],
            "plate_number": plate,
            "timestamp": res["timestamp"],
            "speed_kmh": speed,
            "vehicle_type": v_type,
            "confidence": confidence,
            "is_watchlist_hit": res["is_watchlist_hit"],
            "is_speed_violation": res["is_speed_violation"],
            "crop_path": crop_path
        }
        generated_records.append(record)

    print(f"✅ Successfully inserted {len(generated_records)} detections into SQLite DB: {db_path}")

    # Export JSON fixture
    fixture_path = os.path.join(PROJECT_ROOT, "simulation", "fixtures", "baseline_detections.json")
    if export_json:
        os.makedirs(os.path.dirname(fixture_path), exist_ok=True)
        fixture_payload = {
            "metadata": {
                "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "total_events": len(generated_records),
                "camera_count": len(cameras),
                "time_window": "24 Hours (Peak Spikes at 8-10 AM, 6-9 PM)"
            },
            "detections": generated_records
        }
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(fixture_payload, f, indent=2)
        print(f"✅ Exported JSON fixture to: {fixture_path}")

    # Display KPI summary
    analytics = db.get_analytics_kpis()
    print("\n--- BASELINE DATASET SUMMARY ---")
    print(f"Total Detections: {analytics['totalDetections']}")
    print(f"Unique Vehicles:  {analytics['uniqueVehicles']}")
    print(f"Avg City Speed:   {analytics['avgSpeedKmh']} km/h")
    print(f"Active Alerts:    {analytics['activeAlerts']}")
    print(f"Vehicle Breakdown: {json.dumps(analytics['vehicleDistribution'], indent=2)}")
    print("--------------------------------\n")

    return {
        "total_records": len(generated_records),
        "db_path": db_path,
        "fixture_path": fixture_path,
        "analytics": analytics
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ANPR Synthetic Baseline Scenario")
    parser.add_argument("--count", type=int, default=650, help="Number of baseline detection events to generate")
    parser.add_argument("--no-crops", action="store_true", help="Skip rendering visual plate image crops")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Path to SQLite database")
    args = parser.parse_args()

    generate_baseline_dataset(
        total_events=args.count,
        db_path=args.db,
        export_json=True,
        render_crops=not args.no_crops
    )
