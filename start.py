from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
BACKEND_HOST = "127.0.0.1"
FRONTEND_HOST = "127.0.0.1"


def log(message: str) -> None:
    print(f"[VidMax] {message}", flush=True)


def windows_path(path: Path) -> str:
    text = str(path)
    if text.startswith("/mnt/"):
        parts = text.split("/")
        if len(parts) >= 3:
            tail = "\\" + "\\".join(parts[3:]) if len(parts) > 3 else "\\"
            return f"{parts[2].upper()}:{tail}"
    return text


def backend_python() -> Path:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("No Python interpreter found for the backend.")


def npm_command() -> list[str]:
    npm = shutil.which("npm")
    if npm:
        return [npm]

    node = shutil.which("node")
    if node:
        npm_cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if npm_cli.exists():
            return [node, str(npm_cli)]

    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        node_path = program_files / "nodejs" / "node.exe"
        npm_cli_path = program_files / "nodejs" / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if node_path.exists() and npm_cli_path.exists():
            return [str(node_path), str(npm_cli_path)]
    else:
        node_path = Path("/mnt/c/Program Files/nodejs/node.exe")
        npm_cli_path = Path("/mnt/c/Program Files/nodejs/node_modules/npm/bin/npm-cli.js")
        if node_path.exists() and npm_cli_path.exists():
            return [str(node_path), windows_path(npm_cli_path)]

    raise RuntimeError("Node.js and npm were not found. Install Node.js, then run this again.")


def use_windows_network() -> bool:
    return os.name == "posix" and Path("/mnt/c/Windows/System32/curl.exe").exists()


