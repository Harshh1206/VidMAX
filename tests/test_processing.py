import asyncio
from pathlib import Path

import pytest

from app.core.errors import ProcessingError, UnsupportedOperationError
from app.processing.base import Operation, ProcessingRequest
from app.processing.external import ExternalProviderAdapter
from app.processing.ffmpeg import LocalFFmpegAdapter

ADAPTER = LocalFFmpegAdapter()


def make_request(tmp_path: Path, **overrides) -> ProcessingRequest:
    values = {
        "job_id": "a" * 32,
        "operation": Operation.CONVERT,
        "inputs": (tmp_path / "input.mp4",),
        "output_dir": tmp_path / "output",
        "target_format": "mp4",
        "timeout_seconds": 30,
        "max_output_bytes": 1024,
    }
    values.update(overrides)
    return ProcessingRequest(**values)


def test_convert_command_is_argv_based(tmp_path: Path) -> None:
    request = make_request(tmp_path, max_duration_seconds=60)
    command = ADAPTER.build_convert_command(request)
    assert command[0] == "ffmpeg"
    assert "-nostdin" in command
    assert "-i" in command
    assert "libx264" in command
    assert "-t" in command
    assert "60" in command
    assert command[-1].endswith("mp4")


def test_merge_command_uses_concat_demuxer(tmp_path: Path) -> None:
    request = make_request(
        tmp_path,
        operation=Operation.MERGE,
        inputs=(tmp_path / "a.mp4", tmp_path / "b.mp4"),
    )
    command = ADAPTER.build_merge_command(request)
    assert "-f" in command
    assert "concat" in command
    assert "-safe" in command
    assert "0" in command


def test_unsupported_format_and_input_count(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedOperationError):
        ADAPTER.build_convert_command(make_request(tmp_path, target_format="exe"))
    with pytest.raises(UnsupportedOperationError):
        ADAPTER.build_merge_command(make_request(tmp_path, operation=Operation.MERGE))


class FakeProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"", *, delay: float = 0) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.delay = delay
        self.killed = False

    async def communicate(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        return b"", self.stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.returncode = -9
        return self.returncode


async def test_process_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = make_request(tmp_path)
    request.inputs[0].write_bytes(b"input")

    async def fake_exec(*args, **kwargs):
        output = Path(args[-1])

        class Process(FakeProcess):
            async def communicate(self):
                output.write_bytes(b"output")
                return b"", b""

        return Process()

    monkeypatch.setattr("app.processing.ffmpeg.asyncio.create_subprocess_exec", fake_exec)
    result = await ADAPTER.process(request)
    assert result.bytes_written == 6
    assert result.output_name.endswith("mp4")


async def test_process_timeout_kills_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = make_request(tmp_path, timeout_seconds=1)
    request.inputs[0].write_bytes(b"input")
    process = FakeProcess(delay=5)
    async def fake_exec(*args, **kwargs):
        return process

    monkeypatch.setattr("app.processing.ffmpeg.asyncio.create_subprocess_exec", fake_exec)
    with pytest.raises(ProcessingError, match="timed out"):
        await ADAPTER.process(request)
    assert process.killed is True


async def test_process_failure_reports_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = make_request(tmp_path)
    request.inputs[0].write_bytes(b"input")
    async def fake_exec(*args, **kwargs):
        return FakeProcess(returncode=1, stderr=b"bad input")

    monkeypatch.setattr("app.processing.ffmpeg.asyncio.create_subprocess_exec", fake_exec)
    with pytest.raises(ProcessingError, match="bad input"):
        await ADAPTER.process(request)


async def test_process_enforces_output_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = make_request(tmp_path, max_output_bytes=2)
    request.inputs[0].write_bytes(b"input")

    async def fake_exec(*args, **kwargs):
        output = Path(args[-1])

        class Process(FakeProcess):
            async def communicate(self):
                output.write_bytes(b"large output")
                return b"", b""

        return Process()

    monkeypatch.setattr("app.processing.ffmpeg.asyncio.create_subprocess_exec", fake_exec)
    with pytest.raises(ProcessingError, match="size limit"):
        await ADAPTER.process(request)
    assert not (request.output_dir / f"{request.job_id}.mp4").exists()


async def test_process_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(ProcessingError, match="missing"):
        await ADAPTER.process(make_request(tmp_path))


def test_external_adapter_is_contract_only() -> None:
    with pytest.raises(TypeError):
        ExternalProviderAdapter()
