from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from app.core.errors import DownloadNotAuthorizedError
from app.core.urls import NormalizedURL, URLGuard


class Platform(StrEnum):
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    LOCAL = "local"


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class Capability:
    status: CapabilityStatus
    reason: str


@dataclass(frozen=True)
class ProviderCapabilities:
    url_validation: Capability
    metadata_inspection: Capability
    authorized_download: Capability

    @property
    def fully_functional(self) -> bool:
        return all(
            capability.status is CapabilityStatus.AVAILABLE
            for capability in (
                self.url_validation,
                self.metadata_inspection,
                self.authorized_download,
            )
        )


@dataclass(frozen=True)
class VideoMetadata:
    platform: Platform
    canonical_url: str
    video_id: str | None
    title: str | None
    author: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    source: str


@dataclass(frozen=True)
class DownloadAuthorization:
    authorized: bool = False
    basis: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    adapter_name: str | None = None


class PlatformProvider(ABC):
    platform: ClassVar[Platform]
    allowed_hosts: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, guard: URLGuard, capabilities: ProviderCapabilities) -> None:
        self.guard = guard
        self._capabilities = capabilities

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @abstractmethod
    def validate_url(self, url: str) -> NormalizedURL:
        raise NotImplementedError

    def identify(self, url: str) -> Platform | None:
        try:
            self.validate_url(url)
            return self.platform
        except Exception:
            return None

    @abstractmethod
    async def inspect_metadata(self, url: str) -> VideoMetadata:
        raise NotImplementedError

    async def list_formats(self, url: str) -> list[object]:
        return []

    async def authorize_download(
        self,
        url: str,
        authorization: DownloadAuthorization,
    ) -> AuthorizationDecision:
        normalized = self.validate_url(url)
        capability = self._capabilities.authorized_download
        if capability.status is not CapabilityStatus.AVAILABLE:
            raise DownloadNotAuthorizedError(
                capability.reason,
                details={"platform": self.platform.value, "url": normalized.url},
            )
        raise DownloadNotAuthorizedError(
            "No authorized download adapter has been registered",
            details={"platform": self.platform.value, "url": normalized.url},
        )
