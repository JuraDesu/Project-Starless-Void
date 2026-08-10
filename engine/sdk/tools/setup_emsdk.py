#!/usr/bin/env python3
"""Install and activate the Emscripten release required by the content SDK."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_VERSION = "4.0.14"
REPOSITORY = "https://github.com/emscripten-core/emsdk.git"


def pinned_version() -> str:
    metadata = Path(__file__).resolve().parents[1] / "emsdk-version.txt"
    try:
        value = metadata.read_text(encoding="ascii").strip()
    except OSError:
        value = ""
    return value or DEFAULT_VERSION


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def command(name: str) -> str | None:
    return shutil.which(name)


def run(args: list[str], cwd: Path | None = None) -> int:
    print("+", " ".join(args))
    return subprocess.run(args, cwd=cwd, check=False).returncode


def default_directory() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        return (Path(root) if root else Path.home() / "AppData" / "Local") / "emsdk"
    root = os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / "emsdk"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    version = pinned_version()
    if not command("git"):
        return fail("Git is required to install emsdk; install Git and rerun this script")
    destination = (args.directory or Path(os.environ.get("EMSDK", default_directory()))).expanduser().resolve()
    emsdk_script = destination / ("emsdk.bat" if os.name == "nt" else "emsdk")

    needs_clone = not destination.exists()
    if destination.exists():
        if not destination.is_dir() or not (destination / ".git").exists() or not emsdk_script.is_file():
            try:
                nonempty = any(destination.iterdir())
            except OSError:
                nonempty = True
            if nonempty:
                return fail(f"refusing to use unrelated non-empty directory: {destination}")
            needs_clone = True
    if needs_clone:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = run(["git", "clone", "--depth", "1", REPOSITORY, str(destination)])
        if result:
            return result

    for args_list in ([str(emsdk_script), "install", version], [str(emsdk_script), "activate", version]):
        result = run(args_list, destination)
        if result:
            return fail(f"emsdk command failed with exit code {result}")

    compiler = destination / "upstream" / "emscripten" / ("emcc.bat" if os.name == "nt" else "emcc")
    if not compiler.is_file():
        return fail(f"emsdk activated but emcc was not found under {destination}")
    result = subprocess.run([str(compiler), "--version"], capture_output=True, text=True, check=False, shell=os.name == "nt")
    output = (result.stdout + result.stderr).strip()
    if result.returncode or version not in output:
        return fail(f"expected Emscripten {version}, but emcc reported:\n{output}")
    print(f"Emscripten {version} is ready at {destination}")
    print(f"Set EMSDK={destination} before running the build wrapper.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
