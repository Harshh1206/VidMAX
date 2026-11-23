from fastapi.testclient import TestClient

from tests.test_downloads import FakeFormatAdapter


def test_inspect_youtube(client: TestClient) -> None:
    response = client.post(
        "/api/v1/inspect",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "youtube"
    assert payload["video_id"] == "dQw4w9WgXcQ"
    assert payload["title"] == "Sample title"
    assert payload["metadata_available"] is True
    assert payload["downloadable"] is False
    assert payload["download_capability_status"] == "not_implemented"


def test_inspect_youtube_exposes_real_formats_when_enabled(make_app, make_registry) -> None:
    app = make_app(
        registry=make_registry(
            youtube_download=True,
            youtube_acquisition=FakeFormatAdapter(),
        ),
        enable_youtube_pytubefix_download=True,
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/inspect",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
    payload = response.json()
    assert response.status_code == 200
    assert payload["downloadable"] is True
    assert payload["download_capability_status"] == "available"
    assert [item["id"] for item in payload["formats"]] == ["137", "136"]
    assert payload["recommended_format_id"] == "137"


def test_inspect_facebook(client: TestClient) -> None:
    response = client.post(
        "/api/v1/inspect",
        json={"url": "https://www.facebook.com/watch?v=123456789"},
    )
    assert response.status_code == 200
    assert response.json()["platform"] == "facebook"
    assert response.json()["video_id"] == "123456789"


def test_inspect_rejects_malicious_url(client: TestClient) -> None:
    response = client.post(
        "/api/v1/inspect",
        json={"url": "http://127.0.0.1/watch?v=dQw4w9WgXcQ"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"


def test_inspect_rejects_unsupported_platform(client: TestClient) -> None:
    response = client.post(
        "/api/v1/inspect",
        json={"url": "https://vimeo.com/123456"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_PLATFORM"


def test_inspect_unconfigured_facebook_metadata(make_app, make_registry) -> None:
    app = make_app(registry=make_registry(facebook_token=False))
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/inspect",
            json={"url": "https://www.facebook.com/watch?v=123456789"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "METADATA_UNAVAILABLE"


def test_inspect_does_not_authorize_download(client: TestClient, app) -> None:
    provider = app.state.registry.resolve("https://youtu.be/dQw4w9WgXcQ")

    async def fail_authorization(*args, **kwargs):
        raise AssertionError("inspection must not call download authorization")

    provider.authorize_download = fail_authorization
    response = client.post("/api/v1/inspect", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert response.status_code == 200
