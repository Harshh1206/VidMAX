from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import APIError, JobNotFoundError, ProcessingError
from app.core.logging import get_logger
from app.db.models import JobStatus
from app.processing.base import Operation, ProcessingRequest
from app.processing.service import MediaProcessingService
from app.services.downloads import JobService
from app.services.files import FileService

_LOGGER = get_logger(__name__)


class LocalProcessingService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        job_service: JobService,
        file_service: FileService,
        media_service: MediaProcessingService,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.job_service = job_service
        self.file_service = file_service
        self.media_service = media_service

    async def run_job(self, job_id: str) -> None:
        try:
            with self.session_factory() as session:
                job = self.job_service.get(session, job_id)
                if job.status in (JobStatus.CANCELLED.value, JobStatus.EXPIRED.value):
                    return
                self.job_service.update(
                    session,
                    job,
                    status=JobStatus.PROCESSING.value,
                    progress=10,
                    error_message=None,
                )
        except JobNotFoundError:
            return

        output_path: Path | None = None
        try:
            manifest = self.file_service.read_manifest(job_id)
            request = self._build_request(job_id, manifest)
            output_path = request.output_dir / f"{job_id}.{request.target_format}"
            self._set_progress(job_id, 30)
            result = await self.media_service.process(request)
            self._set_progress(job_id, 90)
        except APIError as exc:
            _LOGGER.warning(
                "Processing failed",
                extra={"job_id": job_id, "error_code": getattr(exc, "code", "UNKNOWN")},
            )
            self._fail(job_id, exc.message, output_path)
            return
        except Exception as exc:
            _LOGGER.exception(
                "Unexpected processing failure",
                extra={"job_id": job_id, "exception": type(exc).__name__},
            )
            self._fail(job_id, "Unexpected processing failure", output_path)
            return
        finally:
            self._cleanup(job_id)

        with self.session_factory() as session:
            job = self.job_service.get(session, job_id)
            if job.status in (JobStatus.CANCELLED.value, JobStatus.EXPIRED.value):
                return
            self.job_service.update(
                session,
                job,
                status=JobStatus.COMPLETED.value,
                progress=100,
                file_name=result.output_name,
                file_path=self.file_service.relative_path(result.output_path),
                error_message=None,
            )

    def _build_request(self, job_id: str, manifest: dict[str, Any]) -> ProcessingRequest:
        operation = Operation(str(manifest["operation"]))
        inputs = tuple(
            self.file_service.resolve_servable_path(str(entry["path"]))
            for entry in manifest["inputs"]
        )
        roles = tuple(str(role) for role in manifest.get("roles", []))
        if operation is Operation.AV_MERGE:
            if len(inputs) != 2 or len(roles) != 2:
                raise ProcessingError("Separate AV merging requires two inputs with roles")
            if tuple(roles) not in {("video", "audio"), ("audio", "video")}:
                raise ProcessingError("Input roles must be video and audio")
            if roles[0] == "audio":
                inputs = (inputs[1], inputs[0])
        target_format = str(manifest["target_format"])
        return ProcessingRequest(
            job_id=job_id,
            operation=operation,
            inputs=inputs,
            output_dir=self.file_service.output_dir(job_id),
            target_format=target_format,
            timeout_seconds=self.settings.processing_timeout_seconds,
            max_output_bytes=self.settings.max_output_bytes,
            quality=manifest.get("quality") if isinstance(manifest.get("quality"), str) else None,
            expect_audio=bool(manifest.get("expect_audio", True)),
            expect_video=target_format not in {"mp3", "m4a", "wav"},
            max_duration_seconds=manifest.get("max_duration_seconds")
            if isinstance(manifest.get("max_duration_seconds"), int)
            else None,
        )

    def _set_progress(self, job_id: str, progress: int) -> None:
        with self.session_factory() as session:
            try:
                job = self.job_service.get(session, job_id)
            except JobNotFoundError:
                return
            self.job_service.update(session, job, progress=progress)

    def _fail(self, job_id: str, message: str, output_path: Path | None) -> None:
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        truncated = message[: self.settings.error_message_max_chars]
        try:
            self.job_service.update_by_id(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=truncated or ProcessingError.message,
            )
        except APIError:
            return

    def _cleanup(self, job_id: str) -> None:
        try:
            self.file_service.clean_temp(job_id)
        except APIError:
            return
