import uuid
import enum
from datetime import datetime
from sqlalchemy import String, DateTime, Enum, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    COLLECTING = "COLLECTING"
    NORMALISING = "NORMALISING"
    CORRELATING = "CORRELATING"
    ANALYSING = "ANALYSING"
    VALIDATING_ANALYSIS = "VALIDATING_ANALYSIS"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ReconJob(Base):
    __tablename__ = "recon_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    selected_modules: Mapped[dict] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Cached AI security briefing markdown for instant subsequent retrievals
    briefing_markdown: Mapped[str] = mapped_column(Text, nullable=True)