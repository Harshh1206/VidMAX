import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.errors import FileTooLargeError, InvalidUploadError
from app.core.ids import new_storage_name


class FileService:
    def __init__(
        self,
        root: Path,
        max_upload_bytes: int,
        allowed_extensions: frozenset[str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max_upload_bytes
        self.allowed_extensions = allowed_extensions or frozenset(
            {"mp4", "mkv", "webm", "mov", "mp3", "m4a", "wav", "aac", "ogg"}
        )

    def init_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self._contained(self.root / "jobs" / job_id)

    def upload_dir(self, job_id: str) -> Path:
        return self._contained(self.job_dir(job_id) / "uploads")

    def output_dir(self, job_id: str) -> Path:
        return self._contained(self.job_dir(job_id) / "output")

    def temp_dir(self, job_id: str) -> Path:
        return self._contained(self.job_dir(job_id) / "tmp")

    def new_temp_path(self, job_id: str, suffix: str) -> Path:
        directory = self.temp_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        clean_suffix = re.sub(r"[^a-z0-9]+", "", suffix.lower())[:8] or "bin"
        return self._contained(directory / new_storage_name(clean_suffix))

    def clean_temp(self, job_id: str) -> None:
        directory = self.temp_dir(job_id)
        if directory.exists():
            shutil.rmtree(directory)

    def sanitize_filename(self, filename: str, *, require_allowed: bool = True) -> str:
        name = Path(filename or "").name
        suffix = Path(name).suffix.lower().lstrip(".")
        if require_allowed and suffix not in self.allowed_extensions:
            raise InvalidUploadError(f"Unsupported file extension: {suffix or 'none'}")
        stem = name.rsplit(".", 1)[0] if "." in name else name
        clean_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")[:80] or "upload"
        clean_suffix = re.sub(r"[^a-z0-9]+", "", suffix)[:8] or "bin"
        return f"{clean_stem}.{clean_suffix}"

    def validate_content_type(self, content_type: str | None) -> None:
        if not content_type:
            return
        if not content_type.startswith(("video/", "audio/", "application/octet-stream")):
            raise InvalidUploadError(f"Unsupported content type: {content_type}")

    async def save_upload(self, job_id: str, upload: UploadFile) -> tuple[Path, str]:
        display_name = self.sanitize_filename(upload.filename or "")
        self.validate_content_type(upload.content_type)
        suffix = Path(display_name).suffix.lstrip(".").lower()
        directory = self.upload_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / new_storage_name(suffix)
        total = 0
        with destination.open("xb") as handle:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_upload_bytes:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise FileTooLargeError()
                handle.write(chunk)
        if total == 0:
            destination.unlink(missing_ok=True)
            raise InvalidUploadError("Uploaded files must not be empty")
        return destination, display_name

    def write_manifest(self, job_id: str, manifest: dict[str, Any]) -> None:
        directory = self.job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_text(
            json.dumps(manifest, separators=(",", ":")),
            encoding="utf-8",
        )

    def read_manifest(self, job_id: str) -> dict[str, Any]:
        path = self._contained(self.job_dir(job_id) / "manifest.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InvalidUploadError("Job manifest is missing or invalid") from exc
        if not isinstance(payload, dict):
            raise InvalidUploadError("Job manifest is invalid")
        return payload

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def resolve_servable_path(self, relative_path: str | None) -> Path:
        if not relative_path or Path(relative_path).is_absolute():
            raise InvalidUploadError("The stored file reference is invalid")
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise InvalidUploadError("The stored file reference escapes storage")
        return candidate

    def delete_job_files(self, job_id: str) -> None:
        directory = self.job_dir(job_id)
        if directory.exists():
            shutil.rmtree(directory)

    def _contained(self, candidate: Path) -> Path:
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise InvalidUploadError("Path escapes storage root")
        return resolved
