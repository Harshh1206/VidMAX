from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import JobStatus, utcnow
from app.services.downloads import JobService
from app.services.files import FileService


class CleanupService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        job_service: JobService,
        file_service: FileService,
    ) -> None:
        self.session_factory = session_factory
        self.job_service = job_service
        self.file_service = file_service

    def expire_jobs(self, now: datetime | None = None) -> int:
        moment = now or utcnow()
        with self.session_factory() as session:
            jobs = self.job_service.list_expired(session, moment)
            for job in jobs:
                self.file_service.delete_job_files(job.id)
                self.job_service.update(session, job, status=JobStatus.EXPIRED.value)
            return len(jobs)

    def expire_job_if_needed(self, job_id: str) -> bool:
        with self.session_factory() as session:
            job = self.job_service.get(session, job_id)
            if job.expires_at is None or job.expires_at > utcnow():
                return False
            if job.status == JobStatus.EXPIRED.value:
                return True
            self.file_service.delete_job_files(job.id)
            self.job_service.update(session, job, status=JobStatus.EXPIRED.value)
            return True
