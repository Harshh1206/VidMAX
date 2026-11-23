import pytest

from app.core.errors import InvalidURLError, UnsupportedPlatformError
from app.core.urls import URLGuard

GUARD = URLGuard()


@pytest.mark.parametrize(
    "url,host",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "www.youtube.com"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtu.be"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "m.youtube.com"),
        ("https://www.facebook.com/watch?v=123456789", "www.facebook.com"),
        ("https://fb.watch/abcDEF123", "fb.watch"),
    ],
)
def test_valid_allowlisted_urls(url: str, host: str) -> None:
    normalized = GUARD.parse(url)
    assert normalized.host == host
    assert normalized.scheme == "https"
    assert normalized.url == url or normalized.url.startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://youtube.com/watch?v=dQw4w9WgXcQ",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com:8443/watch?v=dQw4w9WgXcQ",
        "https://127.0.0.1/watch?v=dQw4w9WgXcQ",
        "https://192.168.1.10/watch",
        "https://[::1]/watch",
        "https://localhost/watch",
        "https://youtube.com.localdomain/watch",
        "https://youtube.com.evil.example/watch",
        "https://youtube.com@evil.example/watch",
        "https://youtube.com/watch v=dQw4w9WgXcQ",
        "",
        "not-a-url",
    ],
)
def test_malicious_and_invalid_urls_rejected(url: str) -> None:
    with pytest.raises(InvalidURLError):
        GUARD.parse(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil-youtube.com/watch",
        "https://notyoutube.com/watch",
        "https://youtu.be.evil.org/abc",
    ],
)
def test_lookalike_hosts_rejected_by_allowlist(url: str) -> None:
    with pytest.raises(UnsupportedPlatformError):
        GUARD.validate_candidate(
            url,
            {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
        )


def test_host_allowlist_is_exact() -> None:
    with pytest.raises(UnsupportedPlatformError):
        GUARD.validate_candidate("https://www.youtube.com.evil.org/watch", {"youtube.com"})
    normalized = GUARD.validate_candidate("https://WWW.YOUTUBE.COM/watch", {"www.youtube.com"})
    assert normalized.host == "www.youtube.com"


def test_redirect_chain_validation() -> None:
    guard = URLGuard()
    final = guard.validate_redirect_chain(
        ["https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        {"youtu.be", "www.youtube.com"},
    )
    assert final is not None
    assert final.host == "www.youtube.com"

    with pytest.raises(UnsupportedPlatformError):
        guard.validate_redirect("https://evil.org/video", {"youtube.com"})

    with pytest.raises(InvalidURLError):
        guard.validate_redirect_chain(["https://youtu.be/a"] * 6, {"youtu.be"})


def test_redirect_to_ip_rejected() -> None:
    with pytest.raises(InvalidURLError):
        URLGuard().validate_redirect("https://10.0.0.5/internal", {"10.0.0.5"})
