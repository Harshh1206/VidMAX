import re
from pathlib import Path
from typing import Any

_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/][^\s:]+"),
    re.compile(r"/[^\s:]+\.(?:mp4|m4a|mkv|webm|mov|mp3|wav|aac|ogg)", re.IGNORECASE),
)


def redact_media_paths(message: str, paths: tuple[Path, ...] = ()) -> str:
    redacted = message
    for path in paths:
        redacted = redacted.replace(str(path), "<media>")
    for pattern in _PATH_PATTERNS:
        redacted = pattern.sub("<media>", redacted)
    return redacted[-500:]


class APIError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "Internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details
        if status_code is not None:
            self.status_code = status_code


class InvalidURLError(APIError):
    status_code = 400
    code = "INVALID_URL"
    message = "The URL is not allowed"


class UnsupportedPlatformError(APIError):
    status_code = 400
    code = "UNSUPPORTED_PLATFORM"
    message = "The URL host is not an allowed platform host"


class MetadataUnavailableError(APIError):
    status_code = 503
    code = "METADATA_UNAVAILABLE"
    message = "Metadata inspection is not available for this provider"


class DownloadNotAuthorizedError(APIError):
    status_code = 409
    code = "DOWNLOAD_NOT_AUTHORIZED"
    message = "No authorized download adapter is configured"


class InvalidFormatError(APIError):
    status_code = 400
    code = "INVALID_FORMAT"
    message = "The selected format is not available"


class InvalidJobIDError(APIError):
    status_code = 400
    code = "INVALID_JOB_ID"
    message = "The job identifier is invalid"


class JobNotFoundError(APIError):
    status_code = 404
    code = "JOB_NOT_FOUND"
    message = "The job does not exist"


class JobNotReadyError(APIError):
    status_code = 409
    code = "JOB_NOT_READY"
    message = "The job has no completed file yet"


class JobExpiredError(APIError):
    status_code = 410
    code = "JOB_EXPIRED"
    message = "The job has expired"


class InvalidUploadError(APIError):
    status_code = 400
    code = "INVALID_UPLOAD"
    message = "The upload is invalid"


class FileTooLargeError(APIError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "The uploaded file exceeds the configured limit"


class UnsupportedOperationError(APIError):
    status_code = 400
    code = "UNSUPPORTED_OPERATION"
    message = "The requested processing operation is not supported"


class ProcessingError(APIError):
    status_code = 500
    code = "PROCESSING_FAILED"
    message = "Media processing failed"


class MediaValidationError(ProcessingError):
    message = "Media validation failed"


class MediaToolUnavailableError(ProcessingError):
    message = "A required media tool is not available"


class LocalUploadsDisabledError(APIError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Not found"
