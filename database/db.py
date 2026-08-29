"""
Database layer for City-Wide ANPR Trajectory & Alert System.
Provides SQLite persistence, indexing, watchlist lookup, trajectory graph queries, and analytics.
"""

import sqlite3
import json
import os
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "anpr_city.db")


class DatabaseManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Cameras Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cameras (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    region TEXT NOT NULL,
                    corridor TEXT,
                    speed_limit INTEGER DEFAULT 60,
                    status TEXT DEFAULT 'normal',
                    fps INTEGER DEFAULT 30,
                    resolution TEXT DEFAULT '4K',
                    stream_url TEXT,
                    adjacent_cameras TEXT,
                    distances_km TEXT
                )
            """)

            # 2. Watchlist / Hotlist Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    plate_number TEXT PRIMARY KEY,
                    vehicle_model TEXT,
                    owner_name TEXT,
                    alert_reason TEXT NOT NULL,
                    severity TEXT DEFAULT 'CRITICAL',
                    fir_number TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. Detections Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    plate_number TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    speed_kmh REAL NOT NULL,
                    vehicle_type TEXT DEFAULT 'Sedan',
                    confidence REAL DEFAULT 0.98,
                    crop_path TEXT,
                    crop_base64 TEXT,
                    is_watchlist_hit INTEGER DEFAULT 0,
                    is_speed_violation INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (camera_id) REFERENCES cameras(id)
                )
            """)

            # 4. Alerts Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'CRITICAL',
                    notes TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    detection_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (camera_id) REFERENCES cameras(id),
                    FOREIGN KEY (detection_id) REFERENCES detections(id)
                )
            """)

            # Indices for lightning-fast trajectory reconstruction and analytics
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_plate_time ON detections(plate_number, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_cam_time ON detections(camera_id, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections(timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_plate ON alerts(plate_number);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);")

            conn.commit()

    def sync_cameras(self, cameras_json_path: str):
        """Synchronizes camera configurations from config/cameras.json into the DB."""
        if not os.path.exists(cameras_json_path):
            return
        with open(cameras_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cameras = data.get("cameras", [])

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for cam in cameras:
                cursor.execute("""
                    INSERT INTO cameras (
                        id, name, lat, lng, region, corridor, speed_limit, status, fps, resolution, stream_url, adjacent_cameras, distances_km
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        lat=excluded.lat,
                        lng=excluded.lng,
                        region=excluded.region,
                        corridor=excluded.corridor,
                        speed_limit=excluded.speed_limit,
                        status=excluded.status,
                        fps=excluded.fps,
                        resolution=excluded.resolution,
                        stream_url=excluded.stream_url,
                        adjacent_cameras=excluded.adjacent_cameras,
                        distances_km=excluded.distances_km
                """, (
                    cam["id"],
                    cam["name"],
                    cam["lat"],
                    cam["lng"],
                    cam.get("region", "central"),
                    cam.get("corridor", ""),
                    cam.get("speedLimit", 60),
                    cam.get("status", "normal"),
                    cam.get("fps", 30),
                    cam.get("resolution", "4K"),
                    cam.get("streamUrl", ""),
                    json.dumps(cam.get("adjacentCameras", [])),
                    json.dumps(cam.get("distancesKm", {}))
                ))
            conn.commit()

    def add_to_watchlist(self, plate_number: str, vehicle_model: str, owner_name: str, alert_reason: str, severity: str = "CRITICAL", fir_number: str = ""):
        plate = plate_number.upper().strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO watchlist (plate_number, vehicle_model, owner_name, alert_reason, severity, fir_number, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(plate_number) DO UPDATE SET
                    vehicle_model=excluded.vehicle_model,
                    owner_name=excluded.owner_name,
                    alert_reason=excluded.alert_reason,
                    severity=excluded.severity,
                    fir_number=excluded.fir_number,
                    is_active=1
            """, (plate, vehicle_model, owner_name, alert_reason, severity, fir_number))
            conn.commit()

    def check_watchlist(self, plate_number: str) -> Optional[Dict[str, Any]]:
        plate = plate_number.upper().strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM watchlist WHERE plate_number = ? AND is_active = 1", (plate,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def insert_detection(self, camera_id: str, plate_number: str, timestamp: datetime, speed_kmh: float,
                         vehicle_type: str = "Sedan", confidence: float = 0.98, crop_path: str = "",
                         crop_base64: str = "") -> Dict[str, Any]:
        """
        Inserts a single detection event.
        Checks for watchlist hit and speed violations automatically.
        """
        plate = plate_number.upper().strip()
        watchlist_hit = self.check_watchlist(plate)
        is_watchlist = 1 if watchlist_hit else 0

        # Retrieve camera speed limit
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT speed_limit FROM cameras WHERE id = ?", (camera_id,))
            cam_row = cursor.fetchone()
            speed_limit = cam_row["speed_limit"] if cam_row else 60
            is_speeding = 1 if speed_kmh > speed_limit else 0

            ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(timestamp, datetime) else str(timestamp)

            cursor.execute("""
                INSERT INTO detections (
                    camera_id, plate_number, timestamp, speed_kmh, vehicle_type,
                    confidence, crop_path, crop_base64, is_watchlist_hit, is_speed_violation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                camera_id, plate, ts_str, speed_kmh, vehicle_type,
                confidence, crop_path, crop_base64, is_watchlist, is_speeding
            ))
            detection_id = cursor.lastrowid

            alert_created = None
            if is_watchlist:
                alert_type = "WATCHLIST_MATCH"
                severity = watchlist_hit.get("severity", "CRITICAL")
                notes = f"{watchlist_hit.get('alert_reason')} | Owner: {watchlist_hit.get('owner_name')} | Model: {watchlist_hit.get('vehicle_model')}"
                cursor.execute("""
                    INSERT INTO alerts (plate_number, camera_id, timestamp, alert_type, severity, notes, status, detection_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                """, (plate, camera_id, ts_str, alert_type, severity, notes, detection_id))
                alert_created = {
                    "alert_id": cursor.lastrowid,
                    "plate_number": plate,
                    "camera_id": camera_id,
                    "timestamp": ts_str,
                    "alert_type": alert_type,
                    "severity": severity,
                    "notes": notes
                }
            elif is_speeding:
                alert_type = "SPEED_VIOLATION"
                severity = "MODERATE" if speed_kmh < speed_limit + 25 else "HIGH"
                notes = f"Speeding violation: {speed_kmh:.1f} km/h in {speed_limit} km/h zone (+{speed_kmh-speed_limit:.1f} km/h)"
                cursor.execute("""
                    INSERT INTO alerts (plate_number, camera_id, timestamp, alert_type, severity, notes, status, detection_id)
                    VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                """, (plate, camera_id, ts_str, alert_type, severity, notes, detection_id))
                alert_created = {
                    "alert_id": cursor.lastrowid,
                    "plate_number": plate,
                    "camera_id": camera_id,
                    "timestamp": ts_str,
                    "alert_type": alert_type,
                    "severity": severity,
                    "notes": notes
                }

            conn.commit()

        return {
            "detection_id": detection_id,
            "plate_number": plate,
            "camera_id": camera_id,
            "timestamp": ts_str,
            "speed_kmh": speed_kmh,
            "is_watchlist_hit": bool(is_watchlist),
            "is_speed_violation": bool(is_speeding),
            "alert": alert_created
        }

    def get_trajectory(self, plate_number: str) -> Dict[str, Any]:
        """
        Reconstructs the full spatial-temporal trajectory hops of a given license plate.
        Calculates cumulative distance, average speed, elapsed time, and violations.
        """
        plate = plate_number.upper().strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if in watchlist
            cursor.execute("SELECT * FROM watchlist WHERE plate_number = ?", (plate,))
            wl_info = cursor.fetchone()
            is_watchlist = bool(wl_info)

            # Query all detections sorted chronologically
            cursor.execute("""
                SELECT d.*, c.name as cam_name, c.lat, c.lng, c.region, c.speed_limit, c.corridor
                FROM detections d
                JOIN cameras c ON d.camera_id = c.id
                WHERE d.plate_number = ?
                ORDER BY d.timestamp ASC
            """, (plate,))
            rows = cursor.fetchall()

        if not rows:
            return {
                "plate": plate,
                "found": False,
                "hops": [],
                "totalDistance": "0.0 km",
                "avgSpeed": "0.0 km/h",
                "travelDuration": "0m 0s",
                "violations": 0
            }

        hops = []
        total_dist_km = 0.0
        speeds = []
        violations_count = 0
        first_time = None
        last_time = None

        for idx, r in enumerate(rows):
            dt = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") if isinstance(r["timestamp"], str) else r["timestamp"]
            if idx == 0:
                first_time = dt
            last_time = dt

            speed = r["speed_kmh"]
            speeds.append(speed)
            if r["is_speed_violation"] or r["is_watchlist_hit"]:
                violations_count += 1

            if idx > 0:
                prev_lat = rows[idx-1]["lat"]
                prev_lng = rows[idx-1]["lng"]
                # Haversine distance
                d_km = self._haversine(prev_lat, prev_lng, r["lat"], r["lng"])
                total_dist_km += d_km

            hops.append({
                "hopIndex": idx + 1,
                "camId": r["camera_id"],
                "camName": r["cam_name"],
                "time": dt.strftime("%H:%M:%S"),
                "dateTime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "speed": f"{int(round(speed))} km/h",
                "speedVal": speed,
                "speedLimit": r["speed_limit"],
                "lat": r["lat"],
                "lng": r["lng"],
                "corridor": r["corridor"],
                "vehicleType": r["vehicle_type"],
                "confidence": f"{r['confidence'] * 100:.1f}%",
                "cropPath": r["crop_path"],
                "cropBase64": r["crop_base64"]
            })

        duration_sec = int((last_time - first_time).total_seconds()) if first_time and last_time else 0
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:02d}s"

        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

        vehicle_desc = wl_info["vehicle_model"] if wl_info and wl_info["vehicle_model"] else f"{rows[-1]['vehicle_type']} (Classified)"
        owner_desc = wl_info["owner_name"] if wl_info and wl_info["owner_name"] else "Regional Transport Record Verified"
        status_desc = "ALERT: CRITICAL WATCHLIST" if is_watchlist else "TRACKED - ACTIVE"

        return {
            "plate": plate,
            "found": True,
            "vehicle": vehicle_desc,
            "owner": owner_desc,
            "status": status_desc,
            "isWatchlist": is_watchlist,
            "alertReason": wl_info["alert_reason"] if wl_info else "",
            "hops": hops,
            "totalDistance": f"{total_dist_km:.1f} km",
            "avgSpeed": f"{avg_speed:.1f} km/h",
            "travelDuration": duration_str,
            "violations": violations_count
        }

    def get_analytics_kpis(self) -> Dict[str, Any]:
        """Calculates 24-hour summary metrics, hourly volume, vehicle distributions, and violations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total counts
            cursor.execute("SELECT COUNT(*) as cnt FROM detections")
            total_detections = cursor.fetchone()["cnt"]

            cursor.execute("SELECT AVG(speed_kmh) as avg_spd FROM detections")
            avg_speed = cursor.fetchone()["avg_spd"] or 0.0

            cursor.execute("SELECT COUNT(*) as cnt FROM alerts WHERE status = 'ACTIVE'")
            active_alerts = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(DISTINCT plate_number) as cnt FROM detections")
            unique_vehicles = cursor.fetchone()["cnt"]

            # Vehicle distribution
            cursor.execute("SELECT vehicle_type, COUNT(*) as cnt FROM detections GROUP BY vehicle_type")
            type_rows = cursor.fetchall()
            vehicle_distribution = {r["vehicle_type"]: r["cnt"] for r in type_rows}

            # Top congested / active cameras
            cursor.execute("""
                SELECT c.id, c.name, COUNT(d.id) as detection_count, AVG(d.speed_kmh) as avg_speed
                FROM cameras c
                LEFT JOIN detections d ON c.id = d.camera_id
                GROUP BY c.id
                ORDER BY detection_count DESC
            """)
            camera_stats = [dict(r) for r in cursor.fetchall()]

            # Hourly distribution for today
            cursor.execute("""
                SELECT strftime('%H:00', timestamp) as hour_slot, COUNT(*) as count
                FROM detections
                GROUP BY hour_slot
                ORDER BY hour_slot ASC
            """)
            hourly_data = [dict(r) for r in cursor.fetchall()]

        return {
            "totalDetections": total_detections,
            "uniqueVehicles": unique_vehicles,
            "avgSpeedKmh": round(avg_speed, 1),
            "activeAlerts": active_alerts,
            "vehicleDistribution": vehicle_distribution,
            "cameraStats": camera_stats,
            "hourlyVolume": hourly_data
        }

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        R = 6371.0 # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
