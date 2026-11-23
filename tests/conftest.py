import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.urls import URLGuard
from app.main import create_app
from app.processing.base import Operation, ProcessingAdapter, ProcessingRequest, ProcessingResult
from app.providers.acquisition import PytubefixAcquisitionAdapter
from app.providers.facebook import FacebookProvider, facebook_capabilities
from app.providers.metadata import NoopInspector
from app.providers.registry import ProviderRegistry
from app.providers.youtube import YouTubeProvider, youtube_capabilities


class FakeInspector:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "title": "Sample title",
            "author_name": "Sample author",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        }

    async def fetch(self, normalized: Any) -> dict[str, Any]:
        return self.payload


class FakeProcessingAdapter(ProcessingAdapter):
    name = "fake_processor"
    supported_operations = frozenset({Operation.CONVERT, Operation.MERGE, Operation.AV_MERGE})
    allowed_formats = frozenset({"mp4", "mp3"})
    max_inputs = 8

    async def process(self, request: ProcessingRequest) -> ProcessingResult:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        output = request.output_dir / f"{request.job_id}.{request.target_format}"
        output.write_bytes(b"processed-media")
        return ProcessingResult(
            output_path=output,
            output_name=output.name,
            bytes_written=output.stat().st_size,
        )


@pytest.fixture
def make_settings(tmp_path: Path):
    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "database_url": f"sqlite:///{tmp_path / 'vidmax-test.db'}",
            "storage_dir": tmp_path / "storage",
            "enable_local_uploads": True,
            "enable_metadata_inspection": True,
            "enable_facebook_metadata": True,
            "facebook_access_token": None,
            "max_upload_bytes": 1024 * 1024,
            "max_output_bytes": 1024 * 1024,
        }
        values.update(overrides)
        return Settings(**values)

    return factory


@pytest.fixture
def guard() -> URLGuard:
    return URLGuard()


@pytest.fixture
def make_registry(guard: URLGuard):
    def factory(
        *,
        facebook_token: bool = True,
        youtube_download: bool = False,
        youtube_acquisition: PytubefixAcquisitionAdapter | None = None,
    ) -> ProviderRegistry:
        acquisition = youtube_acquisition or PytubefixAcquisitionAdapter(enabled=youtube_download)
        youtube = YouTubeProvider(
            guard,
            FakeInspector(),
            youtube_capabilities(
                metadata_enabled=True,
                acquisition_enabled=youtube_download,
            ),
            acquisition=acquisition if youtube_download or youtube_acquisition else None,
        )
        facebook_inspector = (
            FakeInspector()
            if facebook_token
            else NoopInspector("Facebook metadata inspection is not configured")
        )
        facebook = FacebookProvider(
            guard,
            facebook_inspector,
            facebook_capabilities(metadata_enabled=True, oauth_configured=facebook_token),
        )
        return ProviderRegistry(guard, [youtube, facebook])

    return factory


@pytest.fixture
def make_app(make_settings, make_registry):
    def factory(**overrides: Any):
        registry = overrides.pop("registry", make_registry())
        processor = overrides.pop("processor", FakeProcessingAdapter())
        settings = make_settings(**overrides)
        return create_app(settings, registry=registry, processor=processor)

    return factory


@pytest.fixture
def media_tools():
    ffmpeg = os.environ.get("VIDMAX_TEST_FFMPEG") or shutil.which("ffmpeg")
    ffprobe = os.environ.get("VIDMAX_TEST_FFPROBE") or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        try:
            import static_ffmpeg

            static_ffmpeg.add_paths()
            ffmpeg = ffmpeg or shutil.which("ffmpeg")
            ffprobe = ffprobe or shutil.which("ffprobe")
        except ImportError:
            pass
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and FFprobe are required for real media tests")
    return ffmpeg, ffprobe


@pytest.fixture
def make_real_app(make_settings, make_registry, media_tools):
    ffmpeg, ffprobe = media_tools

    def factory(**overrides: Any):
        settings_values = {
            "ffmpeg_path": ffmpeg,
            "ffprobe_path": ffprobe,
            "media_min_bytes": 128,
            "max_output_bytes": 16 * 1024 * 1024,
            "processing_timeout_seconds": 60,
            "ffprobe_timeout_seconds": 30,
        }
        settings_values.update(overrides)
        return create_app(make_settings(**settings_values), registry=make_registry())

    return factory


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
