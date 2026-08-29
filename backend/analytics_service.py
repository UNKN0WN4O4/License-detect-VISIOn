from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, extract

from backend.models import Detection, Camera, Alert


class AnalyticsService:
    @staticmethod
    async def get_summary(session: AsyncSession) -> Dict[str, Any]:
        """
        Computes high-level KPI metrics for the city dashboard.
        """
        now = datetime.now(timezone.utc)
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

        # Total detections today
        det_today_res = await session.execute(
            select(func.count(Detection.id)).where(Detection.timestamp >= start_of_day)
        )
        total_detections_today = det_today_res.scalar() or 0

        # Unique vehicles today
        uniq_today_res = await session.execute(
            select(func.count(distinct(Detection.plate_number))).where(Detection.timestamp >= start_of_day)
        )
        unique_vehicles_today = uniq_today_res.scalar() or 0

        # Fallback if no detections today (e.g. initial demo load)
        if total_detections_today == 0:
            det_all_res = await session.execute(select(func.count(Detection.id)))
            total_detections_today = det_all_res.scalar() or 0

            uniq_all_res = await session.execute(select(func.count(distinct(Detection.plate_number))))
            unique_vehicles_today = uniq_all_res.scalar() or 0

        # Camera counts
        total_cams_res = await session.execute(select(func.count(Camera.id)))
        total_cameras = total_cams_res.scalar() or 0

        active_cams_res = await session.execute(
            select(func.count(Camera.id)).where(Camera.status == "active")
        )
        active_cameras = active_cams_res.scalar() or 0

        # Alerts today
        alerts_today_res = await session.execute(
            select(func.count(Alert.id)).where(Alert.timestamp >= start_of_day)
        )
        hotlist_alerts_today = alerts_today_res.scalar() or 0
        if hotlist_alerts_today == 0:
            alerts_all_res = await session.execute(select(func.count(Alert.id)))
            hotlist_alerts_today = alerts_all_res.scalar() or 0

        # Peak Hour Detection
        hourly_query = (
            select(
                extract('hour', Detection.timestamp).label("hour"),
                func.count(Detection.id).label("count")
            )
            .group_by("hour")
            .order_by(func.count(Detection.id).desc())
            .limit(1)
        )
        peak_res = await session.execute(hourly_query)
        peak_row = peak_res.first()

        peak_hour = int(peak_row[0]) if peak_row and peak_row[0] is not None else None
        peak_hour_count = int(peak_row[1]) if peak_row and peak_row[1] is not None else 0

        return {
            "total_detections_today": total_detections_today,
            "unique_vehicles_today": unique_vehicles_today,
            "active_cameras": active_cameras,
            "total_cameras": total_cameras,
            "hotlist_alerts_today": hotlist_alerts_today,
            "peak_hour": peak_hour,
            "peak_hour_count": peak_hour_count
        }

    @staticmethod
    async def get_congestion(session: AsyncSession) -> Dict[str, Any]:
        """
        Calculates per-camera traffic flow rate, top 5 congested junctions,
        24-hour trends, and vehicle category distribution.
        """
        # Fetch all cameras
        cams_res = await session.execute(select(Camera))
        cameras: List[Camera] = cams_res.scalars().all()
        cam_map = {c.id: c for c in cameras}

        # Detection counts per camera in last 24h
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)

        flow_query = (
            select(
                Detection.camera_id,
                func.count(Detection.id).label("count")
            )
            .where(Detection.timestamp >= since_24h)
            .group_by(Detection.camera_id)
            .order_by(func.count(Detection.id).desc())
        )
        flow_res = await session.execute(flow_query)
        camera_counts = dict(flow_res.all())

        # Fallback to all time if past 24h has zero detections
        if not camera_counts:
            flow_query_all = (
                select(
                    Detection.camera_id,
                    func.count(Detection.id).label("count")
                )
                .group_by(Detection.camera_id)
                .order_by(func.count(Detection.id).desc())
            )
            flow_res = await session.execute(flow_query_all)
            camera_counts = dict(flow_res.all())

        junction_flows = []
        total_detections_all_cams = sum(camera_counts.values())

        for cam_id, cam in cam_map.items():
            count = camera_counts.get(cam_id, 0)
            flow_vph = round(count / 24.0, 1)  # average hourly flow rate

            if flow_vph >= 50:
                congestion = "Severe"
            elif flow_vph >= 25:
                congestion = "High"
            elif flow_vph >= 10:
                congestion = "Moderate"
            else:
                congestion = "Low"

            junction_flows.append({
                "camera_id": cam_id,
                "camera_name": cam.name,
                "zone": cam.zone,
                "latitude": cam.latitude,
                "longitude": cam.longitude,
                "vehicle_count": count,
                "flow_rate_vph": flow_vph,
                "congestion_level": congestion
            })

        # Sort top 5 congested
        junction_flows.sort(key=lambda x: x["vehicle_count"], reverse=True)
        top_congested = junction_flows[:5]

        # 24-hour distribution
        hourly_counts_map = {h: 0 for h in range(24)}
        trend_query = (
            select(
                extract('hour', Detection.timestamp).label("hour"),
                func.count(Detection.id).label("count")
            )
            .group_by("hour")
        )
        trend_res = await session.execute(trend_query)
        for h, cnt in trend_res.all():
            if h is not None:
                hourly_counts_map[int(h)] = int(cnt)

        hourly_trends = [{"hour": h, "count": cnt} for h, cnt in hourly_counts_map.items()]

        # Vehicle type breakdown
        vtype_query = (
            select(
                Detection.vehicle_type,
                func.count(Detection.id).label("count")
            )
            .group_by(Detection.vehicle_type)
        )
        vtype_res = await session.execute(vtype_query)
        vtype_data = vtype_res.all()

        total_vtypes = sum(cnt for _, cnt in vtype_data) or 1
        vehicle_breakdown = [
            {
                "vehicle_type": vtype or "car",
                "count": cnt,
                "percentage": round((cnt / total_vtypes) * 100.0, 1)
            }
            for vtype, cnt in vtype_data
        ]

        total_flow_rate_vph = round(total_detections_all_cams / 24.0, 1)

        return {
            "top_congested_junctions": top_congested,
            "hourly_trends": hourly_trends,
            "vehicle_breakdown": vehicle_breakdown,
            "total_flow_rate_vph": total_flow_rate_vph
        }

    @staticmethod
    async def get_heatmap(session: AsyncSession) -> Dict[str, Any]:
        """
        Generates GeoJSON FeatureCollection and weighted intensity points for GIS mapping.
        """
        cams_res = await session.execute(select(Camera))
        cameras = cams_res.scalars().all()

        # Detections count per camera
        count_res = await session.execute(
            select(
                Detection.camera_id,
                func.count(Detection.id).label("count")
            ).group_by(Detection.camera_id)
        )
        counts_map = dict(count_res.all())
        max_count = max(counts_map.values()) if counts_map else 1
        max_count = max(max_count, 1)

        points = []
        features = []

        for cam in cameras:
            cnt = counts_map.get(cam.id, 0)
            weight = round(cnt / float(max_count), 3) if max_count > 0 else 0.0

            pt = {
                "camera_id": cam.id,
                "camera_name": cam.name,
                "latitude": cam.latitude,
                "longitude": cam.longitude,
                "weight": weight,
                "detection_count": cnt,
                "zone": cam.zone
            }
            points.append(pt)

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [cam.longitude, cam.latitude]
                },
                "properties": {
                    "camera_id": cam.id,
                    "camera_name": cam.name,
                    "zone": cam.zone,
                    "status": cam.status,
                    "weight": weight,
                    "detection_count": cnt
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return {
            "points": points,
            "geojson": geojson,
            "total_nodes": len(points)
        }
