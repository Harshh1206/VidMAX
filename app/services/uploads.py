from fastapi import BackgroundTasks, UploadFile
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import InvalidUploadError, LocalUploadsDisabledError, UnsupportedOperationError
from app.core.ids import new_job_id
from app.db.models import DownloadJob
from app.processing.base import Operation
from app.processing.streams import parse_quality
from app.services.downloads import JobService
from app.services.files import FileService
from app.services.processing import LocalProcessingService


class UploadService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        job_service: JobService,
        file_service: FileService,
        processing_service: LocalProcessingService,
        allowed_formats: frozenset[str],
        max_inputs: int,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.job_service = job_service
        self.file_service = file_service
        self.processing_service = processing_service
        self.allowed_formats = allowed_formats
        self.max_inputs = max_inputs

    async def create_job(
        self,
        files: list[UploadFile],
        operation: Operation,
        target_format: str,
        attestation: bool,
        background_tasks: BackgroundTasks,
        stream_roles: str | None = None,
        quality: str | None = None,
    ) -> DownloadJob:
        if not self.settings.enable_local_uploads:
            raise LocalUploadsDisabledError()
        if quality:
            parse_quality(quality)
        if not attestation:
            raise InvalidUploadError("You must confirm that you own or are authorized to process the media")
        if target_format not in self.allowed_formats:
            raise UnsupportedOperationError(f"Unsupported target format: {target_format}")
        if not files or len(files) > self.max_inputs:
            raise InvalidUploadError(f"Between 1 and {self.max_inputs} files are required")
        if operation is Operation.CONVERT and len(files) != 1:
            raise InvalidUploadError("Conversion requires exactly one file")
        if operation is Operation.MERGE and len(files) < 2:
            raise InvalidUploadError("Merging requires at least two files")

        roles: list[str] = []
        if operation is Operation.AV_MERGE:
            if target_format != "mp4":
                raise UnsupportedOperationError("Separate AV merging requires MP4 output")
            if len(files) != 2:
                raise InvalidUploadError("Separate AV merging requires exactly two files")
            roles = [role.strip().lower() for role in (stream_roles or "").split(",") if role.strip()]
            if not roles:
                roles = ["video", "audio"]
            if sorted(roles) != ["audio", "video"]:
                raise InvalidUploadError("Stream roles must be video and audio")

        job_id = new_job_id()
        saved: list[tuple[str, str]] = []
        for upload in files:
            path, display_name = await self.file_service.save_upload(job_id, upload)
            saved.append((self.file_service.relative_path(path), display_name))

        self.file_service.write_manifest(
            job_id,
            {
                "operation": operation.value,
                "target_format": target_format,
                "inputs": [
                    {"path": path, "name": name}
                    for path, name in saved
                ],
                "roles": roles,
                "quality": quality,
                "expect_audio": True,
            },
        )
        with self.session_factory() as session:
            job = self.job_service.create(
                session,
                platform="local",
                source_url="local://upload",
                job_id=job_id,
            )
        background_tasks.add_task(self.processing_service.run_job, job_id)
        return job

    def get_job(self, job_id: str) -> DownloadJob:
        with self.session_factory() as session:
            return self.job_service.get(session, job_id)
