#!/usr/bin/env python3
"""Portable build driver for a standalone content project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_EMSDK = "4.0.14"
SETTINGS_NAME = ".engine-tools.json"


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def executable(name: str, environment_name: str) -> Path | None:
    configured = os.environ.get(environment_name)
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path.resolve()
        return None
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def project_settings(project: Path) -> dict[str, str]:
    path = project / SETTINGS_NAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: ignoring invalid {path}: {exc}", file=sys.stderr)
        return {}
    return value if isinstance(value, dict) else {}


def save_project_setting(project: Path, name: str, value: str) -> None:
    path = project / SETTINGS_NAME
    settings = project_settings(project)
    if settings.get(name) == value:
        return
    settings[name] = value
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    os.replace(temporary, path)


def emsdk_root(project: Path) -> Path | None:
    configured = os.environ.get("EMSDK")
    if configured:
        path = Path(configured).expanduser()
        return path.resolve() if path.is_dir() else None
    saved = project_settings(project).get("emsdk")
    if isinstance(saved, str) and saved:
        path = Path(saved).expanduser()
        if path.is_dir():
            return path.resolve()
        print(
            f"warning: saved EMSDK directory no longer exists: {path}",
            file=sys.stderr)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        candidate = Path(local_app_data) / "emsdk" if local_app_data else None
    else:
        data_home = os.environ.get("XDG_DATA_HOME")
        candidate = Path(data_home) / "emsdk" if data_home else Path.home() / ".local" / "share" / "emsdk"
    return candidate.resolve() if candidate and candidate.is_dir() else None


def emscripten_toolchain(root: Path) -> Path:
    return root / "upstream" / "emscripten" / "cmake" / "Modules" / "Platform" / "Emscripten.cmake"


def pinned_emsdk(engine: Path) -> str:
    try:
        value = (engine / "sdk" / "emsdk-version.txt").read_text(encoding="ascii").strip()
    except OSError:
        value = ""
    return value or DEFAULT_EMSDK


def check_emcc(root: Path, expected_version: str) -> str | None:
    candidate = root / "upstream" / "emscripten" / ("emcc.bat" if os.name == "nt" else "emcc")
    if not candidate.is_file():
        return f"Emscripten compiler not found under {root}; run setup_emsdk first"
    try:
        result = subprocess.run(
            [str(candidate), "--version"],
            check=False,
            capture_output=True,
            text=True,
            shell=os.name == "nt",
        )
    except OSError as exc:
        return f"could not run {candidate}: {exc}"
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return f"{candidate} --version failed:\n{output}"
    if expected_version not in output:
        return f"Emscripten {expected_version} is required, but {candidate} reported:\n{output.splitlines()[0]}"
    return None


def run(command: list[str], cwd: Path) -> int:
    print("+", " ".join(f'"{part}"' if " " in part else part for part in command))
    return subprocess.run(command, cwd=cwd, check=False).returncode


def configuration_signature(values: dict[str, str]) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default="client", choices=("client", "codegen"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    project = args.project.resolve()
    if not (project / "CMakeLists.txt").is_file():
        return fail(f"project CMakeLists.txt not found: {project}")

    engine = Path(os.environ.get("ENGINE_DIST", project / "engine")).expanduser().resolve()
    if not (engine / "sdk" / "engine-content-config.cmake").is_file():
        return fail(f"engine SDK not found at {engine}; set ENGINE_DIST or synchronize the engine distribution")
    cmake = executable("cmake", "CMAKE")
    ninja = executable("ninja", "NINJA_PATH")
    if not cmake:
        return fail("CMake was not found; install it or set CMAKE to its executable")
    if not ninja:
        return fail("Ninja was not found; install it or set NINJA_PATH to its executable")
    emsdk = emsdk_root(project)
    if not emsdk:
        if os.name == "nt":
            return fail(
                "Emscripten SDK was not found; run setup_emsdk.bat or set "
                "EMSDK=C:\\path\\to\\emsdk before building")
        return fail(
            "Emscripten SDK was not found; run ./setup_emsdk.sh or export "
            "EMSDK=/path/to/emsdk before building")
    version_error = check_emcc(emsdk, pinned_emsdk(engine))
    if version_error:
        return fail(version_error)
    save_project_setting(project, "emsdk", str(emsdk))
    toolchain = emscripten_toolchain(emsdk)
    if not toolchain.is_file():
        return fail(f"Emscripten CMake toolchain was not found: {toolchain}")

    profile = os.environ.get("BUILD_PROFILE", "Release")
    build = Path(os.environ.get("GAME_BUILD_DIR", project / "build" / profile)).expanduser().resolve()
    output = Path(os.environ.get("GAME_OUTPUT_DIR", project / "out")).expanduser().resolve()
    signature_file = build / ".content_config_signature"
    signature_values = {
        "engine": str(engine), "cmake": str(cmake), "ninja": str(ninja),
        "emsdk": str(emsdk), "toolchain": str(toolchain), "profile": profile,
        "output": str(output), "aseprite": os.environ.get("ASEPRITE", ""),
        "msdf": os.environ.get("MSDF_ATLAS_GEN", ""),
    }
    signature = configuration_signature(signature_values)
    needs_configure = not (build / "build.ninja").is_file() or bool(os.environ.get("RECONFIGURE"))
    if signature_file.is_file() and signature_file.read_text(encoding="ascii").strip() != signature:
        needs_configure = True
    if needs_configure:
        build.mkdir(parents=True, exist_ok=True)
        command = [
            str(cmake), "-S", str(project), "-B", str(build), "-G", "Ninja",
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", f"-DCMAKE_BUILD_TYPE={profile}",
            f"-DCMAKE_MAKE_PROGRAM={ninja}", f"-DENGINE_DIST={engine}",
            f"-DGAME_OUTPUT_DIR={output}", f"-DASEPRITE={os.environ.get('ASEPRITE', '')}",
            f"-DMSDF_ATLAS_GEN={os.environ.get('MSDF_ATLAS_GEN', '')}",
        ]
        result = run(command, project)
        if result:
            return result
        signature_file.write_text(signature + "\n", encoding="ascii")

    target = "game_client" if args.target == "client" else "content_codegen_check"
    return run([str(cmake), "--build", str(build), "--target", target], project)


if __name__ == "__main__":
    raise SystemExit(main())
