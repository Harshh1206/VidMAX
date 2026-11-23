from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DownloadJob, JobStatus, utcnow
from app.processing.streams import StreamCandidate
from app.providers.acquisition import StreamAcquisitionAdapter
from app.services.downloads import JobService
from app.services.files import FileService


def test_create_download_is_denied_without_authorized_adapter(client: TestClient, app) -> None:
    response = client.post(
        "/api/v1/downloads",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "authorization": {"authorized": True, "basis": "user_attestation"},
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOWNLOAD_NOT_AUTHORIZED"

    factory: sessionmaker[Session] = app.state.session_factory
    with factory() as session:
        assert session.query(DownloadJob).count() == 0


def test_job_lifecycle(client: TestClient, app) -> None:
    factory: sessionmaker[Session] = app.state.session_factory
    job_service: JobService = app.state.job_service
    file_service: FileService = app.state.file_service

    with factory() as session:
        job = job_service.create(
            session,
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        job_id = job.id

    response = client.get(f"/api/v1/downloads/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["progress"] == 0
    assert "file_path" not in payload
    assert payload["download_url"] is None

    assert client.get(f"/api/v1/downloads/{job_id}/file").status_code == 409

    output_dir = file_service.output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{job_id}.mp4"
    output.write_bytes(b"video-bytes")
    with factory() as session:
        job = session.get(DownloadJob, job_id)
        job_service.update(
            session,
            job,
            status=JobStatus.COMPLETED.value,
            progress=100,
            file_name="video.mp4",
            file_path=file_service.relative_path(output),
        )

    response = client.get(f"/api/v1/downloads/{job_id}")
    assert response.json()["status"] == "completed"
    assert response.json()["download_url"] == f"/api/v1/downloads/{job_id}/file"

    response = client.get(f"/api/v1/downloads/{job_id}/file")
    assert response.status_code == 200
    assert response.content == b"video-bytes"
    assert "storage" not in response.headers.get("content-disposition", "")

    assert client.delete(f"/api/v1/downloads/{job_id}").status_code == 204
    assert client.get(f"/api/v1/downloads/{job_id}").status_code == 404
    assert not file_service.job_dir(job_id).exists()


def test_invalid_and_unknown_job_ids(client: TestClient) -> None:
    assert client.get("/api/v1/downloads/not-a-uuid").status_code == 400
    assert client.get("/api/v1/downloads/00000000000000000000000000000000").status_code == 404


class FakeFormatAdapter(StreamAcquisitionAdapter):
    name = "fake_formats"
    enabled = True

    async def list_candidates(self, url: str) -> list[StreamCandidate]:
        return [
            StreamCandidate("137", "video", "mp4", "avc1", 1920, 1080, 5000, 25, label="1080p H.264"),
            StreamCandidate("136", "video", "mp4", "avc1", 1280, 720, 2500, 25, label="720p H.264"),
            StreamCandidate("140", "audio", "m4a", "mp4a", bitrate_kbps=128, label="AAC audio"),
        ]

    async def download_candidate(
        self,
        candidate: StreamCandidate,
        destination: Path,
        *,
        url: str | None = None,
    ) -> Path:
        destination.write_bytes(b"stream-bytes")
        return destination


def _enabled_app(make_app, make_registry):
    registry = make_registry(
        youtube_download=True,
        youtube_acquisition=FakeFormatAdapter(),
    )
    return make_app(
        registry=registry,
        enable_youtube_pytubefix_download=True,
    )


def test_enabled_download_creates_and_processes_job(make_app, make_registry) -> None:
    app = _enabled_app(make_app, make_registry)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/downloads",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "format_id": "137",
                "authorization": {"authorized": True, "basis": "user_attestation"},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["id"]
        job = client.get(f"/api/v1/downloads/{job_id}").json()
        assert job["status"] == "completed"

        manifest = app.state.file_service.read_manifest(job_id)
        assert manifest["format_id"] == "137"
        assert len(manifest["inputs"]) == 2
        assert client.get(f"/api/v1/downloads/{job_id}/file").status_code == 200


def test_enabled_download_rejects_unavailable_format(make_app, make_registry) -> None:
    app = _enabled_app(make_app, make_registry)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/downloads",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "format_id": "does-not-exist",
                "authorization": {"authorized": True, "basis": "user_attestation"},
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_enabled_download_requires_user_confirmation(make_app, make_registry) -> None:
    app = _enabled_app(make_app, make_registry)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/downloads",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "format_id": "137",
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOWNLOAD_NOT_AUTHORIZED"


def test_expired_job_is_not_served(client: TestClient, app) -> None:
    factory: sessionmaker[Session] = app.state.session_factory
    job_service: JobService = app.state.job_service
    with factory() as session:
        job = job_service.create(session, platform="local", source_url="local://upload")
        job_service.update(session, job, expires_at=utcnow() - timedelta(hours=1))
        job_id = job.id

    response = client.get(f"/api/v1/downloads/{job_id}")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "JOB_EXPIRED"

    with factory() as session:
        assert session.get(type(job_service.get(session, job_id)), job_id).status == JobStatus.EXPIRED.value
