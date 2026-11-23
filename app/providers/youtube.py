import re
from urllib.parse import parse_qs

from app.core.errors import DownloadNotAuthorizedError, InvalidURLError, MetadataUnavailableError
from app.core.urls import NormalizedURL, URLGuard
from app.processing.streams import StreamCandidate
from app.providers.acquisition import StreamAcquisitionAdapter
from app.providers.base import (
    AuthorizationDecision,
    Capability,
    CapabilityStatus,
    DownloadAuthorization,
    Platform,
    PlatformProvider,
    ProviderCapabilities,
    VideoMetadata,
)
from app.providers.metadata import MetadataInspector

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeProvider(PlatformProvider):
    platform = Platform.YOUTUBE
    allowed_hosts = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})

    def __init__(
        self,
        guard: URLGuard,
        inspector: MetadataInspector,
        capabilities: ProviderCapabilities,
        acquisition: StreamAcquisitionAdapter | None = None,
    ):
        super().__init__(guard, capabilities)
        self.inspector = inspector
        self.acquisition = acquisition

    def validate_url(self, url: str) -> NormalizedURL:
        normalized = self.guard.validate_candidate(url, self.allowed_hosts)
        resource_id = self._extract_video_id(normalized)
        canonical = f"https://www.youtube.com/watch?v={resource_id}"
        return self.guard.with_resource_id(
            self.guard.validate_candidate(canonical, self.allowed_hosts),
            resource_id,
        )

    async def inspect_metadata(self, url: str) -> VideoMetadata:
        capability = self.capabilities().metadata_inspection
        if capability.status not in (
            CapabilityStatus.AVAILABLE,
            CapabilityStatus.CONFIGURED_UNVERIFIED,
        ):
            raise MetadataUnavailableError(capability.reason, details={"platform": self.platform.value})
        normalized = self.validate_url(url)
        payload = await self.inspector.fetch(normalized)
        duration = payload.get("duration_seconds")
        return VideoMetadata(
            platform=self.platform,
            canonical_url=normalized.url,
            video_id=normalized.resource_id,
            title=self._optional_text(payload.get("title")),
            author=self._optional_text(payload.get("author_name")),
            thumbnail_url=self._optional_text(payload.get("thumbnail_url")),
            duration_seconds=duration if isinstance(duration, int) and duration >= 0 else None,
            source="documented_oembed",
        )

    async def list_formats(self, url: str) -> list[StreamCandidate]:
        capability = self.capabilities().authorized_download
        if capability.status is not CapabilityStatus.AVAILABLE:
            return []
        normalized = self.validate_url(url)
        if not isinstance(self.acquisition, StreamAcquisitionAdapter) or not self.acquisition.enabled:
            return []
        return await self.acquisition.list_formats(normalized.url)

    async def authorize_download(
        self,
        url: str,
        authorization: DownloadAuthorization,
    ) -> AuthorizationDecision:
        normalized = self.validate_url(url)
        capability = self.capabilities().authorized_download
        if capability.status is not CapabilityStatus.AVAILABLE:
            raise DownloadNotAuthorizedError(
                capability.reason,
                details={"platform": self.platform.value, "url": normalized.url},
            )
        if not authorization.authorized:
            raise DownloadNotAuthorizedError(
                "Confirm that you are allowed to save this video before downloading",
                details={"platform": self.platform.value, "url": normalized.url},
            )
        return AuthorizationDecision(
            allowed=True,
            reason="User confirmed authorization for this download",
            adapter_name=self.acquisition.name if self.acquisition else None,
        )

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
        return None

    @classmethod
    def _extract_video_id(cls, normalized: NormalizedURL) -> str:
        path = normalized.path.rstrip("/")
        query = parse_qs(normalized.query, keep_blank_values=False)
        candidate: str | None = None
        if normalized.host == "youtu.be":
            parts = [part for part in path.split("/") if part]
            if len(parts) == 1:
                candidate = parts[0]
        elif path == "/watch":
            values = query.get("v", [])
            candidate = values[0] if values else None
        else:
            match = re.fullmatch(r"/(?:embed|shorts|live)/([^/]+)", path)
            if match:
                candidate = match.group(1)
        if candidate is None or not _VIDEO_ID_RE.fullmatch(candidate):
            raise InvalidURLError("The YouTube URL does not contain a valid video identifier")
        return candidate


def youtube_capabilities(*, metadata_enabled: bool, acquisition_enabled: bool = False) -> ProviderCapabilities:
    metadata = (
        Capability(
            status=CapabilityStatus.CONFIGURED_UNVERIFIED,
            reason="Documented oEmbed client is configured but has not been verified against the live service",
        )
        if metadata_enabled
        else Capability(
            status=CapabilityStatus.NOT_CONFIGURED,
            reason="Metadata inspection is disabled by configuration",
        )
    )
    return ProviderCapabilities(
        url_validation=Capability(status=CapabilityStatus.AVAILABLE, reason="Exact hostname allowlist"),
        metadata_inspection=metadata,
        authorized_download=(
            Capability(
                status=CapabilityStatus.AVAILABLE,
                reason="Pytubefix adapter is enabled; each download requires user confirmation",
            )
            if acquisition_enabled
            else Capability(
                status=CapabilityStatus.NOT_IMPLEMENTED,
                reason="No authorized YouTube download adapter has been configured or verified",
            )
        ),
    )
