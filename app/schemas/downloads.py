from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import JobStatus
from app.providers.base import Platform


class DownloadAuthorizationRequest(BaseModel):
    authorized: bool = False
    basis: str | None = Field(default=None, max_length=100)
    reference: str | None = Field(default=None, max_length=200)


class CreateDownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    target_format: str | None = Field(default=None, max_length=16)
    format_id: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    authorization: DownloadAuthorizationRequest = Field(default_factory=DownloadAuthorizationRequest)


class JobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    platform: Platform
    source_url: str
    status: JobStatus
    progress: int
    file_name: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    error_message: str | None
    download_url: str | None = None

    @classmethod
    def from_job(cls, job: object) -> "JobResponse":
        response = cls.model_validate(job, from_attributes=True)
        if response.status is JobStatus.COMPLETED:
            response.download_url = f"/api/v1/downloads/{response.id}/file"
        return response
