from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.api.v1.uploads import router as uploads_router
from app.config import Settings, load_settings
from app.core.errors import APIError
from app.core.logging import configure_logging
from app.db.models import utcnow
from app.db.session import create_db_engine, create_session_factory, init_db
from app.processing.base import ProcessingAdapter
from app.processing.ffmpeg import LocalFFmpegAdapter
from app.processing.media import FFprobeValidator
from app.processing.service import MediaInspector, MediaProcessingService
from app.providers.acquisition import PytubefixAcquisitionAdapter
from app.providers.base import PlatformProvider
from app.providers.facebook import FacebookProvider, facebook_capabilities
from app.providers.metadata import HttpJsonInspector, NoopInspector
from app.providers.registry import ProviderRegistry
from app.providers.youtube import YouTubeProvider, youtube_capabilities
from app.schemas.common import ErrorResponse
from app.services.acquisition import AuthorizedDownloadService
from app.services.cleanup import CleanupService
from app.services.downloads import JobService
from app.services.files import FileService
from app.services.inspection import InspectionService
from app.services.processing import LocalProcessingService
from app.services.uploads import UploadService


def build_default_registry(settings: Settings, client: httpx.AsyncClient) -> ProviderRegistry:
    guard = ProviderRegistry.default_guard()
    common = {
        "timeout_seconds": settings.http_timeout_seconds,
        "max_bytes": settings.metadata_max_bytes,
    }
    youtube_inspector = (
        HttpJsonInspector(client, settings.youtube_oembed_url, **common)
        if settings.enable_metadata_inspection
        else NoopInspector("Metadata inspection is disabled by configuration")
    )
    token = settings.facebook_access_token.get_secret_value() if settings.facebook_access_token else None
    facebook_inspector = (
        HttpJsonInspector(
            client,
            settings.facebook_oembed_url,
            extra_params={"access_token": token},
            **common,
        )
        if settings.enable_metadata_inspection and token
        else NoopInspector("Facebook metadata inspection is not configured")
    )
    acquisition = PytubefixAcquisitionAdapter(
        enabled=settings.enable_youtube_pytubefix_download,
        download_timeout_seconds=settings.youtube_download_timeout_seconds,
        download_max_retries=settings.youtube_download_max_retries,
    )
    providers: list[PlatformProvider] = [
        YouTubeProvider(
            guard,
            youtube_inspector,
            youtube_capabilities(
                metadata_enabled=settings.enable_metadata_inspection,
                acquisition_enabled=settings.enable_youtube_pytubefix_download,
            ),
            acquisition=acquisition,
        ),
        FacebookProvider(
            guard,
            facebook_inspector,
            facebook_capabilities(
                metadata_enabled=settings.enable_metadata_inspection,
                oauth_configured=bool(token),
            ),
        ),
    ]
    return ProviderRegistry(guard, providers)


def create_app(
    settings: Settings | None = None,
    *,
    registry: ProviderRegistry | None = None,
    processor: ProcessingAdapter | None = None,
    media_inspector: MediaInspector | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings)
    engine = create_db_engine(resolved_settings.database_url, resolved_settings.storage_dir)
    session_factory = create_session_factory(engine)
    http_client = httpx.AsyncClient(follow_redirects=False)
    file_service = FileService(resolved_settings.storage_dir, resolved_settings.max_upload_bytes)
    job_service = JobService(session_factory, resolved_settings.job_ttl_hours)
    active_registry = registry or build_default_registry(resolved_settings, http_client)
    inspection_service = InspectionService(active_registry)
    active_processor = processor or LocalFFmpegAdapter(ffmpeg_path=resolved_settings.ffmpeg_path or "ffmpeg")
    active_inspector = media_inspector
    if active_inspector is None and processor is None:
        active_inspector = FFprobeValidator(
            resolved_settings.ffprobe_path or "ffprobe",
            timeout_seconds=resolved_settings.ffprobe_timeout_seconds,
            min_bytes=resolved_settings.media_min_bytes,
            max_bytes=resolved_settings.max_output_bytes,
            duration_tolerance_seconds=resolved_settings.duration_tolerance_seconds,
        )
    media_service = MediaProcessingService(active_processor, active_inspector)
    processing_service = LocalProcessingService(
        resolved_settings,
        session_factory,
        job_service,
        file_service,
        media_service,
    )
    cleanup_service = CleanupService(session_factory, job_service, file_service)
    acquisition_service = AuthorizedDownloadService(
        resolved_settings,
        session_factory,
        job_service,
        file_service,
        processing_service,
        inspection_service,
        active_registry.guard,
    )
    upload_service = UploadService(
        resolved_settings,
        session_factory,
        job_service,
        file_service,
        processing_service,
        frozenset(active_processor.allowed_formats)
        if hasattr(active_processor, "allowed_formats")
        else frozenset({"mp4", "mkv", "webm", "mp3", "m4a", "wav"}),
        int(getattr(active_processor, "max_inputs", 8)),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        file_service.init_dirs()
        init_db(engine)
        cleanup_service.expire_jobs(utcnow())
        yield
        await http_client.aclose()
        engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.version,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.http_client = http_client
    app.state.session_factory = session_factory
    app.state.file_service = file_service
    app.state.job_service = job_service
    app.state.registry = active_registry
    app.state.inspection_service = inspection_service
    app.state.processor = active_processor
    app.state.media_service = media_service
    app.state.media_inspector = active_inspector
    app.state.processing_service = processing_service
    app.state.cleanup_service = cleanup_service
    app.state.acquisition_service = acquisition_service
    app.state.upload_service = upload_service

    app.include_router(v1_router)
    if resolved_settings.enable_local_uploads:
        app.include_router(uploads_router, prefix="/api/v1")

    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    return app


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, APIError)
    payload = ErrorResponse(
        error={"code": exc.code, "message": exc.message, "details": exc.details}
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    payload = ErrorResponse(
        error={
            "code": "VALIDATION_ERROR",
            "message": "The request payload is invalid",
            "details": {"errors": exc.errors()},
        }
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


app = create_app()
