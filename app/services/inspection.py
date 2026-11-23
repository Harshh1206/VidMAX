from dataclasses import dataclass

from app.core.errors import MetadataUnavailableError
from app.processing.streams import StreamCandidate
from app.providers.base import (
    AuthorizationDecision,
    CapabilityStatus,
    DownloadAuthorization,
    PlatformProvider,
    VideoMetadata,
)
from app.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class InspectionResult:
    provider: PlatformProvider
    metadata: VideoMetadata
    formats: tuple[StreamCandidate, ...] = ()


class InspectionService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    async def inspect(self, url: str) -> InspectionResult:
        provider = self.registry.resolve(url)
        capability = provider.capabilities().metadata_inspection
        if capability.status not in (
            CapabilityStatus.AVAILABLE,
            CapabilityStatus.CONFIGURED_UNVERIFIED,
        ):
            raise MetadataUnavailableError(
                capability.reason,
                details={"platform": provider.platform.value},
            )
        metadata = await provider.inspect_metadata(url)
        formats: tuple[StreamCandidate, ...] = ()
        if provider.capabilities().authorized_download.status is CapabilityStatus.AVAILABLE:
            discovered = await provider.list_formats(metadata.canonical_url)
            formats = tuple(item for item in discovered if isinstance(item, StreamCandidate))
        return InspectionResult(provider=provider, metadata=metadata, formats=formats)

    async def authorize(self, url: str, authorization: DownloadAuthorization) -> AuthorizationDecision:
        provider = self.registry.resolve(url)
        return await provider.authorize_download(url, authorization)
