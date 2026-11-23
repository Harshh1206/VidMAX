from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Operation(StrEnum):
    CONVERT = "convert"
    MERGE = "merge"
    AV_MERGE = "merge_av"


@dataclass(frozen=True)
class ProcessingRequest:
    job_id: str
    operation: Operation
    inputs: tuple[Path, ...]
    output_dir: Path
    target_format: str
    timeout_seconds: int
    max_output_bytes: int
    max_duration_seconds: int | None = None
    quality: str | None = None
    expect_audio: bool = True
    expect_video: bool = True
    video_codec: str = "copy"
    audio_codec: str = "copy"
    allow_reencode: bool = True


@dataclass(frozen=True)
class ProcessingResult:
    output_path: Path
    output_name: str
    bytes_written: int


class ProcessingAdapter(ABC):
    name: str
    supported_operations: frozenset[Operation] = frozenset()

    def supports(self, operation: Operation) -> bool:
        return operation in self.supported_operations

    @abstractmethod
    async def process(self, request: ProcessingRequest) -> ProcessingResult:
        raise NotImplementedError
