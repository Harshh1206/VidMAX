import re
from urllib.parse import parse_qs

from app.core.errors import InvalidURLError, MetadataUnavailableError
from app.core.urls import NormalizedURL, URLGuard
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

_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class FacebookProvider(PlatformProvider):
    platform = Platform.FACEBOOK
    allowed_hosts = frozenset({"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"})

    def __init__(self, guard: URLGuard, inspector: MetadataInspector, capabilities: ProviderCapabilities):
        super().__init__(guard, capabilities)
        self.inspector = inspector

    def validate_url(self, url: str) -> NormalizedURL:
        normalized = self.guard.validate_candidate(url, self.allowed_hosts)
        resource_id = self._extract_video_id(normalized)
        canonical = f"https://www.facebook.com/watch?v={resource_id}"
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

    async def authorize_download(
        self,
        url: str,
        authorization: DownloadAuthorization,
    ) -> AuthorizationDecision:
        return await super().authorize_download(url, authorization)

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
        if normalized.host == "fb.watch":
            parts = [part for part in path.split("/") if part]
            if len(parts) == 1:
                candidate = parts[0]
        elif path == "/watch":
            values = query.get("v", [])
            candidate = values[0] if values else None
        else:
            match = re.fullmatch(r"/(?:videos|reel|watch|share/v)/([^/]+)", path)
            if match:
                candidate = match.group(1)
        if candidate is None or not _RESOURCE_ID_RE.fullmatch(candidate):
            raise InvalidURLError("The Facebook URL does not contain a valid video identifier")
        return candidate


def facebook_capabilities(
    *,
    metadata_enabled: bool,
    oauth_configured: bool,
) -> ProviderCapabilities:
    if metadata_enabled and oauth_configured:
        metadata = Capability(
            status=CapabilityStatus.CONFIGURED_UNVERIFIED,
            reason="Documented Graph oEmbed client is configured but has not been verified against the live service",
        )
    elif metadata_enabled:
        metadata = Capability(
            status=CapabilityStatus.NOT_CONFIGURED,
            reason="Facebook metadata inspection requires an access token",
        )
    else:
        metadata = Capability(
            status=CapabilityStatus.NOT_CONFIGURED,
            reason="Metadata inspection is disabled by configuration",
        )
    return ProviderCapabilities(
        url_validation=Capability(status=CapabilityStatus.AVAILABLE, reason="Exact hostname allowlist"),
        metadata_inspection=metadata,
        authorized_download=Capability(
            status=CapabilityStatus.NOT_IMPLEMENTED,
            reason="No authorized Facebook download adapter has been configured or verified",
        ),
    )
