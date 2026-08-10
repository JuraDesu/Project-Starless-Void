#!/usr/bin/env python3
"""Synchronize the engine content SDK without disturbing unchanged files."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _copy_if_changed(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and source.read_bytes() == destination.read_bytes():
        return
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
        suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(source.read_bytes())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)


def _prune(destination: Path, expected: set[Path]) -> None:
    for path in sorted((p for p in destination.rglob("*") if p.is_file()), reverse=True):
        if path.relative_to(destination) not in expected:
            path.unlink()
    for path in sorted((p for p in destination.rglob("*") if p.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sdk", type=Path, required=True)
    parser.add_argument("--source-glm", type=Path, required=True)
    parser.add_argument("--engine-cmake", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--stamp", type=Path, required=True)
    args = parser.parse_args()

    if not args.source_sdk.is_dir() or not args.source_glm.is_dir():
        raise SystemExit("engine SDK source directories are missing")

    sources: dict[Path, Path] = {}
    for source in _files(args.source_sdk):
        sources[Path("include") / source.relative_to(args.source_sdk)] = source
    for source in _files(args.source_glm):
        sources[Path("include/glm") / source.relative_to(args.source_glm)] = source
    sources[Path("cmake/EngineContent.cmake")] = args.engine_cmake
    sources[Path("engine-content-config.cmake")] = args.config
    for name in args.tool:
        sources[Path("tools") / name] = args.tools_root / name

    for relative, source in sources.items():
        if not source.is_file():
            raise SystemExit(f"missing SDK export input: {source}")

    args.destination.mkdir(parents=True, exist_ok=True)
    expected = set(sources)
    _prune(args.destination, expected)
    for relative, source in sources.items():
        _copy_if_changed(source, args.destination / relative)

    args.stamp.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=args.stamp.parent, prefix=f".{args.stamp.name}.",
        suffix=".tmp", delete=False, encoding="utf-8"
    ) as temporary:
        temporary.write("engine SDK synchronized\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, args.stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
