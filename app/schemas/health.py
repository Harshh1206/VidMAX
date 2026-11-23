from pydantic import BaseModel

from app.providers.base import CapabilityStatus, Platform


class CapabilityResponse(BaseModel):
    status: CapabilityStatus
    reason: str


class ProviderReadinessResponse(BaseModel):
    platform: Platform
    url_validation: CapabilityResponse
    metadata_inspection: CapabilityResponse
    authorized_download: CapabilityResponse
    fully_functional: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    providers: list[ProviderReadinessResponse]
