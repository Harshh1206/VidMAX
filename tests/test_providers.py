import pytest

from app.core.errors import (
    DownloadNotAuthorizedError,
    InvalidURLError,
    MetadataUnavailableError,
    UnsupportedPlatformError,
)
from app.core.urls import URLGuard
from app.providers.acquisition import PytubefixAcquisitionAdapter
from app.providers.base import CapabilityStatus, DownloadAuthorization, ProviderCapabilities
from app.providers.facebook import FacebookProvider, facebook_capabilities
from app.providers.youtube import YouTubeProvider, youtube_capabilities
from tests.conftest import FakeInspector

GUARD = URLGuard()


def make_youtube() -> YouTubeProvider:
    return YouTubeProvider(
        GUARD,
        FakeInspector(),
        youtube_capabilities(metadata_enabled=True),
    )


def make_facebook() -> FacebookProvider:
    return FacebookProvider(
        GUARD,
        FakeInspector(),
        facebook_capabilities(metadata_enabled=True, oauth_configured=True),
    )


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_youtube_url_validation(url: str, expected_id: str) -> None:
    normalized = make_youtube().validate_url(url)
    assert normalized.resource_id == expected_id
    assert normalized.host in YouTubeProvider.allowed_hosts


def test_youtube_isolates_facebook_urls() -> None:
    provider = make_youtube()
    assert provider.identify("https://www.facebook.com/watch?v=123456789") is None
    with pytest.raises(UnsupportedPlatformError):
        provider.validate_url("https://www.facebook.com/watch?v=123456789")


def test_youtube_rejects_invalid_video_id() -> None:
    with pytest.raises(InvalidURLError):
        make_youtube().validate_url("https://www.youtube.com/watch?v=short")


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.facebook.com/watch?v=123456789", "123456789"),
        ("https://facebook.com/videos/987654321/", "987654321"),
        ("https://m.facebook.com/reel/abcDEF123", "abcDEF123"),
        ("https://fb.watch/abcDEF123", "abcDEF123"),
    ],
)
def test_facebook_url_validation(url: str, expected_id: str) -> None:
    normalized = make_facebook().validate_url(url)
    assert normalized.resource_id == expected_id
    assert normalized.host in FacebookProvider.allowed_hosts


def test_facebook_isolates_youtube_urls() -> None:
    provider = make_facebook()
    assert provider.identify("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None
    with pytest.raises(UnsupportedPlatformError):
        provider.validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_facebook_rejects_short_resource_id() -> None:
    with pytest.raises(InvalidURLError):
        make_facebook().validate_url("https://www.facebook.com/watch?v=123")


async def test_metadata_inspection_returns_metadata() -> None:
    metadata = await make_youtube().inspect_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert metadata.platform.value == "youtube"
    assert metadata.video_id == "dQw4w9WgXcQ"
    assert metadata.title == "Sample title"
    assert metadata.author == "Sample author"


async def test_download_authorization_is_separate_and_denied() -> None:
    provider = make_youtube()
    authorization = DownloadAuthorization(authorized=True, basis="user_attestation", reference="test")
    with pytest.raises(DownloadNotAuthorizedError):
        await provider.authorize_download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", authorization)


async def test_youtube_download_capability_requires_user_confirmation() -> None:
    provider = YouTubeProvider(
        GUARD,
        FakeInspector(),
        youtube_capabilities(metadata_enabled=True, acquisition_enabled=True),
        acquisition=PytubefixAcquisitionAdapter(enabled=True),
    )
    assert provider.capabilities().authorized_download.status is CapabilityStatus.AVAILABLE

    with pytest.raises(DownloadNotAuthorizedError):
        await provider.authorize_download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            DownloadAuthorization(authorized=False),
        )

    decision = await provider.authorize_download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        DownloadAuthorization(authorized=True, basis="user_attestation"),
    )
    assert decision.allowed is True
    assert decision.adapter_name == "pytubefix"


async def test_metadata_disabled_provider_raises() -> None:
    provider = YouTubeProvider(
        GUARD,
        FakeInspector(),
        youtube_capabilities(metadata_enabled=False),
    )
    with pytest.raises(MetadataUnavailableError):
        await provider.inspect_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_provider_capabilities_are_never_fully_functional() -> None:
    for provider in (make_youtube(), make_facebook()):
        capabilities: ProviderCapabilities = provider.capabilities()
        assert capabilities.fully_functional is False
        assert capabilities.authorized_download.reason
