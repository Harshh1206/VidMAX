from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def utcnow() -> datetime:
    return datetime.now(UTC)


class DownloadJob(Base):
    __tablename__ = "download_jobs"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_download_jobs_progress"),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed', 'cancelled', 'expired')",
            name="ck_download_jobs_status",
        ),
        Index("ix_download_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default=JobStatus.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
