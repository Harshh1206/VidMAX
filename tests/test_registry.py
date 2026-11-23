import pytest

from app.core.errors import UnsupportedPlatformError
from app.core.urls import URLGuard
from app.providers.base import Platform
from app.providers.facebook import FacebookProvider, facebook_capabilities
from app.providers.registry import ProviderRegistry
from app.providers.youtube import YouTubeProvider, youtube_capabilities
from tests.conftest import FakeInspector

GUARD = URLGuard()


def youtube() -> YouTubeProvider:
    return YouTubeProvider(GUARD, FakeInspector(), youtube_capabilities(metadata_enabled=True))


def facebook() -> FacebookProvider:
    return FacebookProvider(
        GUARD,
        FakeInspector(),
        facebook_capabilities(metadata_enabled=True, oauth_configured=True),
    )


def test_registry_resolves_each_provider() -> None:
    registry = ProviderRegistry(GUARD, [youtube(), facebook()])
    assert registry.resolve("https://youtu.be/dQw4w9WgXcQ").platform is Platform.YOUTUBE
    assert registry.resolve("https://fb.watch/abcDEF123").platform is Platform.FACEBOOK
    assert registry.get(Platform.YOUTUBE).platform is Platform.YOUTUBE
    assert len(registry.all()) == 2


def test_registry_rejects_unknown_host() -> None:
    registry = ProviderRegistry(GUARD, [youtube()])
    with pytest.raises(UnsupportedPlatformError):
        registry.resolve("https://www.facebook.com/watch?v=123456789")


def test_registry_rejects_duplicate_platform() -> None:
    registry = ProviderRegistry(GUARD, [youtube()])
    with pytest.raises(ValueError):
        registry.register(youtube())


def test_registry_rejects_overlapping_hosts() -> None:
    class OverlappingProvider(FacebookProvider):
        allowed_hosts = frozenset({"youtube.com"})

    registry = ProviderRegistry(GUARD, [youtube()])
    overlapping = OverlappingProvider(
        GUARD,
        FakeInspector(),
        facebook_capabilities(metadata_enabled=True, oauth_configured=True),
    )
    with pytest.raises(ValueError):
        registry.register(overlapping)


def test_registry_readiness_reports_all_platforms() -> None:
    registry = ProviderRegistry(GUARD, [youtube(), facebook()])
    readiness = registry.readiness()
    assert set(readiness) == {Platform.YOUTUBE, Platform.FACEBOOK}
    assert all(not capabilities.fully_functional for capabilities in readiness.values())
