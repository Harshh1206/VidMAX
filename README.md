# VidMax

Self-hosted, YTMP4-inspired video application with a modular FastAPI backend and a React/Vite frontend.

## Architecture

- `app/api` — HTTP endpoints and Pydantic response models.
- `app/providers` — platform abstraction, registry, YouTube/Facebook isolation, capability reporting.
- `app/processing` — stream selection, FFmpeg adapter, FFprobe validation, temporary media safety, replaceable external contract.
- `app/services` — inspection, authorized acquisition pipeline, job lifecycle, file management, optional upload pipeline, expiry cleanup.
- `app/db` — SQLAlchemy 2.x models, engine/session, SQLite setup.
- `app/core` — URL guard, allowlist/SSRF and redirect validation, identifiers, errors.

## Request flow

1. `POST /api/v1/inspect` validates the URL against strict hostname and SSRF rules, resolves the provider, calls metadata inspection, and returns real format options when the YouTube download adapter is enabled.
2. `POST /api/v1/downloads` validates explicit user confirmation separately. It never creates a job unless a provider reports an authorized download adapter as `available`; disabled providers return `409 DOWNLOAD_NOT_AUTHORIZED`.
3. `POST /api/v1/uploads` is optional and disabled by default. When enabled, it accepts media the caller owns or is authorized to process, creates a local job, and runs the local FFmpeg adapter in a background task. `operation=merge_av` accepts exactly two inputs with `stream_roles=video,audio`, prefers stream copying, re-encodes only incompatible codecs, writes MP4 with fast-start, and validates the result with FFprobe.
4. `GET /api/v1/downloads/{job_id}` polls status/progress. Internal filesystem paths are never returned.
5. `GET /api/v1/downloads/{job_id}/file` serves only completed files resolved inside the storage root.
6. `DELETE /api/v1/downloads/{job_id}` deletes the job and its files. Expired jobs are swept on startup and checked lazily.

## Capability and readiness reporting

`GET /api/v1/health` reports three independent capabilities per provider:

- `url_validation` — exact hostname allowlist and platform identification.
- `metadata_inspection` — documented oEmbed client status; YouTube is configured but unverified, Facebook requires an access token.
- `authorized_download` — YouTube is `available` when `VIDMAX_ENABLE_YOUTUBE_PYTUBEFIX_DOWNLOAD=true`; Facebook remains `not_implemented`.

`fully_functional` is `true` only when all three capabilities are `available`. YouTube metadata is currently `configured_unverified`, so `fully_functional` remains `false` even when downloads are enabled; the API never presents a provider as fully functional without verification.

## API endpoints

- `GET /api/v1/health`
- `POST /api/v1/inspect`
- `POST /api/v1/downloads`
- `GET /api/v1/downloads/{job_id}`
- `GET /api/v1/downloads/{job_id}/file`
- `DELETE /api/v1/downloads/{job_id}`
- `POST /api/v1/uploads` (optional, `VIDMAX_ENABLE_LOCAL_UPLOADS=true`)

Errors use `{"error": {"code", "message", "details"}}`.

## Security controls

- HTTPS-only URLs, exact hostname allowlists, no credentials, no explicit ports, no IP literals or reserved/local hosts.
- Redirect validation re-checks every hop against the same allowlist.
- Random UUID4 job IDs, storage-contained path resolution, sanitized filenames.
- Upload size limits, processing timeout, output-size limits, argv-based FFmpeg execution without a shell.
- FFprobe validation of container, duration, stream presence, codecs, and file size; internal paths are redacted from stored errors.
- Job-scoped temporary directories are removed after success or failure; partial outputs are deleted on failed processing.
- Environment-driven configuration and no hardcoded credentials.
- No undocumented platform endpoints, no DRM circumvention, no auth bypass, no unauthorized extraction.

## Honest capability status

- YouTube/Facebook URL validation and provider isolation: implemented.
- Metadata inspection scaffolding: implemented against documented oEmbed endpoints using injectable clients; not verified against the live services.
- Authorized YouTube downloads: implemented through Pytubefix when explicitly enabled and confirmed by the user; Facebook downloads are **not implemented**.
- `pytubefix` is a pinned dependency behind a disabled-by-default adapter (`VIDMAX_ENABLE_YOUTUBE_PYTUBEFIX_DOWNLOAD=false`). No auth bypass, PO-token generator, undocumented endpoint, or DRM circumvention is used.
- External processing providers: abstract contract only; no external API has been invented.
- Local FFmpeg conversion/merge: implemented, optional, isolated, and requires FFmpeg/FFprobe installed at runtime.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..
cp .env.example .env
```

Enable authorized YouTube downloads in `.env`:

```bash
VIDMAX_ENABLE_YOUTUBE_PYTUBEFIX_DOWNLOAD=true
```

On this Windows/WSL environment the working commands were:

```bash
"/mnt/c/Users/Lenovo/AppData/Local/Programs/Python/Python312/python.exe" -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m pytest -q
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Run the frontend in a second terminal:

```bash
cd frontend && npm run dev
```

Enable optional local uploads:

```bash
VIDMAX_ENABLE_LOCAL_UPLOADS=true uvicorn app.main:app --reload
```

FFmpeg and FFprobe are required for real processing, including authorized downloads:

```bash
ffmpeg -version
ffprobe -version
```

Optional runtime overrides:

```bash
VIDMAX_FFMPEG_PATH=/path/to/ffmpeg
VIDMAX_FFPROBE_PATH=/path/to/ffprobe
VIDMAX_MEDIA_MIN_BYTES=1024
VIDMAX_FFPROBE_TIMEOUT_SECONDS=30
VIDMAX_DURATION_TOLERANCE_SECONDS=2.0
```

`static-ffmpeg` is a development-only dependency used by the real media tests when system binaries are unavailable. It is not imported by application runtime code.
