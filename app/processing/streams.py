import re
from dataclasses import dataclass

from app.core.errors import ProcessingError

_QUALITY_RE = re.compile(r"^(\d{3,4})p?$")
_FORMAT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@dataclass(frozen=True)
class StreamCandidate:
    identifier: str
    kind: str
    container: str
    codec: str
    width: int | None = None
    height: int | None = None
    bitrate_kbps: int | None = None
    fps: float | None = None
    filesize_bytes: int | None = None
    label: str | None = None


@dataclass(frozen=True)
class StreamSelection:
    video: StreamCandidate
    audio: StreamCandidate
    quality: str


def parse_quality(quality: str | None) -> tuple[str, int | None]:
    if not quality or quality.lower() == "best":
        return "best", None
    match = _QUALITY_RE.fullmatch(quality.strip().lower())
    if not match:
        raise ProcessingError(f"Unsupported quality value: {quality}")
    height = int(match.group(1))
    if height < 144 or height > 4320:
        raise ProcessingError(f"Unsupported quality value: {quality}")
    return f"{height}p", height


def select_streams(
    candidates: list[StreamCandidate],
    quality: str | None = None,
    *,
    format_id: str | None = None,
    prefer_mp4: bool = True,
) -> StreamSelection:
    videos = [candidate for candidate in candidates if candidate.kind == "video" and candidate.height]
    audios = [candidate for candidate in candidates if candidate.kind == "audio"]
    if not videos:
        raise ProcessingError("No video-only stream is available")
    if not audios:
        raise ProcessingError("No audio-only stream is available")

    if format_id is not None:
        if not _FORMAT_ID_RE.fullmatch(format_id):
            raise ProcessingError("Invalid video format identifier")
        matches = [candidate for candidate in videos if candidate.identifier == format_id]
        if not matches:
            raise ProcessingError("The selected video format is not available")
        video = matches[0]
        normalized = f"{video.height}p" if video.height else "best"
    else:
        normalized, target_height = parse_quality(quality)
        if target_height is not None:
            eligible = [candidate for candidate in videos if candidate.height <= target_height]
            if not eligible:
                raise ProcessingError(f"No video stream is available at or below {normalized}")
            videos = eligible
        video = max(videos, key=lambda item: _video_score(item, prefer_mp4))

    audio = max(audios, key=lambda item: _audio_score(item, prefer_mp4))
    return StreamSelection(video=video, audio=audio, quality=normalized)


def _video_score(candidate: StreamCandidate, prefer_mp4: bool) -> tuple[int, int, int, int, int]:
    height = candidate.height or 0
    return (
        height,
        1 if candidate.codec.lower() in {"h264", "avc1"} else 0,
        1 if prefer_mp4 and candidate.container.lower() == "mp4" else 0,
        int(candidate.fps or 0),
        candidate.bitrate_kbps or 0,
    )


def _audio_score(candidate: StreamCandidate, prefer_mp4: bool) -> tuple[int, int, int]:
    return (
        1 if candidate.codec.lower() in {"aac", "mp4a"} else 0,
        1 if prefer_mp4 and candidate.container.lower() in {"mp4", "m4a"} else 0,
        candidate.bitrate_kbps or 0,
    )
