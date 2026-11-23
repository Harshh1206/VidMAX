from pydantic import BaseModel, Field

from app.processing.streams import StreamCandidate
from app.providers.base import CapabilityStatus, Platform


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class VideoFormatResponse(BaseModel):
    id: str
    label: str
    kind: str
    container: str
    codec: str
    width: int | None = None
    height: int | None = None
    bitrate_kbps: int | None = None
    fps: float | None = None
    filesize_bytes: int | None = None

    @classmethod
    def from_candidate(cls, candidate: StreamCandidate) -> "VideoFormatResponse":
        return cls(
            id=candidate.identifier,
            label=candidate.label or (f"{candidate.height}p" if candidate.height else candidate.identifier),
            kind=candidate.kind,
            container=candidate.container,
            codec=candidate.codec,
            width=candidate.width,
            height=candidate.height,
            bitrate_kbps=candidate.bitrate_kbps,
            fps=candidate.fps,
            filesize_bytes=candidate.filesize_bytes,
        )


class InspectResponse(BaseModel):
    platform: Platform
    canonical_url: str
    video_id: str | None
    title: str | None
    author: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    metadata_source: str
    metadata_available: bool
    downloadable: bool = False
    download_capability_status: CapabilityStatus
    download_capability_reason: str
    formats: list[VideoFormatResponse] = Field(default_factory=list)
    recommended_format_id: str | None = None
