from app.config import Settings


def test_youtube_download_settings_map_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("VIDMAX_ENABLE_YOUTUBE_PYTUBEFIX_DOWNLOAD", "true")
    monkeypatch.setenv("VIDMAX_YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("VIDMAX_YOUTUBE_DOWNLOAD_MAX_RETRIES", "1")

    settings = Settings()

    assert settings.enable_youtube_pytubefix_download is True
    assert settings.youtube_download_timeout_seconds == 45
    assert settings.youtube_download_max_retries == 1
