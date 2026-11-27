import uuid
import enum
from datetime import datetime
from sqlalchemy import String, DateTime, Enum, JSON, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class EntityType(str, enum.Enum):
    DOMAIN = "DOMAIN"
    SUBDOMAIN = "SUBDOMAIN"
    IP_ADDRESS = "IP_ADDRESS"
    DNS_RECORD = "DNS_RECORD"
    CERTIFICATE = "CERTIFICATE"
    TECHNOLOGY = "TECHNOLOGY"
    ASN = "ASN"

class ModuleRun(Base):
    __tablename__ = "module_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_jobs.id"), nullable=False)
    module_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Numeric, nullable=True)
    raw_output_location: Mapped[str] = mapped_column(Text, nullable=True)
    warnings: Mapped[dict] = mapped_column(JSON, nullable=True)
    errors: Mapped[dict] = mapped_column(JSON, nullable=True)

class RawObservation(Base):
    __tablename__ = "raw_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_jobs.id"), nullable=False)
    module_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("module_runs.id"), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    raw_record: Mapped[dict] = mapped_column(JSON, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_jobs.id"), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(255), nullable=False)
    display_value: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_jobs.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    module_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("module_runs.id"), nullable=False)
    source_module: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_value: Mapped[str] = mapped_column(Text, nullable=False)
    raw_record: Mapped[dict] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)