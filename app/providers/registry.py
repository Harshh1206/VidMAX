from collections.abc import Iterable

from app.core.errors import UnsupportedPlatformError
from app.core.urls import URLGuard
from app.providers.base import Platform, PlatformProvider, ProviderCapabilities


class ProviderRegistry:
    @staticmethod
    def default_guard() -> URLGuard:
        return URLGuard()

    def __init__(self, guard: URLGuard, providers: Iterable[PlatformProvider] = ()) -> None:
        self.guard = guard
        self._providers: dict[Platform, PlatformProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: PlatformProvider) -> None:
        if provider.platform in self._providers:
            raise ValueError(f"Duplicate provider registration: {provider.platform.value}")
        for existing in self._providers.values():
            overlap = existing.allowed_hosts & provider.allowed_hosts
            if overlap:
                raise ValueError(f"Host allowlist overlap: {', '.join(sorted(overlap))}")
        self._providers[provider.platform] = provider

    def get(self, platform: Platform) -> PlatformProvider:
        try:
            return self._providers[platform]
        except KeyError as exc:
            raise UnsupportedPlatformError(f"Provider {platform.value} is not registered") from exc

    def resolve(self, url: str) -> PlatformProvider:
        normalized = self.guard.parse(url)
        for provider in self._providers.values():
            if normalized.host in provider.allowed_hosts:
                provider.validate_url(url)
                return provider
        raise UnsupportedPlatformError(f"Host {normalized.host!r} is not registered")

    def all(self) -> tuple[PlatformProvider, ...]:
        return tuple(self._providers.values())

    def readiness(self) -> dict[Platform, ProviderCapabilities]:
        return {platform: provider.capabilities() for platform, provider in self._providers.items()}
