"""
"Stolen Vehicle / Suspect Chase" Live Demo Script.
Simulates a blacklisted/wanted vehicle (HR26DQ5551) transiting across
interconnected city CCTV cameras over a 30-minute window with realistic crops,
speed telemetry, and live WebSocket alert dispatch for instant GIS trajectory replay.
"""

import os
import sys
import time
import json
import argparse
import requests
from datetime import datetime, timedelta

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


# ANSI Color Codes for Rich Terminal Output
class TermColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'


def banner():
    print(f"""{TermColors.CYAN}{TermColors.BOLD}
╔════════════════════════════════════════════════════════════════════════════╗
║         BEL CITY-WIDE ANPR MULTI-CAMERA SURVEILLANCE SYSTEM                ║
║           LIVE "SUSPECT CHASE / STOLEN VEHICLE" SIMULATION HARNESS         ║
╚════════════════════════════════════════════════════════════════════════════╝{TermColors.RESET}""")


# Corridor Waypoint Definition (Chronological CCTV hops over ~32 mins)
SUSPECT_TRANSIT_CORRIDOR = [
    {
        "hop": 1,
        "cam_id": "CAM-06",
        "cam_name": "IGI Airport Expressway North",
        "corridor": "Airport Expressway Corridor",
        "minute_offset": 0,
        "speed_kmh": 82.4,
        "region": "expressway",
        "lat": 28.5562,
        "lng": 77.1000
    },
    {
        "hop": 2,
        "cam_id": "CAM-01",
        "cam_name": "Cyber Hub North Gate",
        "corridor": "Cyber City Arterial",
        "minute_offset": 12,
        "speed_kmh": 64.0,
        "region": "cyber",
        "lat": 28.4986,
        "lng": 77.0878
    },
    {
        "hop": 3,
        "cam_id": "CAM-11",
        "cam_name": "Shankar Chowk Cloverleaf",
        "corridor": "NH-48 / Cyber City Cloverleaf",
        "minute_offset": 15,
        "speed_kmh": 58.5,
        "region": "cyber",
        "lat": 28.5028,
        "lng": 77.0898
    },
    {
        "hop": 4,
        "cam_id": "CAM-02",
        "cam_name": "MG Road Metro Junction",
        "corridor": "MG Road Commercial Corridor",
        "minute_offset": 18,
        "speed_kmh": 48.0,
        "region": "central",
        "lat": 28.4796,
        "lng": 77.0802
    },
    {
        "hop": 5,
        "cam_id": "CAM-03",
        "cam_name": "IFFCO Chowk Flyover",
        "corridor": "NH-48 Expressway Interchange",
        "minute_offset": 23,
        "speed_kmh": 62.0,
        "region": "central",
        "lat": 28.4721,
        "lng": 77.0689
    },
    {
        "hop": 6,
        "cam_id": "CAM-07",
        "cam_name": "Ring Road - Dhaula Kuan",
        "corridor": "Ring Road Arterial",
        "minute_offset": 28,
        "speed_kmh": 76.8,
        "region": "ringroad",
        "lat": 28.5912,
        "lng": 77.1615
    },
    {
        "hop": 7,
        "cam_id": "CAM-04",
        "cam_name": "Golf Course Extn Road",
        "corridor": "Golf Course Southern Peripheral",
        "minute_offset": 32,
        "speed_kmh": 59.2,
        "region": "cyber",
        "lat": 28.4184,
        "lng": 77.0945
    }
]