def windows_port_in_use(port: int) -> bool:
    script = (
        "if (Get-NetTCPConnection -LocalPort "
        f"{port} -State Listen -ErrorAction SilentlyContinue) {{ 'yes' }}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "yes" in result.stdout.lower()


def port_in_use(host: str, port: int) -> bool:
    if use_windows_network() and windows_port_in_use(port):
        return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def http_status(url: str) -> int | None:
    if use_windows_network():
        curl = shutil.which("curl.exe")
        if not curl:
            system_curl = Path("/mnt/c/Windows/System32/curl.exe")
            if system_curl.exists():
                curl = str(system_curl)
        if curl:
            try:
                result = subprocess.run(
                    [curl, "-s", "-o", "NUL", "-w", "%{http_code}", url],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                return int(result.stdout.strip().splitlines()[-1])
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                pass
        return None

    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status
    except Exception:
        return None


def wait_for_port(host: str, port: int, process: subprocess.Popen[bytes], label: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"The {label} stopped before it was ready.")
        if port_in_use(host, port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"The {label} did not open port {port} within {timeout} seconds.")


def wait_for_backend(url: str, process: subprocess.Popen[bytes], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"The backend stopped before it was ready with exit code {process.poll()}."
            )
        if http_status(url) == 200:
            return
        time.sleep(0.25)
    raise RuntimeError(f"The backend did not become healthy within {timeout} seconds.")


def process_options() -> dict[str, object]:
    options: dict[str, object] = {}
    if os.name == "posix":
        options["start_new_session"] = True
    else:
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return options


def command_uses_windows(command: list[str]) -> bool:
    text = " ".join(command).lower()
    return os.name == "nt" or ".exe" in text or "/mnt/c/" in text


def windows_process_id(marker: str) -> int | None:
    script = (
        "$p = Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
        "Select-Object -First 1; if ($p) { $p.ProcessId }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = result.stdout.strip().splitlines()
    if not lines:
        return None
    try:
        return int(lines[0].strip())
    except ValueError:
        return None


def kill_windows_tree(pid: int, include_children: bool = True) -> bool:
    taskkill = shutil.which("taskkill")
    if not taskkill and os.name == "posix":
        system_taskkill = Path("/mnt/c/Windows/System32/taskkill.exe")
        if system_taskkill.exists():
            taskkill = str(system_taskkill)
    if not taskkill:
        return False
    command = [taskkill, "/F"]
    if include_children:
        command.append("/T")
    command.extend(["/PID", str(pid)])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def windows_listeners(port: int) -> list[tuple[int, str]]:
    script = f"""
$connections = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue
foreach ($connection in $connections) {{
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)"
    "{{0}}`t{{1}}" -f $connection.OwningProcess, $process.CommandLine
}}
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    listeners: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        pid_text, command_line = line.split("\t", 1)
        try:
            listeners.append((int(pid_text.strip()), command_line.strip()))
        except ValueError:
            continue
    return listeners


def stale_process_matches(label: str, command_line: str) -> bool:
    text = command_line.lower()
    if label == "backend":
        return "uvicorn app.main:app" in text
    frontend_paths = {str(FRONTEND_DIR).lower(), windows_path(FRONTEND_DIR).lower()}
    return "vite" in text and any(path in text for path in frontend_paths)


def clear_stale_port(label: str, port: int) -> None:
    for _ in range(3):
        matches = [
            (pid, command_line)
            for pid, command_line in windows_listeners(port)
            if stale_process_matches(label, command_line)
        ]
        if not matches:
            return
        for pid, _ in matches:
            log(f"Stopping stale {label} process {pid} on port {port}...")
            kill_windows_tree(pid, include_children=False)
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the VidMax backend and frontend together.")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--no-install", action="store_true")
    args = parser.parse_args()

    if not (ROOT / "app" / "main.py").exists():
        raise SystemExit("[VidMax] Backend source was not found.")
    if not (FRONTEND_DIR / "package.json").exists():
        raise SystemExit("[VidMax] Frontend source was not found.")

    for label, port in (("backend", args.backend_port), ("frontend", args.frontend_port)):
        clear_stale_port(label, port)
        if port_in_use(BACKEND_HOST, port):
            raise SystemExit(
                f"[VidMax] Port {port} is still in use. Close the other application and try again."
            )

    children: dict[str, tuple[subprocess.Popen[bytes], list[str], str]] = {}
    stopping = False
    startup_complete = False

    def stop_children() -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for name in reversed(list(children)):
            child, command, marker = children[name]
            if child.poll() is not None:
                continue
            if command_uses_windows(command):
                pid = child.pid if os.name == "nt" else windows_process_id(marker)
                if pid is not None and kill_windows_tree(pid):
                    continue
            if os.name == "posix":
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    child.terminate()
            else:
                child.terminate()
        deadline = time.monotonic() + 5
        for name in reversed(list(children)):
            child = children[name][0]
            try:
                child.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal startup_complete
        if not startup_complete:
            return
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    backend_url = f"http://{BACKEND_HOST}:{args.backend_port}/api/v1/health"
    frontend_url = f"http://{FRONTEND_HOST}:{args.frontend_port}"

    try:
        backend_command = [
            str(backend_python()),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(args.backend_port),
        ]
        backend_marker = (
            f"uvicorn app.main:app --host {BACKEND_HOST} --port {args.backend_port}"
        )
        log("Starting backend...")
        children["backend"] = (
            subprocess.Popen(
                backend_command,
                cwd=str(ROOT),
                **process_options(),
            ),
            backend_command,
            backend_marker,
        )
        wait_for_backend(backend_url, children["backend"][0], timeout=30)
        log(f"Backend ready at http://{BACKEND_HOST}:{args.backend_port}")

        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = ""
        frontend_env["VITE_API_PROXY_TARGET"] = f"http://{BACKEND_HOST}:{args.backend_port}"

        if not args.no_install and not (FRONTEND_DIR / "node_modules").exists():
            log("Installing frontend dependencies...")
            subprocess.check_call(
                npm_command() + ["install"],
                cwd=str(FRONTEND_DIR),
                env=frontend_env,
            )

        frontend_command = npm_command() + [
            "run",
            "dev",
            "--",
            "--host",
            FRONTEND_HOST,
            "--port",
            str(args.frontend_port),
        ]
        frontend_marker = f"vite --host {FRONTEND_HOST} --port {args.frontend_port}"
        log("Starting frontend...")
        children["frontend"] = (
            subprocess.Popen(
                frontend_command,
                cwd=str(FRONTEND_DIR),
                env=frontend_env,
                **process_options(),
            ),
            frontend_command,
            frontend_marker,
        )
        wait_for_port(
            FRONTEND_HOST,
            args.frontend_port,
            children["frontend"][0],
            "frontend",
            timeout=30,
        )
        startup_complete = True
        log(f"VidMax ready at {frontend_url}")
        log("Press Ctrl+C to stop both servers.")

        while True:
            for name, (child, _, _) in children.items():
                exit_code = child.poll()
                if exit_code is not None:
                    raise RuntimeError(f"The {name} stopped with exit code {exit_code}.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("Stopping servers...")
    except Exception as error:
        log(f"Error: {error}")
        raise SystemExit(1) from error
    finally:
        stop_children()


if __name__ == "__main__":
    main()
