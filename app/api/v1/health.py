from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_registry, get_session, get_settings
from app.config import Settings
from app.providers.registry import ProviderRegistry
from app.schemas.health import CapabilityResponse, HealthResponse, ProviderReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    registry: ProviderRegistry = Depends(get_registry),
) -> HealthResponse:
    database = "ok" if session.execute(text("SELECT 1")).scalar_one() == 1 else "error"
    providers = []
    for provider in registry.all():
        capabilities = provider.capabilities()
        providers.append(
            ProviderReadinessResponse(
                platform=provider.platform,
                url_validation=CapabilityResponse(
                    status=capabilities.url_validation.status,
                    reason=capabilities.url_validation.reason,
                ),
                metadata_inspection=CapabilityResponse(
                    status=capabilities.metadata_inspection.status,
                    reason=capabilities.metadata_inspection.reason,
                ),
                authorized_download=CapabilityResponse(
                    status=capabilities.authorized_download.status,
                    reason=capabilities.authorized_download.reason,
                ),
                fully_functional=capabilities.fully_functional,
            )
        )
    return HealthResponse(
        status="ok" if database == "ok" else "error",
        version=settings.version,
        environment=settings.environment,
        database=database,
        providers=providers,
    )
