from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.providers.registry import ProviderRegistry
from app.services.acquisition import AuthorizedDownloadService
from app.services.cleanup import CleanupService
from app.services.downloads import JobService
from app.services.files import FileService
from app.services.inspection import InspectionService
from app.services.processing import LocalProcessingService
from app.services.uploads import UploadService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_registry(request: Request) -> ProviderRegistry:
    return request.app.state.registry


def get_job_service(request: Request) -> JobService:
    return request.app.state.job_service


def get_file_service(request: Request) -> FileService:
    return request.app.state.file_service


def get_inspection_service(request: Request) -> InspectionService:
    return request.app.state.inspection_service


def get_processing_service(request: Request) -> LocalProcessingService:
    return request.app.state.processing_service


def get_acquisition_service(request: Request) -> AuthorizedDownloadService:
    return request.app.state.acquisition_service


def get_upload_service(request: Request) -> UploadService:
    return request.app.state.upload_service


def get_cleanup_service(request: Request) -> CleanupService:
    return request.app.state.cleanup_service
