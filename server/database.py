"""
IBVAP Event Persistence Layer: SQLite Database with SQLAlchemy
Provides structured schema and optimized indexed queries for border surveillance
security incidents, audit trails, and forensic reviews.
"""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Float,
    Index,
    Integer,
    String,
    create_engine,
    desc,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

logger = logging.getLogger("ibvap.database")


class Base(DeclarativeBase):
    """SQLAlchemy Declarative Base."""
    pass


class IncidentModel(Base):
    """
    SQLAlchemy model representing a security breach incident record.
    Indexed for fast forensic querying by timestamp, event type, camera, and track.
    """
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    iso_timestamp: Mapped[str] = mapped_column(String(32), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), default="person", nullable=False)
    zone_id: Mapped[str] = mapped_column(String(64), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    feet_x: Mapped[float] = mapped_column(Float, nullable=False)
    feet_y: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_path: Mapped[str] = mapped_column(String(256), nullable=False)

    __table_args__ = (
        Index("idx_incidents_cam_time", "camera_id", "timestamp"),
        Index("idx_incidents_type_time", "event_type", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert database record to dictionary representation."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "iso_timestamp": self.iso_timestamp,
            "camera_id": self.camera_id,
            "event_type": self.event_type,
            "track_id": self.track_id,
            "object_type": self.object_type,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "direction": self.direction,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "frame_index": self.frame_index,
            "feet_point": [round(self.feet_x, 2), round(self.feet_y, 2)],
            "snapshot_path": self.snapshot_path,
        }


class IncidentDatabase:
    """
    Database access service encapsulating connection pooling, schema initialization,
    and indexed query operations for border surveillance incidents.
    Supports both SQLite (local development/tests) and PostgreSQL (Supabase cloud).
    """

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask credentials in database URL for safe logging."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return parsed._replace(netloc=netloc).geturl()
            return url
        except Exception:
            return "postgresql+psycopg2://***"

    @staticmethod
    def normalize_db_url(raw_url: Union[str, Path]) -> str:
        """
        Normalize database URLs for SQLAlchemy.
        Ensures PostgreSQL URLs explicitly use the psycopg2 dialect driver
        (postgresql+psycopg2://) to match the installed psycopg2-binary driver
        and avoid ModuleNotFoundError for psycopg (v3).
        """
        url = str(raw_url).strip()
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://"):]
        if url.startswith("postgresql+psycopg://"):
            return "postgresql+psycopg2://" + url[len("postgresql+psycopg://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url

    def __init__(self, db_path_or_url: Optional[Union[str, Path]] = None):
        import os

        # Priority: explicit argument -> DATABASE_URL environment variable -> default SQLite path
        raw = db_path_or_url or os.environ.get("DATABASE_URL") or "data/events.db"
        normalized = self.normalize_db_url(raw)

        is_sqlite = normalized.startswith("sqlite") or not normalized.startswith("postgresql")

        if is_sqlite:
            if normalized.startswith("sqlite://"):
                self.db_url = normalized
            else:
                p = Path(normalized)
                p.parent.mkdir(parents=True, exist_ok=True)
                self.db_url = f"sqlite:///{p.resolve()}"

            logger.info(f"Connecting to SQLite Database: {self.db_url}")
            self.engine = create_engine(
                self.db_url,
                connect_args={"check_same_thread": False},
                echo=False,
            )
        else:
            self.db_url = normalized
            masked_url = self._mask_url(self.db_url)
            logger.info(f"Connecting to PostgreSQL Database: {masked_url}")
            self.engine = create_engine(
                self.db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False,
            )

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        # Create tables automatically
        Base.metadata.create_all(bind=self.engine)
        logger.info("Incident Database schema initialized successfully.")


    def create_incident(self, data: Dict[str, Any]) -> IncidentModel:
        """Insert a new security incident record into SQLite."""
        ts = float(data.get("timestamp", datetime.now(timezone.utc).timestamp()))
        iso_ts = data.get("iso_timestamp")
        if not iso_ts:
            iso_ts = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        feet_pt = data.get("feet_point", [0.0, 0.0])
        feet_x = float(data.get("feet_x", feet_pt[0] if len(feet_pt) > 0 else 0.0))
        feet_y = float(data.get("feet_y", feet_pt[1] if len(feet_pt) > 1 else 0.0))

        incident = IncidentModel(
            timestamp=ts,
            iso_timestamp=iso_ts,
            camera_id=str(data["camera_id"]),
            event_type=str(data["event_type"]),
            track_id=int(data["track_id"]),
            object_type=str(data.get("object_type", "person")),
            zone_id=str(data["zone_id"]),
            zone_name=str(data["zone_name"]),
            direction=str(data["direction"]) if data.get("direction") else None,
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            frame_index=int(data.get("frame_index", 0)),
            feet_x=feet_x,
            feet_y=feet_y,
            snapshot_path=str(data.get("snapshot_path", "")),
        )

        with self.SessionLocal() as session:
            session.add(incident)
            session.commit()
            session.refresh(incident)
            logger.info(
                f"Logged Incident #{incident.id} [{incident.event_type}] | "
                f"Camera: {incident.camera_id} | Track: #{incident.track_id}"
            )
            return incident

    def get_incident_by_id(self, incident_id: int) -> Optional[IncidentModel]:
        """Retrieve an incident record by primary key."""
        with self.SessionLocal() as session:
            stmt = select(IncidentModel).where(IncidentModel.id == incident_id)
            return session.scalars(stmt).first()

    def get_recent_incidents(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[IncidentModel]:
        """Retrieve latest incidents ordered by descending timestamp."""
        with self.SessionLocal() as session:
            stmt = (
                select(IncidentModel)
                .order_by(desc(IncidentModel.timestamp))
                .offset(offset)
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_incidents_by_date_range(
        self,
        start_time: float,
        end_time: float,
    ) -> List[IncidentModel]:
        """Query incidents occurring between start and end timestamps."""
        with self.SessionLocal() as session:
            stmt = (
                select(IncidentModel)
                .where(IncidentModel.timestamp >= start_time)
                .where(IncidentModel.timestamp <= end_time)
                .order_by(desc(IncidentModel.timestamp))
            )
            return list(session.scalars(stmt).all())

    def get_incidents_by_event_type(
        self,
        event_type: str,
        limit: int = 100,
    ) -> List[IncidentModel]:
        """Query incidents filtered by event type (e.g. ZONE_INTRUSION)."""
        with self.SessionLocal() as session:
            stmt = (
                select(IncidentModel)
                .where(IncidentModel.event_type == event_type)
                .order_by(desc(IncidentModel.timestamp))
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_incidents_by_camera(
        self,
        camera_id: str,
        limit: int = 100,
    ) -> List[IncidentModel]:
        """Query incidents originating from a specific surveillance camera node."""
        with self.SessionLocal() as session:
            stmt = (
                select(IncidentModel)
                .where(IncidentModel.camera_id == camera_id)
                .order_by(desc(IncidentModel.timestamp))
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def count_incidents(self) -> int:
        """Return total incident records count."""
        with self.SessionLocal() as session:
            stmt = select(func.count(IncidentModel.id))
            return session.scalar(stmt) or 0

    def count_by_event_type(self) -> Dict[str, int]:
        """Return incident counts grouped by event type."""
        with self.SessionLocal() as session:
            stmt = select(IncidentModel.event_type, func.count(IncidentModel.id)).group_by(
                IncidentModel.event_type
            )
            return dict(session.execute(stmt).all())

    def delete_incident(self, incident_id: int) -> bool:
        """Delete an incident by ID (useful for forensic purge or testing)."""
        with self.SessionLocal() as session:
            stmt = select(IncidentModel).where(IncidentModel.id == incident_id)
            obj = session.scalars(stmt).first()
            if obj:
                session.delete(obj)
                session.commit()
                return True
            return False

    def clear_all(self) -> int:
        """Purge all incident records from database (used for testing)."""
        with self.SessionLocal() as session:
            count = session.query(IncidentModel).delete()
            session.commit()
            return count

    def get_analytics_summary(
        self,
        time_range: str = "all",
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate incidents by time interval, event type, camera, and severity.
        Supports '24h', '7d', and 'all' ranges with deterministic UTC bucketing.
        Guarantees:
          sum(bucket['count'] for bucket in buckets) == total_incidents
          critical + warning == total_incidents
        """
        if now_ts is None:
            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()
        else:
            now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)

        with self.SessionLocal() as session:
            if time_range == "24h":
                cur_hour = now_dt.replace(minute=0, second=0, microsecond=0)
                start_dt = cur_hour - timedelta(hours=23)
                start_ts = start_dt.timestamp()
                buckets = []
                for i in range(24):
                    b_dt = start_dt + timedelta(hours=i)
                    buckets.append({
                        "time_bucket": b_dt.strftime("%H:00"),
                        "iso_timestamp": b_dt.strftime("%Y-%m-%dT%H:00:00Z"),
                        "timestamp": b_dt.timestamp(),
                        "count": 0,
                        "intrusions": 0,
                        "tripwires": 0,
                    })

                stmt = (
                    select(IncidentModel)
                    .where(IncidentModel.timestamp >= start_ts)
                    .where(IncidentModel.timestamp <= now_ts)
                    .order_by(IncidentModel.timestamp.asc())
                )
                records = list(session.scalars(stmt).all())

                for r in records:
                    idx = int((r.timestamp - start_ts) // 3600)
                    if idx < 0:
                        continue
                    if idx >= len(buckets):
                        idx = len(buckets) - 1
                    buckets[idx]["count"] += 1
                    if r.event_type == "ZONE_INTRUSION":
                        buckets[idx]["intrusions"] += 1
                    elif r.event_type == "TRIPWIRE_CROSSING":
                        buckets[idx]["tripwires"] += 1

            elif time_range == "7d":
                cur_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                start_dt = cur_day - timedelta(days=6)
                start_ts = start_dt.timestamp()
                buckets = []
                for i in range(7):
                    b_dt = start_dt + timedelta(days=i)
                    buckets.append({
                        "time_bucket": b_dt.strftime("%Y-%m-%d"),
                        "iso_timestamp": b_dt.strftime("%Y-%m-%dT00:00:00Z"),
                        "timestamp": b_dt.timestamp(),
                        "count": 0,
                        "intrusions": 0,
                        "tripwires": 0,
                    })

                stmt = (
                    select(IncidentModel)
                    .where(IncidentModel.timestamp >= start_ts)
                    .where(IncidentModel.timestamp <= now_ts)
                    .order_by(IncidentModel.timestamp.asc())
                )
                records = list(session.scalars(stmt).all())

                for r in records:
                    idx = int((r.timestamp - start_ts) // 86400)
                    if idx < 0:
                        continue
                    if idx >= len(buckets):
                        idx = len(buckets) - 1
                    buckets[idx]["count"] += 1
                    if r.event_type == "ZONE_INTRUSION":
                        buckets[idx]["intrusions"] += 1
                    elif r.event_type == "TRIPWIRE_CROSSING":
                        buckets[idx]["tripwires"] += 1

            else:  # "all"
                min_ts = session.scalar(select(func.min(IncidentModel.timestamp)))
                cur_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)

                if min_ts is None:
                    start_dt = cur_day - timedelta(days=6)
                    start_ts = start_dt.timestamp()
                    buckets = []
                    for i in range(7):
                        b_dt = start_dt + timedelta(days=i)
                        buckets.append({
                            "time_bucket": b_dt.strftime("%Y-%m-%d"),
                            "iso_timestamp": b_dt.strftime("%Y-%m-%dT00:00:00Z"),
                            "timestamp": b_dt.timestamp(),
                            "count": 0,
                            "intrusions": 0,
                            "tripwires": 0,
                        })
                    records = []
                else:
                    min_dt = datetime.fromtimestamp(min_ts, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    if min_dt > cur_day:
                        min_dt = cur_day
                    span_days = (cur_day - min_dt).days + 1
                    num_buckets = max(span_days, 7)
                    start_dt = cur_day - timedelta(days=num_buckets - 1)
                    start_ts = start_dt.timestamp()

                    buckets = []
                    for i in range(num_buckets):
                        b_dt = start_dt + timedelta(days=i)
                        buckets.append({
                            "time_bucket": b_dt.strftime("%Y-%m-%d"),
                            "iso_timestamp": b_dt.strftime("%Y-%m-%dT00:00:00Z"),
                            "timestamp": b_dt.timestamp(),
                            "count": 0,
                            "intrusions": 0,
                            "tripwires": 0,
                        })

                    stmt = (
                        select(IncidentModel)
                        .where(IncidentModel.timestamp <= now_ts)
                        .order_by(IncidentModel.timestamp.asc())
                    )
                    records = list(session.scalars(stmt).all())

                    for r in records:
                        idx = int((r.timestamp - start_ts) // 86400)
                        if idx < 0:
                            idx = 0
                        if idx >= len(buckets):
                            idx = len(buckets) - 1
                        buckets[idx]["count"] += 1
                        if r.event_type == "ZONE_INTRUSION":
                            buckets[idx]["intrusions"] += 1
                        elif r.event_type == "TRIPWIRE_CROSSING":
                            buckets[idx]["tripwires"] += 1

            total_incidents = len(records)
            incidents_by_type = {"ZONE_INTRUSION": 0, "TRIPWIRE_CROSSING": 0}
            incidents_by_camera: Dict[str, int] = {}
            incidents_by_severity = {"critical": 0, "warning": 0}

            for r in records:
                incidents_by_type[r.event_type] = incidents_by_type.get(r.event_type, 0) + 1
                incidents_by_camera[r.camera_id] = incidents_by_camera.get(r.camera_id, 0) + 1

                if r.event_type == "ZONE_INTRUSION":
                    incidents_by_severity["critical"] += 1
                else:
                    incidents_by_severity["warning"] += 1

            return {
                "time_range": time_range,
                "total_incidents": total_incidents,
                "incidents_over_time": buckets,
                "incidents_by_type": incidents_by_type,
                "incidents_by_camera": incidents_by_camera,
                "incidents_by_severity": incidents_by_severity,
                "camera_status_distribution": {},
                "total_cameras": 0,
                "online_cameras": 0,
            }

