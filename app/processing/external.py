from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from app.processing.base import ProcessingRequest, ProcessingResult


class ExternalJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExternalJobSnapshot:
    reference: str
    status: ExternalJobStatus
    error_message: str | None = None


class ExternalProviderAdapter(ABC):
    name: str

    @abstractmethod
    async def submit(self, request: ProcessingRequest) -> str:
        raise NotImplementedError

    @abstractmethod
    async def poll(self, reference: str) -> ExternalJobSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, reference: str, request: ProcessingRequest) -> ProcessingResult:
        raise NotImplementedError
