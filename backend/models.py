from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ==========================================
# SQLAlchemy ORM Models
# ==========================================

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    zone = Column(String(64), nullable=False, default="Central")
    direction = Column(String(64), nullable=False, default="Both")
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    detections = relationship("Detection", back_populates="camera", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plate_number = Column(String(32), nullable=False, index=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    confidence = Column(Float, nullable=False, default=0.95)
    crop_path = Column(String(256), nullable=True)
    vehicle_type = Column(String(32), nullable=False, default="car")

    camera = relationship("Camera", back_populates="detections")

    __table_args__ = (
        Index("ix_detections_plate_time", "plate_number", "timestamp"),
        Index("ix_detections_cam_time", "camera_id", "timestamp"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    plate_number = Column(String(32), primary_key=True, index=True)
    reason = Column(String(128), nullable=False)  # stolen, wanted, suspect, traffic_violation
    severity = Column(String(32), nullable=False, default="high")  # high, medium, low
    notes = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plate_number = Column(String(32), nullable=False, index=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    reason = Column(String(128), nullable=False)
    severity = Column(String(32), nullable=False, default="high")
    match_type = Column(String(16), nullable=False, default="exact")  # exact or fuzzy
    matched_watchlist_plate = Column(String(32), nullable=False)
    crop_path = Column(String(256), nullable=True)
    acknowledged = Column(Boolean, default=False, nullable=False)

    camera = relationship("Camera", back_populates="alerts")


# ==========================================
# Pydantic Schemas (Request / Response)
# ==========================================

class CameraBase(BaseModel):
    name: str
    latitude: float
    longitude: float
    zone: str = "Central"
    direction: str = "Both"
    status: str = "active"


class CameraCreate(CameraBase):
    id: str


class CameraResponse(CameraBase):
    id: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DetectionIngest(BaseModel):
    plate_number: str
    camera_id: str
    timestamp: Optional[datetime] = None
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    crop_path: Optional[str] = None
    vehicle_type: str = "car"


class DetectionResponse(BaseModel):
    id: int
    plate_number: str
    camera_id: str
    timestamp: datetime
    confidence: float
    crop_path: Optional[str] = None
    vehicle_type: str
    camera_name: Optional[str] = None
    camera_zone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WatchlistCreate(BaseModel):
    plate_number: str
    reason: str
    severity: str = "high"
    notes: Optional[str] = None


class WatchlistResponse(BaseModel):
    plate_number: str
    reason: str
    severity: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertResponse(BaseModel):
    id: int
    plate_number: str
    camera_id: str
    camera_name: Optional[str] = None
    camera_latitude: Optional[float] = None
    camera_longitude: Optional[float] = None
    timestamp: datetime
    reason: str
    severity: str
    match_type: str
    matched_watchlist_plate: str
    crop_path: Optional[str] = None
    acknowledged: bool

    model_config = ConfigDict(from_attributes=True)


# Trajectory Schemas
class CameraNode(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    zone: str


class TrajectoryHop(BaseModel):
    from_camera: CameraNode
    to_camera: CameraNode
    start_time: datetime
    end_time: datetime
    time_delta_seconds: float
    distance_meters: float
    distance_km: float
    speed_kmh: float
    anomaly_speed: bool = False
    confidence: float = 0.95


class TrajectoryDetectionPoint(BaseModel):
    detection_id: int
    camera_id: str
    camera_name: str
    latitude: float
    longitude: float
    zone: str
    timestamp: datetime
    confidence: float
    crop_path: Optional[str] = None
    vehicle_type: str


class TrajectoryResponse(BaseModel):
    plate_number: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_detections: int
    total_hops: int
    total_distance_km: float
    total_duration_minutes: float
    avg_speed_kmh: float
    max_speed_kmh: float
    speed_anomalies_detected: int
    detection_points: List[TrajectoryDetectionPoint]
    hops: List[TrajectoryHop]
    route_coordinates: List[List[float]]  # [[lng, lat], [lng, lat], ...] for GIS GeoJSON standard


# Analytics Schemas
class AnalyticsSummary(BaseModel):
    total_detections_today: int
    unique_vehicles_today: int
    active_cameras: int
    total_cameras: int
    hotlist_alerts_today: int
    peak_hour: Optional[int] = None
    peak_hour_count: int = 0


class JunctionFlow(BaseModel):
    camera_id: str
    camera_name: str
    zone: str
    latitude: float
    longitude: float
    vehicle_count: int
    flow_rate_vph: float  # vehicles per hour estimated
    congestion_level: str  # Low, Moderate, High, Severe


class HourlyTrend(BaseModel):
    hour: int  # 0 to 23
    count: int


class VehicleTypeBreakdown(BaseModel):
    vehicle_type: str
    count: int
    percentage: float


class CongestionAnalytics(BaseModel):
    top_congested_junctions: List[JunctionFlow]
    hourly_trends: List[HourlyTrend]
    vehicle_breakdown: List[VehicleTypeBreakdown]
    total_flow_rate_vph: float


class HeatmapPoint(BaseModel):
    camera_id: str
    camera_name: str
    latitude: float
    longitude: float
    weight: float
    detection_count: int
    zone: str


class GeoJSONGeometry(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: Dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]
