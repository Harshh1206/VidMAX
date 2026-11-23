import re
import uuid
from pathlib import Path

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_job_id() -> str:
    return uuid.uuid4().hex


def new_storage_name(suffix: str) -> str:
    clean = suffix.lstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9]{1,8}", clean):
        clean = "bin"
    return f"{uuid.uuid4().hex}.{clean}"


def is_valid_job_id(value: str) -> bool:
    return bool(JOB_ID_RE.fullmatch(value))


def safe_relative_path(root: Path, candidate: Path) -> str:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    return resolved_candidate.relative_to(resolved_root).as_posix()
