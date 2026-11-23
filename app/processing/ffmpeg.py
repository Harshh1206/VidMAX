import asyncio
from pathlib import Path

from app.core.errors import ProcessingError, UnsupportedOperationError, redact_media_paths
from app.core.logging import get_logger
from app.processing.base import Operation, ProcessingAdapter, ProcessingRequest, ProcessingResult

_AUDIO_CODECS = {"mp3": "libmp3lame", "m4a": "aac", "wav": "pcm_s16le"}
_VIDEO_CODECS = {
    "mp4": ("libx264", "aac"),
    "mkv": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
}
_LOGGER = get_logger(__name__)


class LocalFFmpegAdapter(ProcessingAdapter):
    name = "local_ffmpeg"
    supported_operations = frozenset({Operation.CONVERT, Operation.MERGE, Operation.AV_MERGE})

    def __init__(
        self,
        allowed_formats: frozenset[str] | None = None,
        max_inputs: int = 8,
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self.allowed_formats = allowed_formats or frozenset(_AUDIO_CODECS) | frozenset(_VIDEO_CODECS)
        self.max_inputs = max_inputs
        self.ffmpeg_path = ffmpeg_path

    def output_path(self, request: ProcessingRequest) -> Path:
        return request.output_dir / f"{request.job_id}.{request.target_format}"

    def concat_path(self, request: ProcessingRequest) -> Path:
        return request.output_dir / f"{request.job_id}.concat.txt"

    def build_convert_command(self, request: ProcessingRequest) -> list[str]:
        self._validate(request)
        if len(request.inputs) != 1:
            raise UnsupportedOperationError("Conversion requires exactly one input file")
        output = self.output_path(request)
        command = self._base_command() + ["-i", str(request.inputs[0])]
        command += self._codec_args(request.target_format)
        command += self._duration_args(request)
        if request.target_format == "mp4":
            command += ["-movflags", "+faststart"]
        command.append(str(output))
        return command

    def build_merge_command(self, request: ProcessingRequest) -> list[str]:
        self._validate(request)
        if len(request.inputs) < 2:
            raise UnsupportedOperationError("Merging requires at least two input files")
        manifest = self.concat_path(request)
        output = self.output_path(request)
        command = self._base_command() + [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            "-c",
            "copy",
        ]
        command += self._duration_args(request)
        command.append(str(output))
        return command

    def build_av_merge_command(self, request: ProcessingRequest) -> list[str]:
        self._validate(request)
        if request.target_format != "mp4":
            raise UnsupportedOperationError("Separate AV merging only supports MP4 output")
        if len(request.inputs) != 2:
            raise UnsupportedOperationError("Separate AV merging requires a video and an audio input")
        output = self.output_path(request)
        command = self._base_command() + [
            "-i",
            str(request.inputs[0]),
            "-i",
            str(request.inputs[1]),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
        command += self._av_codec_args(request)
        command += self._duration_args(request)
        command += ["-movflags", "+faststart", str(output)]
        return command

    async def process(self, request: ProcessingRequest) -> ProcessingResult:
        if not self.supports(request.operation):
            raise UnsupportedOperationError(f"Unsupported operation: {request.operation.value}")
        for path in request.inputs:
            if not path.is_file():
                raise ProcessingError("An input file is missing")

        request.output_dir.mkdir(parents=True, exist_ok=True)
        output = self.output_path(request)
        if request.operation is Operation.CONVERT:
            command = self.build_convert_command(request)
        elif request.operation is Operation.AV_MERGE:
            command = self.build_av_merge_command(request)
        else:
            manifest = self.concat_path(request)
            manifest.write_text(
                "".join(f"file '{self._escape_concat_path(path)}'\n" for path in request.inputs),
                encoding="utf-8",
            )
            command = self.build_merge_command(request)

        _LOGGER.info(
            "Starting FFmpeg processing",
            extra={
                "job_id": request.job_id,
                "operation": request.operation.value,
                "input_count": len(request.inputs),
                "target_format": request.target_format,
                "quality": request.quality,
            },
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), request.timeout_seconds)
            except TimeoutError:
                process.kill()
                await process.wait()
                output.unlink(missing_ok=True)
                raise ProcessingError("Media processing timed out") from None
        except FileNotFoundError as exc:
            output.unlink(missing_ok=True)
            raise ProcessingError("FFmpeg is not installed") from exc

        if process.returncode != 0:
            output.unlink(missing_ok=True)
            detail = stderr.decode("utf-8", errors="replace") if stderr else "unknown error"
            message = redact_media_paths(detail, (*request.inputs, output))
            raise ProcessingError(f"FFmpeg failed: {message}")

        if not output.is_file():
            raise ProcessingError("FFmpeg did not produce an output file")
        size = output.stat().st_size
        if size > request.max_output_bytes:
            output.unlink(missing_ok=True)
            raise ProcessingError("Processed file exceeds the configured size limit")
        _LOGGER.info(
            "FFmpeg processing finished",
            extra={"job_id": request.job_id, "operation": request.operation.value, "bytes_written": size},
        )
        return ProcessingResult(
            output_path=output,
            output_name=output.name,
            bytes_written=size,
        )

    def _validate(self, request: ProcessingRequest) -> None:
        if request.target_format not in self.allowed_formats:
            raise UnsupportedOperationError(f"Unsupported target format: {request.target_format}")
        if not request.inputs or len(request.inputs) > self.max_inputs:
            raise UnsupportedOperationError("The number of input files is not allowed")
        if request.timeout_seconds <= 0 or request.max_output_bytes <= 0:
            raise UnsupportedOperationError("Invalid processing limits")

    def _base_command(self) -> list[str]:
        return [self.ffmpeg_path, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]

    @staticmethod
    def _codec_args(target_format: str) -> list[str]:
        if target_format in _AUDIO_CODECS:
            return ["-vn", "-c:a", _AUDIO_CODECS[target_format]]
        video_codec, audio_codec = _VIDEO_CODECS[target_format]
        return ["-c:v", video_codec, "-c:a", audio_codec]

    @staticmethod
    def _av_codec_args(request: ProcessingRequest) -> list[str]:
        video_codec = "copy" if request.video_codec == "copy" else "libx264"
        audio_codec = "copy" if request.audio_codec == "copy" else "aac"
        return ["-c:v", video_codec, "-c:a", audio_codec]

    @staticmethod
    def _duration_args(request: ProcessingRequest) -> list[str]:
        if request.max_duration_seconds is None:
            return []
        return ["-t", str(request.max_duration_seconds)]

    @staticmethod
    def _escape_concat_path(path: Path) -> str:
        return str(path).replace("'", "'\\''")
