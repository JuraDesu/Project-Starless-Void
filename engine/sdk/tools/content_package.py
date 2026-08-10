#!/usr/bin/env python3
"""Validate and create deterministic single-content .wmod archives."""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path, PurePosixPath


class PackageError(ValueError):
    pass


def validate_path(name: str) -> str:
    if "\\" in name or not name or name.startswith("/"):
        raise PackageError(f"unsafe package path: {name!r}")
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in path.parts):
        raise PackageError(f"unsafe package path: {name!r}")
    normalized = path.as_posix()
    if normalized != "client.wasm" and not normalized.startswith("assets/"):
        raise PackageError(f"unsupported package path: {normalized!r}")
    return normalized


def package(source: Path, output: Path) -> None:
    if output.name != "content.wmod":
        raise PackageError("output filename must be content.wmod")
    client = source / "client.wasm"
    if not client.is_file():
        raise PackageError(f"missing content executable: {client}")

    entries: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = validate_path(path.relative_to(source).as_posix())
        if relative in seen:
            raise PackageError(f"duplicate package path: {relative}")
        seen.add(relative)
        entries.append((relative, path))

    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED,
            compresslevel=9) as archive:
        for relative, path in sorted(entries):
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    data = buffer.getvalue()
    if output.is_file() and output.read_bytes() == data:
        return
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(output)


def validate_archive(path: Path) -> None:
    if path.name != "content.wmod":
        raise PackageError("package filename must be content.wmod")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise PackageError("duplicate ZIP paths")
        for name in names:
            validate_path(name)
        if "client.wasm" not in names:
            raise PackageError("missing client.wasm")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    try:
        if args.validate:
            validate_archive(args.validate)
        elif args.source and args.output:
            package(args.source, args.output)
        else:
            parser.error("use --validate ARCHIVE or --source DIR --output ARCHIVE")
    except (OSError, zipfile.BadZipFile, PackageError) as exc:
        print(f"content package error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
