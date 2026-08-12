"""Stage explicitly declared atlas and font assets for a content module."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


class AssetError(ValueError):
    pass


ASSET_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def tool_identity(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve().as_posix()}:{stat.st_size}:{stat.st_mtime_ns}"


PREPARED_REVISION = "prepared-assets-v2"
ATLAS_EXPORT_LAYER = "main"


def source_identity(path: Path) -> str:
    return f"{path.resolve().as_posix()}:{digest_file(path)}"


def write_if_changed(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return False
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    return True


def write_json_if_changed(path: Path, value: object) -> bool:
    return write_if_changed(
        path,
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def copy_if_changed(source: Path, target: Path) -> bool:
    return write_if_changed(target, source.read_bytes())


def prepared_fingerprint(kind: str, source: Path, **settings: object) -> dict:
    return {
        "kind": kind,
        "revision": PREPARED_REVISION,
        "source_sha256": digest_file(source),
        **settings,
    }


def prepared_metadata(document: dict) -> dict | None:
    value = document.get("_content_prepared")
    return value if isinstance(value, dict) else None


def load_font_codegen() -> object:
    path = Path(__file__).with_name("font_codegen.py")
    spec = importlib.util.spec_from_file_location("content_font_codegen", path)
    if spec is None or spec.loader is None:
        raise AssetError(f"unable to load font generator {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prune_directory(directory: Path, keep: set[str]) -> None:
    if not directory.exists():
        return
    for path in directory.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()


def safe_relative(value: str, source: Path) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise AssetError(f"{source}: unsafe asset path {value!r}")
    return path.as_posix()


def calls(text: str, name: str, source: Path) -> list[list[str]]:
    clean = re.sub(r"//[^\n]*|/\*.*?\*/", " ", text, flags=re.S)
    result: list[list[str]] = []
    pattern = re.compile(rf"\bassets\s*\.\s*{name}\s*\(")
    for match in pattern.finditer(clean):
        start = match.end(); depth = 1; i = start; quote = False
        while i < len(clean) and depth:
            char = clean[i]
            if char == '"' and (i == 0 or clean[i - 1] != "\\"):
                quote = not quote
            elif not quote:
                if char == "(": depth += 1
                elif char == ")": depth -= 1
            i += 1
        if depth:
            raise AssetError(f"{source}: unterminated assets.{name} call")
        body = clean[start:i - 1]
        args: list[str] = []
        token = []
        quote = False
        for char in body + ",":
            if char == '"' and (not token or token[-1] != "\\"):
                quote = not quote
            if char == "," and not quote:
                value = "".join(token).strip()
                if not value:
                    raise AssetError(f"{source}: empty assets.{name} argument")
                args.append(value); token = []
            else:
                token.append(char)
        result.append(args)
    return result


def literal(value: str, source: Path) -> str:
    if not (len(value) >= 2 and value[0] == '"' and value[-1] == '"'):
        raise AssetError(f"{source}: build-time asset arguments must be string literals")
    return bytes(value[1:-1], "utf-8").decode("unicode_escape")


def integer(value: str, source: Path, label: str) -> int:
    try:
        return int(value.rstrip("uU"), 10)
    except ValueError as exc:
        raise AssetError(f"{source}: {label} must be an integer literal") from exc


def scan(root: Path) -> dict:
    source = root / "content" / "assets.h"
    if not source.is_file():
        raise AssetError(f"missing central asset file: {source}")
    text = source.read_text(encoding="utf-8")
    atlases = []
    seen = set()
    for args in calls(text, "atlas", source):
        if len(args) not in (2, 4):
            raise AssetError(f"{source}: assets.atlas expects 2 or 4 arguments")
        name = literal(args[0], source)
        aseprite = safe_relative(literal(args[1], source), source)
        if not ASSET_NAME.fullmatch(name):
            raise AssetError(f"{source}: invalid atlas name {name!r}")
        if Path(aseprite).suffix.lower() != ".aseprite":
            raise AssetError(
                f"{source}: atlas {name} source must be an .aseprite file")
        if name in seen:
            raise AssetError(f"{source}: duplicate atlas {name}")
        seen.add(name)
        filter_name = "nearest" if len(args) == 2 else args[2].lower().replace("filter_", "")
        address_name = "clamp" if len(args) == 2 else args[3].lower().replace("address_", "")
        if filter_name not in {"nearest", "linear"} or address_name not in {"clamp", "repeat"}:
            raise AssetError(f"{source}: invalid atlas sampler settings")
        if not (root / aseprite).is_file():
            raise AssetError(f"{source}: atlas source file is missing for {name}")
        atlases.append({"name": name, "source": aseprite,
                        "filter": filter_name, "address": address_name})
    fonts = []
    for args in calls(text, "font", source):
        if len(args) not in (2, 4):
            raise AssetError(f"{source}: assets.font expects 2 or 4 arguments")
        name = literal(args[0], source)
        path = safe_relative(literal(args[1], source), source)
        if not ASSET_NAME.fullmatch(name):
            raise AssetError(f"{source}: invalid font name {name!r}")
        if name in {item["name"] for item in fonts}:
            raise AssetError(f"{source}: duplicate font {name}")
        size = 32 if len(args) == 2 else integer(args[2], source, "font size")
        pxrange = 4 if len(args) == 2 else integer(args[3], source, "font pxrange")
        if size <= 0 or pxrange <= 0 or not (root / path).is_file():
            raise AssetError(f"{source}: invalid or missing font {name}")
        fonts.append({"name": name, "source": path, "size": size, "pxrange": pxrange})
    if not atlases:
        raise AssetError(f"{source}: at least one assets.atlas declaration is required")
    return {"atlases": atlases, "fonts": fonts}


def referenced_slices(root: Path, atlases: list[dict]) -> dict[str, set[str]]:
    all_names: dict[str, list[str]] = {}
    for atlas in atlases:
        document = json.loads(Path(atlas["export_json"]).read_text(encoding="utf-8"))
        for item in document.get("meta", {}).get("slices", []):
            all_names.setdefault(item["name"], []).append(atlas["name"])
    used = {atlas["name"]: set() for atlas in atlases}
    source_files = list((root / "content").rglob("*.h"))
    source_files += list((root / "content").rglob("*.hpp"))
    for path in source_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"", " ", text, flags=re.S)
        for marker in re.findall(r"\bt_([A-Za-z_][A-Za-z0-9_]*)\b", text):
            if "_" in marker:
                owner, slice_name = marker.split("_", 1)
                if owner in used:
                    used[owner].add(slice_name)
                    continue
            owners = all_names.get(marker, [])
            if len(owners) == 1:
                used[owners[0]].add(marker)
            elif len(owners) > 1:
                raise AssetError(f"{path}: ambiguous texture marker t_{marker}; use an atlas-prefixed marker")
    return used


def validate_atlas_export(png: Path, meta: Path, source: Path) -> dict:
    if not png.is_file() or not meta.is_file() or not png.stat().st_size \
            or not meta.stat().st_size:
        raise AssetError(f"prepared atlas is missing PNG/JSON output for {source}")
    try:
        document = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssetError(f"prepared atlas JSON is malformed for {source}: {exc}") from exc
    frames = document.get("frames")
    frame_count = len(frames) if isinstance(frames, (dict, list)) else 0
    if frame_count != 1:
        raise AssetError(
            f"Aseprite atlas {source} must contain exactly one frame; found {frame_count}")
    slices = document.get("meta", {}).get("slices")
    if not isinstance(slices, list):
        raise AssetError(f"Aseprite atlas {source} did not export slice metadata")
    names = [item.get("name") for item in slices if isinstance(item, dict)]
    if len(names) != len(set(names)) or any(not name for name in names):
        raise AssetError(f"Aseprite atlas {source} contains invalid or duplicate slice names")
    if "invalid" not in names:
        raise AssetError(f"Aseprite atlas {source} must contain an invalid slice")
    return document


def export_aseprite(
        executable: Path, source: Path, png: Path, meta: Path,
        fingerprint: dict | None = None) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable), "--batch", "--list-slices", "--layer",
        ATLAS_EXPORT_LAYER, str(source),
        "--sheet", str(png), "--data", str(meta),
        "--format", "json-hash",
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        raise AssetError(
            f"Aseprite export failed for {source} (exit {result.returncode}){suffix}")
    document = validate_atlas_export(png, meta, source)
    if fingerprint is not None:
        document["_content_prepared"] = fingerprint
        write_json_if_changed(meta, document)


def prepared_atlas_paths(source: Path) -> tuple[Path, Path]:
    return source.with_suffix(".png"), source.with_suffix(".json")


def prepared_font_paths(source: Path) -> tuple[Path, Path]:
    return source.with_name(f"{source.stem}__none.png"), source.with_suffix(".json")


def prepare_atlas(
        executable: Path, source: Path, png: Path, meta: Path, fingerprint: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="aseprite-prepared-") as temporary:
        temporary_root = Path(temporary)
        export_aseprite(
            executable, source, temporary_root / png.name, temporary_root / meta.name,
            fingerprint)
        copy_if_changed(temporary_root / png.name, png)
        copy_if_changed(temporary_root / meta.name, meta)


def validate_font_export(png: Path, meta: Path, source: Path) -> dict:
    if not png.is_file() or not meta.is_file() or not png.stat().st_size \
            or not meta.stat().st_size:
        raise AssetError(f"prepared font is missing PNG/JSON output for {source}")
    try:
        document = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssetError(f"prepared font JSON is malformed for {source}: {exc}") from exc
    atlas = document.get("atlas")
    glyphs = document.get("glyphs")
    if not isinstance(atlas, dict) or not isinstance(glyphs, list):
        raise AssetError(f"prepared font JSON is missing atlas/glyph data for {source}")
    if float(atlas.get("width", 0)) <= 0 or float(atlas.get("height", 0)) <= 0:
        raise AssetError(f"prepared font JSON has invalid atlas dimensions for {source}")
    return document


def prepare_font(
        executable: Path, source: Path, png: Path, meta: Path,
        name: str, size: int, pxrange: int, fingerprint: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="font-prepared-") as temporary:
        temporary_root = Path(temporary)
        subprocess.run([
            sys.executable, str(Path(__file__).with_name("font_codegen.py")),
            "--output-root", str(temporary_root),
            "--header", str(temporary_root / "unused.h"),
            "--msdf-atlas-gen", str(executable),
            "--font-spec", "|".join((name, str(source), str(size), str(pxrange)))],
            check=True)
        generated_png = temporary_root / "font" / png.name
        generated_meta = temporary_root / "font" / meta.name
        document = validate_font_export(generated_png, generated_meta, source)
        document["_content_prepared"] = fingerprint
        write_json_if_changed(generated_meta, document)
        copy_if_changed(generated_png, png)
        copy_if_changed(generated_meta, meta)


def stage(root: Path, output_root: Path, manifest_path: Path, header: Path,
          msdf: Path | None, aseprite: Path | None) -> None:
    spec = scan(root)
    output_root.mkdir(parents=True, exist_ok=True)
    raw_root = output_root / "_aseprite"
    atlas_dir = output_root / "atlases"
    font_dir = output_root / "fonts"
    state_path = output_root / ".asset-cache.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {"version": 1, "atlases": {}, "fonts": {}}

    asset_script_hash = digest_file(Path(__file__))
    atlas_script = Path(__file__).with_name("content_atlas.py")
    atlas_script_hash = digest_file(atlas_script)
    font_script = Path(__file__).with_name("font_codegen.py")
    font_script_hash = digest_file(font_script)
    generated = []
    exclusions = []
    next_atlases = {}
    for atlas in spec["atlases"]:
        name = atlas["name"]
        source = root / atlas["source"]
        prepared_png, prepared_json = prepared_atlas_paths(source)
        fingerprint = prepared_fingerprint(
            "aseprite", source, pipeline=asset_script_hash,
            layer=ATLAS_EXPORT_LAYER)
        prepared_exists = prepared_png.is_file() and prepared_json.is_file()
        prepared_document = None
        if prepared_exists:
            try:
                prepared_document = validate_atlas_export(
                    prepared_png, prepared_json, source)
            except AssetError:
                if not aseprite:
                    raise
        if not prepared_exists or prepared_document is None \
                or prepared_metadata(prepared_document) != fingerprint:
            if aseprite:
                prepare_atlas(
                    aseprite, source, prepared_png, prepared_json, fingerprint)
                prepared_document = validate_atlas_export(
                    prepared_png, prepared_json, source)
            elif prepared_exists and prepared_document is not None:
                raise AssetError(
                    f"prepared atlas is stale for {source}; set ASEPRITE to "
                    "regenerate its PNG/JSON output")
            else:
                raise AssetError(
                    f"prepared atlas files are missing for {source}; "
                    "set ASEPRITE or add the checked-in .png/.json outputs")
        raw_png = raw_root / f"{name}.png"
        raw_json = raw_root / f"{name}.json"
        export_key = digest_bytes(
            prepared_png.read_bytes() + prepared_json.read_bytes())
        previous = state.get("atlases", {}).get(name, {})
        if (previous.get("export_key") != export_key
                or not raw_png.is_file() or not raw_json.is_file()):
            copy_if_changed(prepared_png, raw_png)
            copy_if_changed(prepared_json, raw_json)
        atlas["export_key"] = export_key
        atlas["export_png"] = str(raw_png)
        atlas["export_json"] = str(raw_json)

    used = referenced_slices(root, spec["atlases"])
    for atlas in spec["atlases"]:
        name = atlas["name"]
        raw_png = Path(atlas["export_png"])
        raw_json = Path(atlas["export_json"])
        export_key = atlas["export_key"]
        previous = state.get("atlases", {}).get(name, {})
        compact_key = digest_bytes(json.dumps({
            "export": export_key,
            "used": sorted(used[name]),
            "script": atlas_script_hash,
        }, sort_keys=True).encode("utf-8"))
        out_png = atlas_dir / f"{name}.png"
        out_json = atlas_dir / f"{name}.json"
        if (previous.get("compact_key") != compact_key
                or not out_png.is_file() or not out_json.is_file()):
            with tempfile.TemporaryDirectory(prefix="atlas-") as temporary:
                temporary_root = Path(temporary)
                cmd = [sys.executable, str(atlas_script),
                       "--png", str(raw_png), "--json", str(raw_json),
                       "--output-png", str(temporary_root / out_png.name),
                       "--output-json", str(temporary_root / out_json.name)]
                for item in sorted(used[name]):
                    cmd.extend(["--used", item])
                subprocess.run(cmd, check=True)
                copy_if_changed(temporary_root / out_png.name, out_png)
                copy_if_changed(temporary_root / out_json.name, out_json)
        atlas.update(runtime_png=f"assets/generated/atlases/{name}.png",
                     runtime_json=f"assets/generated/atlases/{name}.json")
        generated += [str(out_png), str(out_json)]
        exclusions.append(atlas["source"])
        source_path = Path(atlas["source"])
        for prepared in prepared_atlas_paths(source_path):
            exclusions.append(prepared.as_posix())
        del atlas["export_key"]
        del atlas["export_png"]
        del atlas["export_json"]
        next_atlases[name] = {"export_key": export_key, "compact_key": compact_key,
                              "used": sorted(used[name])}

    next_fonts = {}
    font_codegen = load_font_codegen()
    font_dir.mkdir(parents=True, exist_ok=True)
    for font in spec["fonts"]:
        name = font["name"]
        source = root / font["source"]
        prepared_png, prepared_json = prepared_font_paths(source)
        fingerprint = prepared_fingerprint(
            "msdf", source, name=name, size=font["size"],
            pxrange=font["pxrange"], pipeline=font_script_hash)
        prepared_exists = prepared_png.is_file() and prepared_json.is_file()
        prepared_document = None
        if prepared_exists:
            try:
                prepared_document = validate_font_export(
                    prepared_png, prepared_json, source)
            except AssetError:
                if not msdf:
                    raise
        if not prepared_exists or prepared_document is None \
                or prepared_metadata(prepared_document) != fingerprint:
            if msdf:
                prepare_font(
                    msdf, source, prepared_png, prepared_json,
                    name, font["size"], font["pxrange"], fingerprint)
                prepared_document = validate_font_export(
                    prepared_png, prepared_json, source)
            elif prepared_exists and prepared_document is not None:
                print(
                    f"content asset warning: prepared font is stale for {source}; "
                    "using the checked-in output. Set MSDF_ATLAS_GEN to regenerate it.",
                    file=sys.stderr)
            else:
                raise AssetError(
                    f"prepared font files are missing for {source}; "
                    "set MSDF_ATLAS_GEN or add the checked-in PNG/JSON outputs")
        key = digest_bytes(prepared_png.read_bytes() + prepared_json.read_bytes())
        previous = state.get("fonts", {}).get(name, {})
        out_png = font_dir / f"{name}__none.png"
        out_json = font_dir / f"{name}.json"
        if (previous.get("key") != key or not out_png.is_file() or not out_json.is_file()):
            copy_if_changed(prepared_png, out_png)
            copy_if_changed(prepared_json, out_json)
        font.update(texture=f"font_{name}",
                    runtime_png=f"assets/generated/fonts/{name}__none.png",
                    runtime_json=f"assets/generated/fonts/{name}.json")
        next_fonts[name] = {"key": key}
        exclusions.append(font["source"])
        for prepared in prepared_font_paths(Path(font["source"])):
            exclusions.append(prepared.as_posix())

    prune_directory(raw_root, {f"{name}.{suffix}" for name in next_atlases for suffix in ("png", "json")})
    prune_directory(atlas_dir, {f"{name}.{suffix}" for name in next_atlases for suffix in ("png", "json")})
    prune_directory(font_dir, {f"{name}.{suffix}" for name in next_fonts for suffix in ("png", "json")} |
                    {f"{name}__none.png" for name in next_fonts})

    if spec["fonts"]:
        generated_fonts = [(font["name"], json.loads(
            (font_dir / f"{font['name']}.json").read_text(encoding="utf-8")))
                           for font in spec["fonts"]]
        write_if_changed(header, font_codegen.render_header(generated_fonts).encode("utf-8"))
    else:
        write_if_changed(header, b"#pragma once\n")
    manifest = {**spec, "generated_root": str(output_root), "exclusions": exclusions}
    write_json_if_changed(manifest_path, manifest)
    write_json_if_changed(state_path, {"version": 1, "atlases": next_atlases,
                                       "fonts": next_fonts})


def stage_package(root: Path, stage_dir: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    client_data = (stage_dir / "client.wasm").read_bytes() if (stage_dir / "client.wasm").is_file() else None
    if stage_dir.exists(): shutil.rmtree(stage_dir)
    if client_data is None:
        raise AssetError(f"missing content executable: {stage_dir / 'client.wasm'}")
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "client.wasm").write_bytes(client_data)
    (stage_dir / "assets").mkdir(parents=True)
    for path in (root / "assets").rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel not in manifest["exclusions"] \
                    and path.suffix.lower() not in {".aseprite", ".ttf"}:
                target = stage_dir / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    generated_root = Path(manifest["generated_root"])
    for rel in [item["runtime_png"] for item in manifest["atlases"]] + [item["runtime_json"] for item in manifest["atlases"]] + [item["runtime_png"] for item in manifest["fonts"]] + [item["runtime_json"] for item in manifest["fonts"]]:
        name = Path(rel).name; source = generated_root / ("atlases" if "/atlases/" in rel else "fonts") / name
        target = stage_dir / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True); parser.add_argument("--output-root", type=Path); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--header", type=Path); parser.add_argument("--msdf-atlas-gen", type=Path); parser.add_argument("--aseprite", type=Path); parser.add_argument("--stage-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.stage_dir: stage_package(args.root.resolve(), args.stage_dir.resolve(), args.manifest.resolve())
        else:
            stage(args.root.resolve(), args.output_root.resolve(), args.manifest.resolve(),
                  args.header.resolve(),
                  args.msdf_atlas_gen.resolve() if args.msdf_atlas_gen else None,
                  args.aseprite.resolve() if args.aseprite else None)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"content asset error: {exc}", file=__import__('sys').stderr); return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
