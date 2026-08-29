"""
Routing Service Module
Provides real-world street network routing and road path geometry calculations.
Integrates with Open Source Routing Machine (OSRM) with in-memory caching and fallback smoothing.
"""

import time
import math
import logging
from typing import List, Tuple, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Cache for routing responses: { coords_key: (timestamp, data) }
_ROUTING_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3600.0  # 1 hour cache


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance in meters between two points using Haversine formula."""
    R = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def generate_fallback_road_points(coords: List[Tuple[float, float]], num_subdivisions: int = 15) -> List[List[float]]:
    """
    Fallback curve generator in case network routing API is unreachable.
    Generates smooth road-like curves between points using Catmull-Rom spline interpolation.
    """
    if len(coords) < 2:
        return [[c[0], c[1]] for c in coords]

    result: List[List[float]] = []
    # For Catmull-Rom spline, pad start and end
    pts = [coords[0]] + coords + [coords[-1]]

    for i in range(1, len(pts) - 2):
        p0 = pts[i - 1]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[i + 2]

        for step in range(num_subdivisions):
            t = step / float(num_subdivisions)
            t2 = t * t
            t3 = t2 * t

            # Catmull-Rom basis matrix
            lon = 0.5 * ((2 * p1[0]) +
                         (-p0[0] + p2[0]) * t +
                         (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                         (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)

            lat = 0.5 * ((2 * p1[1]) +
                         (-p0[1] + p2[1]) * t +
                         (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                         (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)

            result.append([lon, lat])

    # Append final endpoint
    result.append([coords[-1][0], coords[-1][1]])
    return result


class RoutingService:
    OSRM_PUBLIC_URL = "https://router.project-osrm.org/route/v1/driving"

    @classmethod
    async def get_route(
        cls,
        coordinates_str: str,
        overview: str = "full",
        geometries: str = "geojson"
    ) -> Dict[str, Any]:
        """
        Fetches turn-by-turn real road path coordinates for a series of (lon, lat) pairs.
        Format of coordinates_str: 'lng1,lat1;lng2,lat2;lng3,lat3'
        """
        now = time.time()
        # Check in-memory cache
        cache_key = f"{coordinates_str}:{overview}:{geometries}"
        if cache_key in _ROUTING_CACHE:
            ts, cached_data = _ROUTING_CACHE[cache_key]
            if now - ts < CACHE_TTL_SECONDS:
                return cached_data

        # Parse coordinate pairs
        coord_pairs: List[Tuple[float, float]] = []
        try:
            for part in coordinates_str.split(";"):
                part = part.strip()
                if not part:
                    continue
                lon_s, lat_s = part.split(",")
                coord_pairs.append((float(lon_s), float(lat_s)))
        except Exception as e:
            logger.warning(f"Error parsing coordinates string '{coordinates_str}': {e}")
            return {
                "status": "error",
                "message": f"Invalid coordinates format: {e}",
                "coordinates": [],
                "distance_meters": 0.0,
                "duration_seconds": 0.0,
                "source": "invalid_input"
            }

        if len(coord_pairs) < 2:
            return {
                "status": "error",
                "message": "At least 2 coordinate waypoints required for routing",
                "coordinates": [[c[0], c[1]] for c in coord_pairs],
                "distance_meters": 0.0,
                "duration_seconds": 0.0,
                "source": "insufficient_points"
            }

        # Attempt to query OSRM Real Road Network API
        url = f"{cls.OSRM_PUBLIC_URL}/{coordinates_str}"
        params = {
            "overview": overview,
            "geometries": geometries,
            "steps": "true",
            "annotations": "false"
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    primary_route = data["routes"][0]
                    route_coords = primary_route["geometry"]["coordinates"]
                    total_dist_m = float(primary_route.get("distance", 0.0))
                    total_dur_s = float(primary_route.get("duration", 0.0))

                    legs_info = []
                    for leg in primary_route.get("legs", []):
                        legs_info.append({
                            "distance_meters": leg.get("distance", 0.0),
                            "duration_seconds": leg.get("duration", 0.0),
                            "summary": leg.get("summary", "")
                        })

                    result = {
                        "status": "ok",
                        "source": "osrm_real_road_network",
                        "coordinates": route_coords,  # [[lon, lat], [lon, lat], ...]
                        "total_points": len(route_coords),
                        "distance_meters": total_dist_m,
                        "distance_km": round(total_dist_m / 1000.0, 2),
                        "duration_seconds": total_dur_s,
                        "duration_minutes": round(total_dur_s / 60.0, 1),
                        "legs": legs_info
                    }

                    # Cache successful result
                    _ROUTING_CACHE[cache_key] = (now, result)
                    return result
                else:
                    logger.warning(f"OSRM returned non-OK status: {data.get('code')}")
        except Exception as err:
            logger.warning(f"OSRM API request failed ({err}), generating fallback smoothed path.")

        # Fallback: Generate smooth road trajectory
        fallback_coords = generate_fallback_road_points(coord_pairs, num_subdivisions=20)
        calc_dist_m = 0.0
        for i in range(len(fallback_coords) - 1):
            calc_dist_m += haversine_distance(
                fallback_coords[i][1], fallback_coords[i][0],
                fallback_coords[i + 1][1], fallback_coords[i + 1][0]
            )

        fallback_result = {
            "status": "ok",
            "source": "fallback_interpolated_network",
            "coordinates": fallback_coords,
            "total_points": len(fallback_coords),
            "distance_meters": calc_dist_m,
            "distance_km": round(calc_dist_m / 1000.0, 2),
            "duration_seconds": (calc_dist_m / 15.0),  # Approx 54 km/h (15 m/s)
            "duration_minutes": round((calc_dist_m / 15.0) / 60.0, 1),
            "legs": []
        }
        _ROUTING_CACHE[cache_key] = (now, fallback_result)
        return fallback_result
