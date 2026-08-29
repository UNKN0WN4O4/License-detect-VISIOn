import math
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.models import Detection, Camera
from backend.alert_manager import normalize_plate


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two geographic coordinates in kilometers.
    """
    R = 6371.0  # Earth radius in kilometers

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c


class TrajectoryService:
    @staticmethod
    async def reconstruct_trajectory(
        session: AsyncSession,
        plate_number: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        speed_anomaly_threshold_kmh: float = 160.0
    ) -> Dict[str, Any]:
        """
        Reconstructs the full spatio-temporal trajectory for a license plate.
        Calculates Haversine distance, travel time, and speed for each hop.
        """
        clean_plate = normalize_plate(plate_number)

        # Build query
        query = (
            select(Detection)
            .options(joinedload(Detection.camera))
            .where(Detection.plate_number == clean_plate)
        )

        if start_time:
            query = query.where(Detection.timestamp >= start_time)
        if end_time:
            query = query.where(Detection.timestamp <= end_time)

        query = query.order_by(Detection.timestamp.asc())

        result = await session.execute(query)
        detections: List[Detection] = result.scalars().all()

        if not detections:
            return {
                "plate_number": clean_plate,
                "start_time": start_time,
                "end_time": end_time,
                "total_detections": 0,
                "total_hops": 0,
                "total_distance_km": 0.0,
                "total_duration_minutes": 0.0,
                "avg_speed_kmh": 0.0,
                "max_speed_kmh": 0.0,
                "speed_anomalies_detected": 0,
                "detection_points": [],
                "hops": [],
                "route_coordinates": []
            }

        detection_points = []
        route_coordinates = []

        for d in detections:
            cam = d.camera
            lat = cam.latitude if cam else 0.0
            lng = cam.longitude if cam else 0.0
            cam_name = cam.name if cam else d.camera_id
            cam_zone = cam.zone if cam else "Central"

            pt = {
                "detection_id": d.id,
                "camera_id": d.camera_id,
                "camera_name": cam_name,
                "latitude": lat,
                "longitude": lng,
                "zone": cam_zone,
                "timestamp": d.timestamp.isoformat(),
                "confidence": d.confidence,
                "crop_path": d.crop_path,
                "vehicle_type": d.vehicle_type
            }
            detection_points.append(pt)
            route_coordinates.append([lng, lat])

        hops = []
        total_distance_km = 0.0
        max_speed_kmh = 0.0
        speed_anomalies_count = 0

        # Compute consecutive hops
        for i in range(len(detections) - 1):
            d1 = detections[i]
            d2 = detections[i + 1]

            cam1 = d1.camera
            cam2 = d2.camera

            lat1 = cam1.latitude if cam1 else 0.0
            lon1 = cam1.longitude if cam1 else 0.0
            lat2 = cam2.latitude if cam2 else 0.0
            lon2 = cam2.longitude if cam2 else 0.0

            # Distance in km and meters
            dist_km = haversine_distance_km(lat1, lon1, lat2, lon2)
            dist_m = dist_km * 1000.0
            total_distance_km += dist_km

            # Time delta in seconds
            time_delta_sec = (d2.timestamp - d1.timestamp).total_seconds()
            time_delta_sec = max(time_delta_sec, 0.0)

            # Speed calculation in km/h
            if time_delta_sec > 0:
                speed_kmh = (dist_km / (time_delta_sec / 3600.0))
            else:
                speed_kmh = 0.0 if dist_km == 0.0 else 999.9  # Instant teleportation

            # Check speed anomaly (teleportation / clone plate / extreme speeding)
            is_anomaly = (speed_kmh > speed_anomaly_threshold_kmh) and (dist_km > 0.05)
            if is_anomaly:
                speed_anomalies_count += 1

            if not is_anomaly:
                max_speed_kmh = max(max_speed_kmh, speed_kmh)

            hop = {
                "from_camera": {
                    "id": cam1.id if cam1 else d1.camera_id,
                    "name": cam1.name if cam1 else d1.camera_id,
                    "latitude": lat1,
                    "longitude": lon1,
                    "zone": cam1.zone if cam1 else "Central"
                },
                "to_camera": {
                    "id": cam2.id if cam2 else d2.camera_id,
                    "name": cam2.name if cam2 else d2.camera_id,
                    "latitude": lat2,
                    "longitude": lon2,
                    "zone": cam2.zone if cam2 else "Central"
                },
                "start_time": d1.timestamp.isoformat(),
                "end_time": d2.timestamp.isoformat(),
                "time_delta_seconds": round(time_delta_sec, 1),
                "distance_meters": round(dist_m, 1),
                "distance_km": round(dist_km, 3),
                "speed_kmh": round(speed_kmh, 1),
                "anomaly_speed": is_anomaly,
                "confidence": min(d1.confidence, d2.confidence)
            }
            hops.append(hop)

        # Formatted waypoint hops for UI / E2E test client
        formatted_hops = []
        for i, pt in enumerate(detection_points):
            spd = "60 km/h"
            if i < len(hops):
                spd = f"{round(hops[i]['speed_kmh'])} km/h"
            elif i > 0 and (i - 1) < len(hops):
                spd = f"{round(hops[i-1]['speed_kmh'])} km/h"

            formatted_hops.append({
                "camId": pt["camera_id"],
                "camName": pt["camera_name"],
                "time": pt["timestamp"].split("T")[-1] if "T" in pt["timestamp"] else pt["timestamp"],
                "speed": spd,
                "lat": pt["latitude"],
                "lng": pt["longitude"]
            })

        # Overall Journey Metrics
        first_time = detections[0].timestamp
        last_time = detections[-1].timestamp
        total_duration_sec = (last_time - first_time).total_seconds()
        total_duration_minutes = max(round(total_duration_sec / 60.0, 1), 0.0)

        if total_duration_sec > 0 and total_distance_km > 0:
            avg_speed_kmh = round((total_distance_km / (total_duration_sec / 3600.0)), 1)
        else:
            avg_speed_kmh = 0.0

        return {
            "plate_number": clean_plate,
            "start_time": first_time.isoformat(),
            "end_time": last_time.isoformat(),
            "total_detections": len(detections),
            "total_hops": len(hops),
            "total_distance_km": round(total_distance_km, 3),
            "total_duration_minutes": total_duration_minutes,
            "avg_speed_kmh": avg_speed_kmh,
            "max_speed_kmh": round(max_speed_kmh, 1),
            "speed_anomalies_detected": speed_anomalies_count,
            "detection_points": detection_points,
            "hops": hops,
            "waypoint_hops": formatted_hops,
            "route_coordinates": route_coordinates
        }
