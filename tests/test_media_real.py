import subprocess
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.errors import MediaValidationError
from app.processing.base import Operation, ProcessingRequest
from app.processing.ffmpeg import LocalFFmpegAdapter
from app.processing.media import FFprobeValidator
from app.processing.service import MediaProcessingService
from app.processing.streams import StreamCandidate
from app.providers.acquisition import StreamAcquisitionAdapter, StreamAcquisitionResult
from app.providers.base import (
    AuthorizationDecision,
    Capability,
    CapabilityStatus,
    DownloadAuthorization,
    Platform,
)
from app.services.acquisition import AuthorizedAcquisitionRequest


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def _validator(ffprobe: str) -> FFprobeValidator:
    return FFprobeValidator(
        ffprobe,
        timeout_seconds=30,
        min_bytes=64,
        max_bytes=16 * 1024 * 1024,
        duration_tolerance_seconds=2.0,
    )


def _video(path: Path, ffmpeg: str, codec: str = "libx264") -> None:
    _run(
        [
            ffmpeg,
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10",
            "-t",
            "1",
            "-an",
            "-c:v",
            codec,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _audio(path: Path, ffmpeg: str, codec: str = "aac") -> None:
    _run(
        [
            ffmpeg,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1",
            "-c:a",
            codec,
            str(path),
        ]
    )


async def test_a_merge_separate_streams_and_validate(media_tools, tmp_path: Path) -> None:
    ffmpeg, ffprobe = media_tools
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    _video(video, ffmpeg)
    _audio(audio, ffmpeg)
    validator = _validator(ffprobe)
    service = MediaProcessingService(LocalFFmpegAdapter(ffmpeg_path=ffmpeg), validator)
    request = ProcessingRequest(
        job_id="av-merge-test",
        operation=Operation.AV_MERGE,
        inputs=(video, audio),
        output_dir=tmp_path / "merged",
        target_format="mp4",
        timeout_seconds=60,
        max_output_bytes=16 * 1024 * 1024,
    )

    result = await service.process(request)
    info = await validator.validate_output(
        result.output_path,
        expected_format="mp4",
        expect_audio=True,
        expect_video=True,
    )

    assert result.bytes_written > 0
    assert result.output_path.suffix == ".mp4"
    assert info.video_streams and info.audio_streams
    assert 0.5 < info.duration_seconds < 2.0


async def test_b_convert_webm_to_mp4_and_validate(media_tools, tmp_path: Path) -> None:
    ffmpeg, ffprobe = media_tools
    source = tmp_path / "source.webm"
    _run(
        [
            ffmpeg,
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1",
            "-c:v",
            "libvpx",
            "-b:v",
            "200k",
            "-c:a",
            "libopus",
            str(source),
        ]
    )
    validator = _validator(ffprobe)
    service = MediaProcessingService(LocalFFmpegAdapter(ffmpeg_path=ffmpeg), validator)
    request = ProcessingRequest(
        job_id="convert-test",
        operation=Operation.CONVERT,
        inputs=(source,),
        output_dir=tmp_path / "converted",
        target_format="mp4",
        timeout_seconds=60,
        max_output_bytes=16 * 1024 * 1024,
    )

    result = await service.process(request)
    info = await validator.validate_output(result.output_path, expected_format="mp4")

    assert info.video_streams[0].codec_name == "h264"
    assert info.audio_streams[0].codec_name == "aac"
    assert 0.5 < info.duration_seconds < 2.0


def test_c_end_to_end_separate_stream_upload(make_real_app, media_tools, tmp_path: Path) -> None:
    ffmpeg, _ = media_tools
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    _video(video, ffmpeg)
    _audio(audio, ffmpeg)
    app = make_real_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads",
            files=[
                ("files", ("video.mp4", video.read_bytes(), "video/mp4")),
                ("files", ("audio.m4a", audio.read_bytes(), "audio/mp4")),
            ],
            data={
                "operation": "merge_av",
                "target_format": "mp4",
                "attestation": "true",
                "stream_roles": "video,audio",
                "quality": "best",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        job = client.get(f"/api/v1/downloads/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "completed"
        assert job.json()["progress"] == 100

        downloaded = client.get(f"/api/v1/downloads/{job_id}/file")
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("video/mp4")
        assert b"ftyp" in downloaded.content[:64]
        assert not app.state.file_service.temp_dir(job_id).exists()


def test_failed_merge_marks_job_failed_and_cleans_temp(make_real_app, media_tools, tmp_path: Path) -> None:
    ffmpeg, _ = media_tools
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    _video(video, ffmpeg)
    audio.write_bytes(b"not media")
    app = make_real_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads",
            files=[
                ("files", ("video.mp4", video.read_bytes(), "video/mp4")),
                ("files", ("audio.m4a", audio.read_bytes(), "audio/mp4")),
            ],
            data={
                "operation": "merge_av",
                "target_format": "mp4",
                "attestation": "true",
                "stream_roles": "video,audio",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = client.get(f"/api/v1/downloads/{job_id}").json()

        assert job["status"] == "failed"
        assert job["error_message"]
        assert "FFprobe" in job["error_message"] or "FFmpeg" in job["error_message"]
        assert not app.state.file_service.temp_dir(job_id).exists()
        assert not app.state.file_service.output_dir(job_id).exists()


async def test_d_full_flow_with_mocked_stream_manifest(
    make_real_app,
    media_tools,
    tmp_path: Path,
    monkeypatch,
) -> None:
    ffmpeg, _ = media_tools
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    _video(video, ffmpeg)
    _audio(audio, ffmpeg)
    app = make_real_app()
    provider = app.state.registry.get(Platform.YOUTUBE)
    patched_capabilities = replace(
        provider.capabilities(),
        authorized_download=Capability(CapabilityStatus.AVAILABLE, "test-only authorization"),
    )
    monkeypatch.setattr(provider, "_capabilities", patched_capabilities)

    async def authorize(url, authorization):
        assert authorization.authorized is True
        return AuthorizationDecision(True, "test-owned media", "mock_streams")

    monkeypatch.setattr(app.state.inspection_service, "authorize", authorize)

    class MockStreamAdapter(StreamAcquisitionAdapter):
        name = "mock_streams"
        enabled = True

        async def list_candidates(self, url: str) -> list[StreamCandidate]:
            return [
                StreamCandidate("1", "video", "mp4", "h264", 160, 120, 500, 10),
                StreamCandidate("2", "audio", "m4a", "aac", bitrate_kbps=128),
            ]

        async def download_candidate(
            self,
            candidate: StreamCandidate,
            destination: Path,
            *,
            url: str | None = None,
        ) -> Path:
            return destination

        async def acquire(
            self,
            url: str,
            guard,
            allowed_hosts,
            quality: str | None,
            destination_factory,
            *,
            format_id: str | None = None,
        ) -> StreamAcquisitionResult:
            video_path = destination_factory("video", "mp4")
            audio_path = destination_factory("audio", "m4a")
            video_path.write_bytes(video.read_bytes())
            audio_path.write_bytes(audio.read_bytes())
            return StreamAcquisitionResult(
                inputs=(video_path, audio_path),
                roles=("video", "audio"),
                cleanup_paths=(video_path, audio_path),
            )

    with TestClient(app) as client:
        job = await app.state.acquisition_service.create_and_process(
            AuthorizedAcquisitionRequest(
                platform=Platform.YOUTUBE,
                source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                authorization=DownloadAuthorization(
                    authorized=True,
                    basis="test-owned media",
                    reference="local-fixture",
                ),
                quality="best",
            ),
            MockStreamAdapter(),
        )
        assert job.status == "completed"
        downloaded = client.get(f"/api/v1/downloads/{job.id}/file")
        assert downloaded.status_code == 200
        assert b"ftyp" in downloaded.content[:64]
        assert not app.state.file_service.temp_dir(job.id).exists()


def test_validation_failure_removes_partial_output(make_real_app, media_tools, tmp_path: Path, monkeypatch) -> None:
    ffmpeg, _ = media_tools
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    _video(video, ffmpeg)
    _audio(audio, ffmpeg)
    app = make_real_app()

    async def fail_validation(*args, **kwargs):
        raise MediaValidationError("Simulated validation failure")

    monkeypatch.setattr(app.state.media_inspector, "validate_output", fail_validation)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads",
            files=[
                ("files", ("video.mp4", video.read_bytes(), "video/mp4")),
                ("files", ("audio.m4a", audio.read_bytes(), "audio/mp4")),
            ],
            data={
                "operation": "merge_av",
                "target_format": "mp4",
                "attestation": "true",
                "stream_roles": "video,audio",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = client.get(f"/api/v1/downloads/{job_id}").json()

        assert job["status"] == "failed"
        assert job["error_message"] == "Simulated validation failure"
        assert not list(app.state.file_service.output_dir(job_id).glob("*"))
        assert not app.state.file_service.temp_dir(job_id).exists()


def test_video_only_conversion_allows_missing_audio(make_real_app, media_tools, tmp_path: Path) -> None:
    ffmpeg, _ = media_tools
    source = tmp_path / "video_only.webm"
    _video(source, ffmpeg, codec="libvpx")
    app = make_real_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads",
            files=[("files", ("video_only.webm", source.read_bytes(), "video/webm"))],
            data={"operation": "convert", "target_format": "mp4", "attestation": "true"},
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = client.get(f"/api/v1/downloads/{job_id}").json()

        assert job["status"] == "completed"
        assert job["error_message"] is None
        downloaded = client.get(f"/api/v1/downloads/{job_id}/file")
        assert downloaded.status_code == 200
        assert b"ftyp" in downloaded.content[:64]
