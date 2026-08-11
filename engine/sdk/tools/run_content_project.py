#!/usr/bin/env python3
"""Serve a standalone content deployment with ownership-aware PID tracking."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import webbrowser


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def process_command_line(pid: int) -> str:
    if os.name != "nt":
        path = Path(f"/proc/{pid}/cmdline")
        try:
            return path.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            return ""
    command = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' "
        "-ErrorAction SilentlyContinue; if($p){$p.CommandLine}"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def stop_process(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)


def port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            pass
        return True
    except OSError:
        return False


def listening_process_ids(port: int) -> list[int]:
    if os.name == "nt":
        command = (
            "Get-NetTCPConnection -State Listen -LocalPort "
            f"{port} -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, check=False)
        return sorted({int(value) for value in result.stdout.split() if value.isdigit()})
    try:
        result = subprocess.run(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, check=False)
    except OSError:
        # `lsof` is conventional on Linux, but is not installed on every
        # minimal distribution.  In that case retain the conservative
        # behaviour: never claim an unknown listener is ours.
        return []
    return sorted({int(value) for value in result.stdout.split() if value.isdigit()})


def owned_server(pid: int, server: Path, output: Path) -> bool:
    command_line = process_command_line(pid).lower().replace("/", "\\")
    server_text = str(server).lower().replace("/", "\\")
    output_text = str(output).lower().replace("/", "\\")
    return server_text in command_line and output_text in command_line


def wait_for_port_closed(port: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not port_listening(port):
            return True
        time.sleep(0.05)
    return not port_listening(port)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=1111)
    args = parser.parse_args()
    project = args.project.resolve()
    engine = Path(os.environ.get("ENGINE_DIST", project / "engine")).expanduser().resolve()
    output = Path(os.environ.get("GAME_OUTPUT_DIR", project / "out")).expanduser().resolve()
    server = engine / "sdk" / "tools" / "static_http_server.py"
    if not server.is_file():
        return fail(f"HTTP server helper not found: {server}")
    if not (output / "index.html").is_file():
        return fail(f"game deployment not found: {output}; run the build first")
    build = project / "build"
    build.mkdir(parents=True, exist_ok=True)
    pid_file = build / "http_server.pid"

    if pid_file.is_file():
        try:
            old_pid = int(pid_file.read_text(encoding="ascii").strip())
        except ValueError:
            old_pid = 0
        if old_pid and owned_server(old_pid, server, output):
            print(f"Stopping previous HTTP server PID {old_pid}...")
            stop_process(old_pid)
        elif old_pid:
            print(f"Ignoring stale PID {old_pid}; it does not belong to this project.")
        pid_file.unlink(missing_ok=True)

    if port_listening(args.port):
        listeners = listening_process_ids(args.port)
        owned_listeners = [
            pid for pid in listeners if owned_server(pid, server, output)]
        if owned_listeners:
            for pid in owned_listeners:
                print(f"Stopping recovered HTTP server PID {pid}...")
                stop_process(pid)
            if not wait_for_port_closed(args.port):
                return fail(f"previous project HTTP server did not release port {args.port}")
        else:
            return fail(f"port {args.port} is already owned by an unrelated process")

    log = build / "http_server.log"
    with log.open("ab") as stream:
        process = subprocess.Popen(
            [sys.executable, str(server), "--root", str(output), "--port", str(args.port), "--serverless"],
            cwd=project,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="ascii")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if port_listening(args.port):
            url = f"http://localhost:{args.port}/"
            print(f"HTTP server running at {url} (PID {process.pid})")
            if not webbrowser.open(url):
                print(f"Open {url} in a browser.")
            return 0
        if process.poll() is not None:
            pid_file.unlink(missing_ok=True)
            return fail(f"HTTP server exited with code {process.returncode}; see {log}")
        time.sleep(0.1)
    stop_process(process.pid)
    pid_file.unlink(missing_ok=True)
    return fail(f"HTTP server did not bind port {args.port}; see {log}")


if __name__ == "__main__":
    raise SystemExit(main())
