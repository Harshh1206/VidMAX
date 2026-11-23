from dataclasses import replace

from app.core.errors import MediaValidationError
from app.core.logging import get_logger
from app.processing.base import Operation, ProcessingAdapter, ProcessingRequest, ProcessingResult
from app.processing.media import FFprobeValidator, MediaInfo

_LOGGER = get_logger(__name__)
_FFPROBE_FORMATS = {"mkv": "matroska"}
_AUDIO_FORMATS = frozenset({"mp3", "m4a", "wav"})
_MP4_VIDEO_CODECS = frozenset({"h264", "avc1"})
_MP4_AUDIO_CODECS = frozenset({"aac", "mp4a"})


class MediaInspector(FFprobeValidator):
    pass


class MediaProcessingService:
    def __init__(self, adapter: ProcessingAdapter, inspector: MediaInspector | None = None) -> None:
        self.adapter = adapter
        self.inspector = inspector

    async def process(self, request: ProcessingRequest) -> ProcessingResult:
        prepared = await self._prepare(request)
        result = await self.adapter.process(prepared)
        if self.inspector is not None:
            expected_format = _FFPROBE_FORMATS.get(prepared.target_format, prepared.target_format)
            expect_video = prepared.expect_video and prepared.target_format not in _AUDIO_FORMATS
            await self.inspector.validate_output(
                result.output_path,
                expected_format=expected_format,
                expect_audio=prepared.expect_audio,
                expect_video=expect_video,
                max_bytes=prepared.max_output_bytes,
                max_duration_seconds=prepared.max_duration_seconds,
            )
        _LOGGER.info(
            "Media processing validated",
            extra={
                "job_id": request.job_id,
                "operation": request.operation.value,
                "validated": self.inspector is not None,
            },
        )
        return result

    async def _prepare(self, request: ProcessingRequest) -> ProcessingRequest:
        if self.inspector is None:
            return request
        if request.operation is Operation.CONVERT and len(request.inputs) == 1:
            info = await self.inspector.probe(request.inputs[0])
            expect_video = request.expect_video and bool(info.video_streams)
            return replace(request, expect_audio=bool(info.audio_streams), expect_video=expect_video)
        if request.operation is not Operation.AV_MERGE:
            return request
        if len(request.inputs) != 2:
            raise MediaValidationError("Separate AV merging requires exactly two inputs")
        video_info = await self.inspector.probe(request.inputs[0])
        audio_info = await self.inspector.probe(request.inputs[1])
        if not video_info.video_streams:
            raise MediaValidationError("Video input contains no video stream")
        if not audio_info.audio_streams:
            raise MediaValidationError("Audio input contains no audio stream")
        video_codec = _codec_plan(video_info, "video", _MP4_VIDEO_CODECS, request.allow_reencode)
        audio_codec = _codec_plan(audio_info, "audio", _MP4_AUDIO_CODECS, request.allow_reencode)
        _LOGGER.info(
            "Selected AV stream codecs",
            extra={
                "job_id": request.job_id,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
            },
        )
        return replace(request, video_codec=video_codec, audio_codec=audio_codec)


def _codec_plan(info: MediaInfo, kind: str, compatible: frozenset[str], allow_reencode: bool) -> str:
    streams = info.video_streams if kind == "video" else info.audio_streams
    codec = (streams[0].codec_name or "").lower()
    if codec in compatible:
        return "copy"
    if not allow_reencode:
        raise MediaValidationError(f"{kind.capitalize()} stream codec is not MP4-compatible")
    return "libx264" if kind == "video" else "aac"
