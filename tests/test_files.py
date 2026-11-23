from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.errors import FileTooLargeError, InvalidUploadError
from app.services.files import FileService


def make_upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def make_service(tmp_path: Path, max_bytes: int = 1024) -> FileService:
    service = FileService(tmp_path / "storage", max_bytes)
    service.init_dirs()
    return service


def test_sanitize_filename_blocks_traversal(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    assert service.sanitize_filename("../../evil name.mp4") == "evil_name.mp4"
    assert "/" not in service.sanitize_filename("C:\\temp\\clip.mp4")


def test_sanitize_filename_rejects_unsupported_extension(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    with pytest.raises(InvalidUploadError):
        service.sanitize_filename("payload.exe")


def test_resolve_servable_path_rejects_traversal(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    with pytest.raises(InvalidUploadError):
        service.resolve_servable_path("../secret.txt")
    with pytest.raises(InvalidUploadError):
        service.resolve_servable_path("/etc/passwd")
    with pytest.raises(InvalidUploadError):
        service.resolve_servable_path(None)


def test_resolve_servable_path_allows_contained_paths(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    target = service.output_dir("abc") / "video.mp4"
    assert service.resolve_servable_path(service.relative_path(target)) == target.resolve()


async def test_save_upload_streams_and_deletes(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    upload = make_upload(b"0123456789", "clip.mp4", "video/mp4")
    path, display_name = await service.save_upload("abc", upload)
    assert path.read_bytes() == b"0123456789"
    assert display_name == "clip.mp4"
    assert path.parent == service.upload_dir("abc")

    service.delete_job_files("abc")
    assert not service.job_dir("abc").exists()


async def test_save_upload_enforces_size_limit(tmp_path: Path) -> None:
    service = make_service(tmp_path, max_bytes=4)
    upload = make_upload(b"0123456789", "clip.mp4", "video/mp4")
    with pytest.raises(FileTooLargeError):
        await service.save_upload("abc", upload)
    assert list(service.upload_dir("abc").glob("*")) == []


async def test_save_upload_rejects_empty_and_bad_type(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    empty = make_upload(b"", "clip.mp4", "video/mp4")
    with pytest.raises(InvalidUploadError):
        await service.save_upload("abc", empty)

    bad_type = make_upload(b"data", "clip.mp4", "text/html")
    with pytest.raises(InvalidUploadError):
        await service.save_upload("abc", bad_type)
