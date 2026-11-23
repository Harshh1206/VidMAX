from pathlib import Path

import pytest

from app.core.errors import (
    DownloadNotAuthorizedError,
    MediaToolUnavailableError,
    MediaValidationError,
    ProcessingError,
    redact_media_paths,
)
from app.processing.base import Operation, ProcessingRequest
from app.processing.ffmpeg import LocalFFmpegAdapter
from app.processing.media import FFprobeValidator, MediaInfo, MediaStream
from app.processing.service import MediaProcessingService
from app.processing.streams import StreamCandidate, select_streams
from app.providers.acquisition import PytubefixAcquisitionAdapter
from app.providers.base import CapabilityStatus
from app.providers.youtube import youtube_capabilities


def _request(tmp_path: Path, **overrides) -> ProcessingRequest:
    values = {
        "job_id": "media-unit",
        "operation": Operation.AV_MERGE,
        "inputs": (tmp_path / "video.mp4", tmp_path / "audio.m4a"),
        "output_dir": tmp_path / "out",
        "target_format": "mp4",
        "timeout_seconds": 30,
        "max_output_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return ProcessingRequest(**values)


def test_av_merge_command_maps_streams_and_prefers_copy(tmp_path: Path) -> None:
    command = LocalFFmpegAdapter().build_av_merge_command(_request(tmp_path))
    assert command[command.index("-map") + 1] == "0:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "1:a:0"
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert "+faststart" in command


def test_av_merge_command_reencodes_only_when_requested(tmp_path: Path) -> None:
    request = _request(tmp_path, video_codec="libx264", audio_codec="aac")
    command = LocalFFmpegAdapter().build_av_merge_command(request)
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


def test_stream_selection_prefers_requested_quality_and_compatible_container() -> None:
    candidates = [
        StreamCandidate("1", "video", "webm", "vp9", 1920, 1080, 4000, 30),
        StreamCandidate("2", "video", "mp4", "avc1", 1280, 720, 2500, 30),
        StreamCandidate("3", "video", "mp4", "h264", 1280, 720, 3000, 30),
        StreamCandidate("4", "audio", "webm", "opus", bitrate_kbps=160),
        StreamCandidate("5", "audio", "m4a", "mp4a", bitrate_kbps=128),
    ]
    selection = select_streams(candidates, "720p")
    assert selection.video.identifier == "3"
    assert selection.audio.identifier == "5"
    assert selection.quality == "720p"


def test_stream_selection_rejects_missing_streams() -> None:
    with pytest.raises(ProcessingError, match="video-only"):
        select_streams([StreamCandidate("1", "audio", "m4a", "aac")])
    with pytest.raises(ProcessingError, match="audio-only"):
        select_streams([StreamCandidate("1", "video", "mp4", "h264", 1920, 1080)])


async def test_media_service_rejects_input_without_video_stream(tmp_path: Path) -> None:
    request = _request(tmp_path)
    for path in request.inputs:
        path.write_bytes(b"input")

    class Inspector(FFprobeValidator):
        def __init__(self) -> None:
            pass

        async def probe(self, path: Path) -> MediaInfo:
            if path == request.inputs[0]:
                return MediaInfo("mp4", 1.0, 100, (MediaStream(0, "audio", "aac", None, None, None, None, None),))
            return MediaInfo("mp4", 1.0, 100, (MediaStream(0, "audio", "aac", None, None, None, None, None),))

    service = MediaProcessingService(LocalFFmpegAdapter(), Inspector())
    with pytest.raises(MediaValidationError, match="no video stream"):
        await service.process(request)


async def test_pytubefix_adapter_is_disabled_without_authorization(guard) -> None:
    adapter = PytubefixAcquisitionAdapter(enabled=False)
    with pytest.raises(DownloadNotAuthorizedError):
        await adapter.acquire(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guard,
            frozenset({"youtube.com", "www.youtube.com"}),
            "best",
            lambda role, suffix: Path("unused"),
        )


async def test_validator_rejects_empty_output(tmp_path: Path) -> None:
    path = tmp_path / "empty.mp4"
    path.write_bytes(b"")
    validator = FFprobeValidator(
        "unused",
        timeout_seconds=5,
        min_bytes=1,
        max_bytes=1024,
        duration_tolerance_seconds=1.0,
    )
    with pytest.raises(MediaValidationError, match="empty"):
        await validator.validate_output(path)


async def test_validator_rejects_output_missing_audio(tmp_path: Path) -> None:
    path = tmp_path / "video-only.mp4"
    path.write_bytes(b"media")
    validator = FFprobeValidator(
        "unused",
        timeout_seconds=5,
        min_bytes=1,
        max_bytes=1024,
        duration_tolerance_seconds=1.0,
    )
    video_stream = MediaStream(0, "video", "h264", 160, 120, 10.0, 1000, 1.0)

    async def probe(_path: Path) -> MediaInfo:
        return MediaInfo("mov,mp4,m4a,3gp,3g2,mj2", 1.0, 5, (video_stream,))

    validator.probe = probe  # type: ignore[method-assign]
    with pytest.raises(MediaValidationError, match="audio stream"):
        await validator.validate_output(path)


async def test_missing_ffprobe_tool_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "input.mp4"
    path.write_bytes(b"input")
    validator = FFprobeValidator(
        "definitely-missing-ffprobe",
        timeout_seconds=5,
        min_bytes=1,
        max_bytes=1024,
        duration_tolerance_seconds=1.0,
    )
    with pytest.raises(MediaToolUnavailableError):
        await validator.probe(path)


async def test_missing_ffmpeg_tool_is_reported(tmp_path: Path) -> None:
    request = _request(tmp_path, operation=Operation.CONVERT, inputs=(tmp_path / "video.mp4",))
    request.inputs[0].write_bytes(b"input")
    adapter = LocalFFmpegAdapter(ffmpeg_path="definitely-missing-ffmpeg")
    with pytest.raises(ProcessingError, match="not installed"):
        await adapter.process(request)


def test_enabling_pytubefix_marks_download_capability_available() -> None:
    capabilities = youtube_capabilities(metadata_enabled=True, acquisition_enabled=True)
    assert capabilities.authorized_download.status is CapabilityStatus.AVAILABLE
    assert capabilities.fully_functional is False


def test_error_details_redact_internal_paths() -> None:
    detail = r"C:\Users\Lenovo\Desktop\VidMAX\storage\jobs\abc\video.mp4: Invalid data"
    assert "C:\\Users" not in redact_media_paths(detail)
    assert "<media>" in redact_media_paths(detail)
