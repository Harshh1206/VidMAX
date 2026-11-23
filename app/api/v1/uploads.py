from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.api.deps import get_upload_service
from app.processing.base import Operation
from app.schemas.downloads import JobResponse
from app.services.uploads import UploadService

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=JobResponse, status_code=202)
async def create_upload(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    operation: Operation = Form(Operation.CONVERT),
    target_format: str = Form("mp4"),
    attestation: bool = Form(False),
    stream_roles: str | None = Form(None),
    quality: str | None = Form(None),
    service: UploadService = Depends(get_upload_service),
) -> JobResponse:
    job = await service.create_job(
        files=files,
        operation=operation,
        target_format=target_format,
        attestation=attestation,
        background_tasks=background_tasks,
        stream_roles=stream_roles,
        quality=quality,
    )
    return JobResponse.from_job(job)
