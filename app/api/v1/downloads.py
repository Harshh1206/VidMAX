from mimetypes import guess_type

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_acquisition_service,
    get_cleanup_service,
    get_file_service,
    get_inspection_service,
    get_job_service,
    get_session,
)
from app.core.errors import DownloadNotAuthorizedError, JobExpiredError, JobNotReadyError
from app.db.models import JobStatus
from app.providers.acquisition import StreamAcquisitionAdapter
from app.providers.base import DownloadAuthorization
from app.schemas.downloads import CreateDownloadRequest, JobResponse
from app.services.acquisition import AuthorizedAcquisitionRequest, AuthorizedDownloadService
from app.services.cleanup import CleanupService
from app.services.downloads import JobService
from app.services.files import FileService
from app.services.inspection import InspectionService

router = APIRouter(tags=["downloads"])


@router.post("/downloads", response_model=JobResponse, status_code=201)
async def create_download(
    payload: CreateDownloadRequest,
    background_tasks: BackgroundTasks,
    inspection: InspectionService = Depends(get_inspection_service),
    acquisition_service: AuthorizedDownloadService = Depends(get_acquisition_service),
) -> JobResponse:
    provider = inspection.registry.resolve(payload.url)
    adapter = getattr(provider, "acquisition", None)
    if not isinstance(adapter, StreamAcquisitionAdapter):
        raise DownloadNotAuthorizedError("No authorized download adapter is registered for this provider")
    job = await acquisition_service.create_job(
        AuthorizedAcquisitionRequest(
            platform=provider.platform,
            source_url=payload.url,
            authorization=DownloadAuthorization(
                authorized=payload.authorization.authorized,
                basis=payload.authorization.basis,
                reference=payload.authorization.reference,
            ),
            format_id=payload.format_id,
        ),
        adapter,
    )
    background_tasks.add_task(acquisition_service.process_job, job.id, adapter)
    return JobResponse.from_job(job)


@router.get("/downloads/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    session: Session = Depends(get_session),
    job_service: JobService = Depends(get_job_service),
    cleanup: CleanupService = Depends(get_cleanup_service),
) -> JobResponse:
    if cleanup.expire_job_if_needed(job_id):
        raise JobExpiredError()
    job = job_service.get(session, job_id)
    return JobResponse.from_job(job)


@router.get("/downloads/{job_id}/file")
def get_job_file(
    job_id: str,
    session: Session = Depends(get_session),
    job_service: JobService = Depends(get_job_service),
    file_service: FileService = Depends(get_file_service),
    cleanup: CleanupService = Depends(get_cleanup_service),
) -> FileResponse:
    if cleanup.expire_job_if_needed(job_id):
        raise JobExpiredError()
    job = job_service.get(session, job_id)
    if job.status != JobStatus.COMPLETED.value:
        raise JobNotReadyError(f"Job status is {job.status}")
    path = file_service.resolve_servable_path(job.file_path)
    if not path.is_file():
        raise JobNotReadyError("The completed file is missing")
    media_type, _ = guess_type(job.file_name or path.name)
    return FileResponse(
        path,
        filename=job.file_name or path.name,
        media_type=media_type or "application/octet-stream",
    )


@router.delete("/downloads/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    session: Session = Depends(get_session),
    job_service: JobService = Depends(get_job_service),
    file_service: FileService = Depends(get_file_service),
) -> Response:
    job_service.get(session, job_id)
    file_service.delete_job_files(job_id)
    job_service.delete(session, job_id)
    return Response(status_code=204)
