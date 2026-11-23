from fastapi.testclient import TestClient


def upload_payload(**overrides):
    data = {"operation": "convert", "target_format": "mp4", "attestation": "true"}
    data.update(overrides)
    return data


def test_upload_creates_job_and_processes(client: TestClient, app) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[("files", ("clip.mp4", b"video-data", "video/mp4"))],
        data=upload_payload(),
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert response.json()["platform"] == "local"
    assert "file_path" not in response.json()

    job = client.get(f"/api/v1/downloads/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["progress"] == 100

    file_response = client.get(f"/api/v1/downloads/{job_id}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"processed-media"


def test_upload_requires_authorization_attestation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[("files", ("clip.mp4", b"video-data", "video/mp4"))],
        data=upload_payload(attestation="false"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_upload_rejects_unsupported_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[("files", ("clip.mp4", b"video-data", "video/mp4"))],
        data=upload_payload(target_format="exe"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_OPERATION"


def test_merge_requires_two_files(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[("files", ("a.mp4", b"a", "video/mp4"))],
        data=upload_payload(operation="merge"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_merge_with_two_files(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[
            ("files", ("a.mp4", b"a", "video/mp4")),
            ("files", ("b.mp4", b"b", "video/mp4")),
        ],
        data=upload_payload(operation="merge"),
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/v1/downloads/{job_id}").json()["status"] == "completed"


def test_upload_sanitizes_filename(client: TestClient, app) -> None:
    response = client.post(
        "/api/v1/uploads",
        files=[("files", ("../../evil name.mp4", b"video-data", "video/mp4"))],
        data=upload_payload(),
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    manifest = app.state.file_service.read_manifest(job_id)
    assert manifest["inputs"][0]["name"] == "evil_name.mp4"


def test_upload_size_limit(make_app) -> None:
    app = make_app(max_upload_bytes=4)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/uploads",
            files=[("files", ("clip.mp4", b"0123456789", "video/mp4"))],
            data=upload_payload(),
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_uploads_endpoint_is_optional(make_app) -> None:
    app = make_app(enable_local_uploads=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/uploads",
            files=[("files", ("clip.mp4", b"video-data", "video/mp4"))],
            data=upload_payload(),
        )
    assert response.status_code == 404
