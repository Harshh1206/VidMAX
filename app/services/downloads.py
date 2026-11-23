from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import InvalidJobIDError, JobNotFoundError
from app.core.ids import is_valid_job_id, new_job_id
from app.db.models import DownloadJob, JobStatus, utcnow


class JobService:
    def __init__(self, session_factory: sessionmaker[Session], job_ttl_hours: int) -> None:
        self.session_factory = session_factory
        self.job_ttl_hours = job_ttl_hours

    def create(
        self,
        session: Session,
        *,
        platform: str,
        source_url: str,
        job_id: str | None = None,
    ) -> DownloadJob:
        identifier = job_id or new_job_id()
        if not is_valid_job_id(identifier):
            raise InvalidJobIDError()
        job = DownloadJob(
            id=identifier,
            platform=platform,
            source_url=source_url,
            status=JobStatus.QUEUED.value,
            progress=0,
            expires_at=utcnow() + timedelta(hours=self.job_ttl_hours),
        )
        session.add(job)
        session.commit()
        return job

    def get(self, session: Session, job_id: str) -> DownloadJob:
        if not is_valid_job_id(job_id):
            raise InvalidJobIDError()
        job = session.get(DownloadJob, job_id)
        if job is None:
            raise JobNotFoundError()
        return job

    def find(self, job_id: str) -> DownloadJob | None:
        if not is_valid_job_id(job_id):
            return None
        with self.session_factory() as session:
            return session.get(DownloadJob, job_id)

    def update(self, session: Session, job: DownloadJob, **fields: Any) -> DownloadJob:
        allowed = {
            "status",
            "progress",
            "file_name",
            "file_path",
            "error_message",
            "expires_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported job fields: {', '.join(sorted(unknown))}")
        if "progress" in fields:
            progress = fields["progress"]
            if not isinstance(progress, int) or not 0 <= progress <= 100:
                raise ValueError("Progress must be between 0 and 100")
        for key, value in fields.items():
            setattr(job, key, value)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def update_by_id(self, job_id: str, **fields: Any) -> DownloadJob:
        with self.session_factory() as session:
            job = self.get(session, job_id)
            return self.update(session, job, **fields)

    def list_expired(self, session: Session, now: datetime) -> list[DownloadJob]:
        statement = select(DownloadJob).where(
            DownloadJob.expires_at.is_not(None),
            DownloadJob.expires_at <= now,
            DownloadJob.status != JobStatus.EXPIRED.value,
        )
        return list(session.scalars(statement).all())

    def delete(self, session: Session, job_id: str) -> None:
        job = self.get(session, job_id)
        session.delete(job)
        session.commit()
