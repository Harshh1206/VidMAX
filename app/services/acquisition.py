from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import APIError, DownloadNotAuthorizedError, InvalidFormatError, redact_media_paths
from app.core.ids import new_job_id
from app.core.urls import URLGuard
from app.db.models import DownloadJob, JobStatus
from app.providers.acquisition import StreamAcquisitionAdapter
from app.providers.base import CapabilityStatus, DownloadAuthorization, Platform, PlatformProvider
from app.services.downloads import JobService
from app.services.files import FileService
from app.services.inspection import InspectionService
from app.services.processing import LocalProcessingService


@dataclass(frozen=True)
class AuthorizedAcquisitionRequest:
    platform: Platform
    source_url: str
    authorization: DownloadAuthorization
    quality: str | None = None
    format_id: str | None = None


class AuthorizedDownloadService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        job_service: JobService,
        file_service: FileService,
        processing_service: LocalProcessingService,
        inspection_service: InspectionService,
        guard: URLGuard,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.job_service = job_service
        self.file_service = file_service
        self.processing_service = processing_service
        self.inspection_service = inspection_service
        self.guard = guard

    async def create_job(
        self,
        request: AuthorizedAcquisitionRequest,
        adapter: StreamAcquisitionAdapter,
    ) -> DownloadJob:
        await self._authorize(request, adapter)
        if request.format_id is not None:
            formats = await adapter.list_formats(request.source_url)
            if not any(item.identifier == request.format_id for item in formats):
                raise InvalidFormatError()

        job_id = new_job_id()
        manifest = {
            "operation": "merge_av",
            "target_format": "mp4",
            "source_platform": request.platform.value,
            "source_url": request.source_url,
            "format_id": request.format_id,
            "quality": request.quality,
            "expect_audio": True,
            "inputs": [],
            "roles": [],
        }
        with self.session_factory() as session:
            job = self.job_service.create(
                session,
                platform=request.platform.value,
                source_url=request.source_url,
                job_id=job_id,
            )
        self.file_service.write_manifest(job_id, manifest)
        return job

    async def process_job(self, job_id: str, adapter: StreamAcquisitionAdapter) -> None:
        try:
            manifest = self.file_service.read_manifest(job_id)
            source_url = str(manifest["source_url"])
            provider = self.inspection_service.registry.resolve(source_url)
            self.guard.validate_candidate(source_url, provider.allowed_hosts)
            with self.session_factory() as session:
                job = self.job_service.get(session, job_id)
            if job.status in (JobStatus.CANCELLED.value, JobStatus.EXPIRED.value):
                return

            format_id = manifest.get("format_id")
            quality = manifest.get("quality")
            acquired = await adapter.acquire(
                source_url,
                self.guard,
                provider.allowed_hosts,
                quality if isinstance(quality, str) else None,
                lambda role, suffix: self.file_service.new_temp_path(job_id, f"{role}-{suffix}"),
                format_id=format_id if isinstance(format_id, str) else None,
            )
            manifest["inputs"] = [
                {"path": self.file_service.relative_path(path), "role": role}
                for path, role in zip(acquired.inputs, acquired.roles, strict=True)
            ]
            manifest["roles"] = list(acquired.roles)
            self.file_service.write_manifest(job_id, manifest)
        except APIError as exc:
            self._fail(job_id, exc.message)
            return
        except Exception:
            self._fail(job_id, "Unexpected acquisition failure")
            return

        await self.processing_service.run_job(job_id)

    async def create_and_process(
        self,
        request: AuthorizedAcquisitionRequest,
        adapter: StreamAcquisitionAdapter,
    ) -> DownloadJob:
        job = await self.create_job(request, adapter)
        await self.process_job(job.id, adapter)
        with self.session_factory() as session:
            return self.job_service.get(session, job.id)

    async def _authorize(
        self,
        request: AuthorizedAcquisitionRequest,
        adapter: StreamAcquisitionAdapter,
    ) -> PlatformProvider:
        decision = await self.inspection_service.authorize(request.source_url, request.authorization)
        if not decision.allowed:
            raise DownloadNotAuthorizedError(decision.reason)
        provider = self.inspection_service.registry.resolve(request.source_url)
        if provider.platform is not request.platform:
            raise DownloadNotAuthorizedError("The URL belongs to a different provider")
        capability = provider.capabilities().authorized_download
        if capability.status is not CapabilityStatus.AVAILABLE:
            raise DownloadNotAuthorizedError(capability.reason)
        if not adapter.enabled:
            raise DownloadNotAuthorizedError("No authorized download adapter is enabled")
        return provider

    def _fail(self, job_id: str, message: str) -> None:
        self.file_service.clean_temp(job_id)
        self.job_service.update_by_id(
            job_id,
            status=JobStatus.FAILED.value,
            error_message=redact_media_paths(message)[: self.settings.error_message_max_chars],
        )
