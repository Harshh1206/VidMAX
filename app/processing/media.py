import asyncio
import json
import shutil
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.core.errors import MediaToolUnavailableError, MediaValidationError, redact_media_paths


@dataclass(frozen=True)
class MediaStream:
    index: int
    codec_type: str
    codec_name: str | None
    width: int | None
    height: int | None
    fps: float | None
    bitrate: int | None
    duration: float | None


@dataclass(frozen=True)
class MediaInfo:
    format_name: str
    duration_seconds: float
    size_bytes: int
    streams: tuple[MediaStream, ...]

    @property
    def video_streams(self) -> tuple[MediaStream, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "video")

    @property
    def audio_streams(self) -> tuple[MediaStream, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "audio")


def resolve_media_tool(configured: str | None, binary: str) -> str:
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate.resolve())
        raise MediaToolUnavailableError(f"Configured {binary} was not found")
    found = shutil.which(binary)
    if found:
        return found
    raise MediaToolUnavailableError(f"{binary} is not installed or not on PATH")


class FFprobeValidator:
    def __init__(
        self,
        ffprobe_path: str,
        *,
        timeout_seconds: int,
        min_bytes: int,
        max_bytes: int,
        duration_tolerance_seconds: float,
    ) -> None:
        self.ffprobe_path = ffprobe_path
        self.timeout_seconds = timeout_seconds
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.duration_tolerance_seconds = duration_tolerance_seconds

    async def probe(self, path: Path) -> MediaInfo:
        if not path.is_file():
            raise MediaValidationError("Input media file is missing")
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        stdout, stderr = await self._run(command, "FFprobe", path)
        try:
            payload = json.loads(stdout)
        except ValueError as exc:
            raise MediaValidationError("FFprobe returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MediaValidationError("FFprobe returned an unexpected payload")
        return self._to_media_info(payload, path)

    async def validate_output(
        self,
        path: Path,
        *,
        expected_format: str = "mp4",
        expect_audio: bool = True,
        expect_video: bool = True,
        max_bytes: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> MediaInfo:
        if not path.is_file():
            raise MediaValidationError("Output file does not exist")
        size = path.stat().st_size
        if size == 0:
            raise MediaValidationError("Output file is empty")
        if size < self.min_bytes:
            raise MediaValidationError("Output file is too small to be valid media")
        limit = max_bytes or self.max_bytes
        if size > limit:
            raise MediaValidationError("Output file exceeds the configured size limit")

        info = await self.probe(path)
        formats = {part.strip().lower() for part in info.format_name.split(",")}
        if expected_format not in formats:
            raise MediaValidationError(f"Output container is not {expected_format.upper()}")
        if expect_video and not info.video_streams:
            raise MediaValidationError("Output has no video stream")
        if expect_audio and not info.audio_streams:
            raise MediaValidationError("Output has no audio stream")
        if info.duration_seconds <= 0:
            raise MediaValidationError("Output duration is invalid")
        if max_duration_seconds and info.duration_seconds > max_duration_seconds + self.duration_tolerance_seconds:
            raise MediaValidationError("Output duration exceeds the allowed limit")
        return info

    async def _run(self, command: list[str], tool_name: str, path: Path) -> tuple[str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout_seconds)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise MediaValidationError(f"{tool_name} timed out") from None
        except FileNotFoundError as exc:
            raise MediaToolUnavailableError(f"{tool_name} is not installed") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace") if stderr else "unknown error"
            raise MediaValidationError(f"{tool_name} failed: {redact_media_paths(detail, (path,))}")
        return stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

    @staticmethod
    def _to_media_info(payload: dict, path: Path) -> MediaInfo:
        details = payload.get("format") if isinstance(payload.get("format"), dict) else {}
        raw_streams = payload.get("streams")
        if not isinstance(raw_streams, list):
            raw_streams = []
        streams: list[MediaStream] = []
        for raw in raw_streams:
            if not isinstance(raw, dict):
                continue
            streams.append(
                MediaStream(
                    index=_as_int(raw.get("index"), 0),
                    codec_type=str(raw.get("codec_type") or ""),
                    codec_name=raw.get("codec_name") if isinstance(raw.get("codec_name"), str) else None,
                    width=_as_int(raw.get("width")),
                    height=_as_int(raw.get("height")),
                    fps=_as_fraction(raw.get("avg_frame_rate") or raw.get("r_frame_rate")),
                    bitrate=_as_int(raw.get("bit_rate")),
                    duration=_as_float(raw.get("duration")),
                )
            )
        size = _as_int(details.get("size")) or path.stat().st_size
        duration = _as_float(details.get("duration"))
        if duration <= 0:
            candidates = [stream.duration for stream in streams if stream.duration and stream.duration > 0]
            duration = max(candidates) if candidates else 0.0
        return MediaInfo(
            format_name=str(details.get("format_name") or ""),
            duration_seconds=duration,
            size_bytes=size,
            streams=tuple(streams),
        )


def _as_int(value: object, default: int | None = None) -> int | None:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_fraction(value: object) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    try:
        result = float(Fraction(value))
        return result if result > 0 else None
    except (ValueError, ZeroDivisionError):
        return None
