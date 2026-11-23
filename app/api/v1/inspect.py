from fastapi import APIRouter, Depends

from app.api.deps import get_inspection_service
from app.providers.base import CapabilityStatus
from app.schemas.inspect import InspectRequest, InspectResponse, VideoFormatResponse
from app.services.inspection import InspectionService

router = APIRouter(tags=["inspect"])


@router.post("/inspect", response_model=InspectResponse)
async def inspect(
    payload: InspectRequest,
    service: InspectionService = Depends(get_inspection_service),
) -> InspectResponse:
    result = await service.inspect(payload.url)
    capabilities = result.provider.capabilities()
    formats = [VideoFormatResponse.from_candidate(candidate) for candidate in result.formats]
    downloadable = bool(formats) and capabilities.authorized_download.status is CapabilityStatus.AVAILABLE
    return InspectResponse(
        platform=result.metadata.platform,
        canonical_url=result.metadata.canonical_url,
        video_id=result.metadata.video_id,
        title=result.metadata.title,
        author=result.metadata.author,
        thumbnail_url=result.metadata.thumbnail_url,
        duration_seconds=result.metadata.duration_seconds,
        metadata_source=result.metadata.source,
        metadata_available=True,
        downloadable=downloadable,
        download_capability_status=capabilities.authorized_download.status,
        download_capability_reason=capabilities.authorized_download.reason,
        formats=formats,
        recommended_format_id=formats[0].id if formats else None,
    )
