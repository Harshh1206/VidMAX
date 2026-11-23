import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errors import (
    DownloadNotAuthorizedError,
    MediaToolUnavailableError,
    MetadataUnavailableError,
    ProcessingError,
)
from app.core.logging import get_logger
from app.core.urls import URLGuard
from app.processing.streams import StreamCandidate, select_streams

_LOGGER = get_logger(__name__)
DestinationFactory = Callable[[str, str], Path]


@dataclass(frozen=True)
class StreamAcquisitionResult:
    inputs: tuple[Path, Path]
    roles: tuple[str, str]
    cleanup_paths: tuple[Path, ...]


class StreamAcquisitionAdapter(ABC):
    name = "abstract"
    enabled = False

    @abstractmethod
    async def list_candidates(self, url: str) -> list[StreamCandidate]:
        raise NotImplementedError

    async def list_formats(self, url: str) -> list[StreamCandidate]:
        candidates = await self.list_candidates(url)
        return [candidate for candidate in candidates if candidate.kind == "video"]

    @abstractmethod
    async def download_candidate(
        self,
        candidate: StreamCandidate,
        destination: Path,
        *,
        url: str | None = None,
    ) -> Path:
        raise NotImplementedError

    async def acquire(
        self,
        url: str,
        guard: URLGuard,
        allowed_hosts: frozenset[str],
        quality: str | None,
        destination_factory: DestinationFactory,
        *,
        format_id: str | None = None,
    ) -> StreamAcquisitionResult:
        if not self.enabled:
            raise DownloadNotAuthorizedError()
        guard.validate_candidate(url, allowed_hosts)
        selection = select_streams(await self.list_candidates(url), quality, format_id=format_id)
        video_path = await self.download_candidate(
            selection.video,
            destination_factory("video", selection.video.container),
            url=url,
        )
        audio_path = await self.download_candidate(
            selection.audio,
            destination_factory("audio", selection.audio.container),
            url=url,
        )
        _LOGGER.info(
            "Acquired separate media streams",
            extra={
                "adapter": self.name,
                "quality": selection.quality,
                "video_id": selection.video.identifier,
                "audio_id": selection.audio.identifier,
            },
        )
        return StreamAcquisitionResult(
            inputs=(video_path, audio_path),
            roles=("video", "audio"),
            cleanup_paths=(video_path, audio_path),
        )


class PytubefixAcquisitionAdapter(StreamAcquisitionAdapter):
    name = "pytubefix"

    def __init__(
        self,
        *,
        enabled: bool = False,
        download_timeout_seconds: int = 60,
        download_max_retries: int = 2,
    ) -> None:
        self.enabled = enabled
        self.download_timeout_seconds = download_timeout_seconds
        self.download_max_retries = download_max_retries
        self._cache: dict[str, list[Any]] = {}

    async def list_candidates(self, url: str) -> list[StreamCandidate]:
        youtube = await self._youtube(url)
        try:
            adaptive = await asyncio.to_thread(lambda: list(youtube.streams.filter(adaptive=True)))
        except Exception as exc:
            raise MetadataUnavailableError("YouTube stream information is temporarily unavailable") from exc
        candidates: list[StreamCandidate] = []
        for stream in adaptive:
            subtype = _mime_subtype(getattr(stream, "mime_type", ""))
            codec = _stream_codec(stream)
            kind = "video" if str(getattr(stream, "type", "")).startswith("video") else "audio"
            if kind == "video":
                if subtype != "mp4" or codec not in {"h264", "avc1"}:
                    continue
                height = getattr(stream, "height", None)
                if not isinstance(height, int) or height <= 0:
                    continue
                container = "mp4"
                fps = getattr(stream, "fps", None)
                label = f"{height}p H.264"
                if isinstance(fps, (int, float)) and fps:
                    label += f" {fps:g}fps"
            else:
                if subtype not in {"mp4", "m4a"} or codec not in {"mp4a", "aac"}:
                    continue
                container = "m4a"
                label = "AAC audio"

            bitrate = getattr(stream, "bitrate", None)
            bitrate_kbps = round(bitrate / 1000) if isinstance(bitrate, (int, float)) and bitrate else None
            size = getattr(stream, "filesize", None) or getattr(stream, "filesize_approx", None)
            identifier = str(getattr(stream, "itag", "") or "")
            if not identifier:
                continue
            if kind == "audio" and bitrate_kbps:
                label = f"{label} {bitrate_kbps} kbps"
            candidates.append(
                StreamCandidate(
                    identifier=identifier,
                    kind=kind,
                    container=container,
                    codec=codec,
                    width=getattr(stream, "width", None),
                    height=getattr(stream, "height", None),
                    bitrate_kbps=bitrate_kbps,
                    fps=getattr(stream, "fps", None),
                    filesize_bytes=size if isinstance(size, int) and size > 0 else None,
                    label=label,
                )
            )
        self._cache[url] = adaptive
        return candidates

    async def download_candidate(
        self,
        candidate: StreamCandidate,
        destination: Path,
        *,
        url: str | None = None,
    ) -> Path:
        if not self.enabled:
            raise DownloadNotAuthorizedError()
        cached = self._cache.get(url or "")
        stream = next(
            (
                item
                for item in (cached or [])
                if str(getattr(item, "itag", "")) == candidate.identifier
            ),
            None,
        )
        if stream is None:
            raise ProcessingError("The selected stream is no longer available")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = await asyncio.to_thread(
                stream.download,
                output_path=str(destination.parent),
                filename=destination.name,
                skip_existing=False,
                timeout=self.download_timeout_seconds,
                max_retries=self.download_max_retries,
            )
        except Exception as exc:
            raise ProcessingError("YouTube stream download failed") from exc
        path = Path(result) if isinstance(result, str) else destination
        if not path.is_file():
            raise ProcessingError("Stream acquisition did not produce a file")
        return path

    async def _youtube(self, url: str) -> Any:
        if not self.enabled:
            raise DownloadNotAuthorizedError()
        try:
            from pytubefix import YouTube
        except ImportError as exc:
            raise MediaToolUnavailableError("pytubefix is not installed") from exc
        return await asyncio.to_thread(
            YouTube,
            url,
            use_oauth=False,
            allow_oauth_cache=False,
            use_po_token=False,
        )


def _mime_subtype(value: object) -> str:
    return str(value or "").partition(";")[0].split("/", 1)[-1].strip().lower()


def _stream_codec(stream: Any) -> str:
    raw = getattr(stream, "codecs", None)
    if isinstance(raw, (list, tuple)) and raw:
        raw = raw[0]
    return str(raw or "").split(",", 1)[0].split(".", 1)[0].strip().lower()
