"""
IBVAP Event Persistence Layer: SQLite Database with SQLAlchemy
Provides structured schema and optimized indexed queries for border surveillance
security incidents, audit trails, and forensic reviews.
"""

from datetime import datetime, timezone
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
    """

    def __init__(self, db_path_or_url: Union[str, Path] = "data/events.db"):
        str_path = str(db_path_or_url)
        if str_path.startswith("sqlite://"):
            self.db_url = str_path
        else:
            p = Path(str_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_url = f"sqlite:///{p.resolve()}"

        logger.info(f"Connecting to Incident Database: {self.db_url}")
        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False},
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