def run_chase_demo(target_plate: str = "HR26DQ5551",
                   vehicle_model: str = "Hyundai Verna (Polar White)",
                   owner_name: str = "R. Sharma / TechCorp Fleet",
                   alert_reason: str = "CRITICAL: Stolen Vehicle / Suspect Vehicle In Transit",
                   api_url: str = "http://localhost:8000",
                   speedup_factor: float = 20.0,
                   step_mode: bool = False,
                   db_path: str = DEFAULT_DB_PATH):
    banner()

    print(f"{TermColors.BOLD}[*] Initializing Database & Camera Network...{TermColors.RESET}")
    db = DatabaseManager(db_path=db_path)
    cameras_config_file = os.path.join(PROJECT_ROOT, "config", "cameras.json")
    db.sync_cameras(cameras_config_file)

    # 1. Register Suspect Vehicle to Watchlist
    print(f"\n{TermColors.YELLOW}[*] Registering Target to High-Priority Blacklist / Watchlist:{TermColors.RESET}")
    print(f"    • License Plate:  {TermColors.BOLD}{TermColors.RED}{target_plate}{TermColors.RESET}")
    print(f"    • Vehicle Model:  {vehicle_model}")
    print(f"    • Owner/Record:   {owner_name}")
    print(f"    • Alert Reason:   {TermColors.RED}{alert_reason}{TermColors.RESET}")
    print(f"    • Severity:       {TermColors.RED}CRITICAL{TermColors.RESET}")

    db.add_to_watchlist(
        plate_number=target_plate,
        vehicle_model=vehicle_model,
        owner_name=owner_name,
        alert_reason=alert_reason,
        severity="CRITICAL",
        fir_number="FIR-DL-2026/0942"
    )

    # Check if backend API server is reachable
    api_online = False
    try:
        r = requests.get(f"{api_url}/api/v1/health", timeout=1.5)
        if r.status_code == 200:
            api_online = True
            print(f"    • Backend API:    {TermColors.GREEN}ONLINE ({api_url}){TermColors.RESET}")
    except Exception:
        print(f"    • Backend API:    {TermColors.YELLOW}OFFLINE / Standalone DB Mode{TermColors.RESET}")

    # 2. Prepare Synthetic Crop Generator
    renderer = PlateCropRenderer()
    print(f"    • Crop Generator: {TermColors.GREEN}READY (Generating HSRP Visual Crops){TermColors.RESET}\n")

    base_time = datetime.now() - timedelta(minutes=34)

    print(f"{TermColors.CYAN}{TermColors.BOLD}========================================================================{TermColors.RESET}")
    print(f"{TermColors.CYAN}STARTING MULTI-CAMERA TRANSIT SIMULATION (Total Hops: {len(SUSPECT_TRANSIT_CORRIDOR)}){TermColors.RESET}")
    if step_mode:
        print(f"{TermColors.YELLOW}Mode: Interactive Step-by-Step [Press ENTER after each hop]{TermColors.RESET}")
    else:
        print(f"{TermColors.YELLOW}Mode: Automated Speedup ({speedup_factor}x Realtime Rate){TermColors.RESET}")
    print(f"{TermColors.CYAN}{TermColors.BOLD}========================================================================{TermColors.RESET}\n")

    total_hops = len(SUSPECT_TRANSIT_CORRIDOR)
    previous_offset = 0

    for idx, node in enumerate(SUSPECT_TRANSIT_CORRIDOR):
        hop_num = node["hop"]
        cam_id = node["cam_id"]
        cam_name = node["cam_name"]
        speed = node["speed_kmh"]
        offset_mins = node["minute_offset"]

        # Calculate time delta for playback delay
        delta_mins = offset_mins - previous_offset
        previous_offset = offset_mins

        if idx > 0 and not step_mode and speedup_factor > 0:
            # Sleep simulated duration
            sim_sleep_seconds = (delta_mins * 60.0) / speedup_factor
            sim_sleep_seconds = min(sim_sleep_seconds, 3.5) # Cap sleep for snappy demo
            time.sleep(sim_sleep_seconds)

        if step_mode:
            input(f"{TermColors.BOLD}>> Press [ENTER] to trigger detection at Hop {hop_num}/{total_hops} ({cam_id})...{TermColors.RESET}")

        detection_timestamp = base_time + timedelta(minutes=offset_mins)
        ts_str = detection_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # Generate realistic image crop
        crop_path, crop_base64 = renderer.generate_plate_crop(
            plate_number=target_plate,
            vehicle_type="Sedan",
            is_commercial=False,
            night_mode=False
        )

        # Ingest to DB
        result = db.insert_detection(
            camera_id=cam_id,
            plate_number=target_plate,
            timestamp=detection_timestamp,
            speed_kmh=speed,
            vehicle_type="Sedan",
            confidence=0.994,
            crop_path=crop_path,
            crop_base64=crop_base64
        )

        # Forward to API if online to trigger WebSocket broadcast to live UI
        if api_online:
            try:
                payload = {
                    "camera_id": cam_id,
                    "plate_number": target_plate,
                    "timestamp": ts_str,
                    "speed_kmh": speed,
                    "vehicle_type": "Sedan",
                    "confidence": 0.994,
                    "crop_path": crop_path,
                    "crop_base64": crop_base64
                }
                requests.post(f"{api_url}/api/v1/ingest", json=payload, timeout=2.0)
            except Exception as e:
                pass

        # Print Rich Telemetry Alert Box
        print(f"{TermColors.RED}{TermColors.BOLD}╔════════════════════════════════════════════════════════════════════════════╗")
        print(f"║ 🚨 CRITICAL WATCHLIST INTERCEPT: HOP #{hop_num}/{total_hops} AT {cam_id:<28} ║")
        print(f"╠════════════════════════════════════════════════════════════════════════════╣{TermColors.RESET}")
        print(f"  {TermColors.BOLD}• Camera:{TermColors.RESET}     {cam_name} ({node['corridor']})")
        print(f"  {TermColors.BOLD}• GPS Coords:{TermColors.RESET} LAT: {node['lat']:.4f} | LNG: {node['lng']:.4f}")
        print(f"  {TermColors.BOLD}• Timestamp:{TermColors.RESET}  {ts_str} (+{offset_mins}m from start)")
        print(f"  {TermColors.BOLD}• Velocity:{TermColors.RESET}   {TermColors.YELLOW}{speed:.1f} km/h{TermColors.RESET}")
        print(f"  {TermColors.BOLD}• Plate Crop:{TermColors.RESET} {crop_path}")
        print(f"  {TermColors.BOLD}• Action:{TermColors.RESET}     {TermColors.GREEN}GIS Map Updated & Trajectory Vector Plotted{TermColors.RESET}")
        print(f"{TermColors.RED}╚════════════════════════════════════════════════════════════════════════════╝{TermColors.RESET}\n")

    # 3. Final Trajectory Summary Query
    print(f"\n{TermColors.BOLD}{TermColors.GREEN}========================================================================{TermColors.RESET}")
    print(f"{TermColors.BOLD}{TermColors.GREEN}✅ SIMULATION COMPLETE: RECONSTRUCTING FULL VEHICLE TRAJECTORY...{TermColors.RESET}")
    print(f"{TermColors.BOLD}{TermColors.GREEN}========================================================================{TermColors.RESET}")

    trajectory = db.get_trajectory(target_plate)

    print(f"• Target Plate:    {TermColors.BOLD}{trajectory['plate']}{TermColors.RESET}")
    print(f"• Vehicle Profile: {trajectory['vehicle']}")
    print(f"• Status:          {TermColors.RED}{trajectory['status']}{TermColors.RESET}")
    print(f"• Total Distance:  {TermColors.CYAN}{trajectory['totalDistance']}{TermColors.RESET}")
    print(f"• Average Speed:   {TermColors.YELLOW}{trajectory['avgSpeed']}{TermColors.RESET}")
    print(f"• Total Duration:  {TermColors.CYAN}{trajectory['travelDuration']}{TermColors.RESET}")
    print(f"• Violations:      {TermColors.RED}{trajectory['violations']} Flagged Events{TermColors.RESET}")
    print(f"• Total CCTV Hops: {len(trajectory['hops'])}")

    print(f"\n{TermColors.BOLD}Hops Sequence:{TermColors.RESET}")
    for hop in trajectory['hops']:
        print(f"  [{hop['hopIndex']}] {hop['time']} | {hop['camId']} - {hop['camName']:<32} | {hop['speed']:<8} | Lat: {hop['lat']:.4f}, Lng: {hop['lng']:.4f}")

    print(f"\n{TermColors.GREEN}{TermColors.BOLD}💡 Instant Trajectory Replay is now ready on the GIS Dashboard!{TermColors.RESET}")
    print(f"   Open: {TermColors.UNDERLINE}http://localhost:8000{TermColors.RESET} and search '{target_plate}'\n")

    return trajectory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Stolen Vehicle / Suspect Chase Simulation")
    parser.add_argument("--plate", type=str, default="HR26DQ5551", help="Target vehicle plate number")
    parser.add_argument("--model", type=str, default="Hyundai Verna (Polar White)", help="Vehicle model")
    parser.add_argument("--owner", type=str, default="R. Sharma / TechCorp Fleet", help="Owner description")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="FastAPI backend URL")
    parser.add_argument("--speedup", type=float, default=25.0, help="Simulation speedup multiplier")
    parser.add_argument("--step", action="store_true", help="Step-by-step interactive mode with prompt")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Path to SQLite database")
    args = parser.parse_args()

    run_chase_demo(
        target_plate=args.plate,
        vehicle_model=args.model,
        owner_name=args.owner,
        api_url=args.api_url,
        speedup_factor=args.speedup,
        step_mode=args.step,
        db_path=args.db
    )
