"""
Generate an MSDF font atlas PNG plus C++ glyph metrics.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


FIRST_PRINTABLE_ASCII = 32
LAST_PRINTABLE_ASCII = 126
GLYPH_COUNT = LAST_PRINTABLE_ASCII - FIRST_PRINTABLE_ASCII + 1


def write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def f32(value: float) -> str:
    text = f"{float(value):.9g}"
    if "e" not in text and "E" not in text and "." not in text:
        text += ".0"
    return f"{text}f"


def bounds_vec4(bounds: dict[str, float] | None, *, atlas_height: float | None = None) -> str:
    if not bounds:
        return "vec4(0.0f)"

    left = float(bounds.get("left", 0.0))
    bottom = float(bounds.get("bottom", 0.0))
    right = float(bounds.get("right", 0.0))
    top = float(bounds.get("top", 0.0))

    if atlas_height is not None:
        # msdf-atlas-gen emits atlasBounds with bottom-origin coordinates. The
        # runtime atlas UVs are top-origin, so convert to x/y/width/height in
        # generated texture pixel space.
        y = atlas_height - top
        return (
            f"vec4({f32(left)}, {f32(y)}, "
            f"{f32(right - left)}, {f32(top - bottom)})"
        )

    return (
        f"vec4({f32(left)}, {f32(bottom)}, "
        f"{f32(right - left)}, {f32(top - bottom)})"
    )


def cpp_identifier(name: str) -> str:
    ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not ident:
        ident = "font"
    if ident[0].isdigit():
        ident = f"font_{ident}"
    return ident


def render_font_glyphs(font_json: dict) -> tuple[str, dict, dict]:
    atlas = font_json.get("atlas", {})
    metrics = font_json.get("metrics", {})
    atlas_width = float(atlas.get("width", 0.0))
    atlas_height = float(atlas.get("height", 0.0))
    glyphs_by_code = {
        int(glyph["unicode"]): glyph
        for glyph in font_json.get("glyphs", [])
        if "unicode" in glyph
    }

    glyph_lines: list[str] = []
    for codepoint in range(FIRST_PRINTABLE_ASCII, LAST_PRINTABLE_ASCII + 1):
        glyph = glyphs_by_code.get(codepoint)
        if glyph is None:
            glyph_lines.append("    { false, 0.0f, vec4(0.0f), vec4(0.0f) },")
            continue

        has_atlas_bounds = "atlasBounds" in glyph and "planeBounds" in glyph
        advance = float(glyph.get("advance", 0.0))
        plane = bounds_vec4(glyph.get("planeBounds"))
        atlas_bounds = bounds_vec4(glyph.get("atlasBounds"), atlas_height=atlas_height)
        glyph_lines.append(
            f"    {{ {'true' if has_atlas_bounds else 'false'}, "
            f"{f32(advance)}, {plane}, {atlas_bounds} }},"
        )

    return "\n".join(glyph_lines), atlas, metrics


def render_header(generated_fonts: list[tuple[str, dict]]) -> str:
    font_blocks: list[str] = []
    info_lines: list[str] = []
    id_lines: list[str] = []
    font_names = [font_name for font_name, _ in generated_fonts]
    default_font = "quantix" if "quantix" in font_names else (generated_fonts[0][0] if generated_fonts else "invalid")

    for font_index, (font_name, font_json) in enumerate(generated_fonts):
        ident = cpp_identifier(font_name)
        glyph_lines, atlas, metrics = render_font_glyphs(font_json)
        font_blocks.append(
            f"""inline constexpr GeneratedFontGlyph GENERATED_FONT_GLYPHS_{ident}[GENERATED_FONT_GLYPH_COUNT] = {{
{glyph_lines}
}};"""
        )
        info_lines.append(
            f'    {{"{ident}", {font_index}u, {f32(float(atlas.get("width", 0.0)))}, '
            f'{f32(float(atlas.get("height", 0.0)))}, {f32(float(atlas.get("distanceRange", 4.0)))}, '
            f'{f32(float(atlas.get("size", 32.0)))}, {f32(float(metrics.get("lineHeight", 1.0)))}, '
            f'{f32(float(metrics.get("ascender", 0.0)))}, {f32(float(metrics.get("descender", 0.0)))}, '
            f"GENERATED_FONT_GLYPHS_{ident}}},"
        )
        id_lines.append(f"    inline constexpr uint32 {ident} = {font_index}u;")

    font_blocks_text = "\n\n".join(font_blocks)
    info_text = "\n".join(info_lines)
    id_text = "\n".join(id_lines)
    default_ident = cpp_identifier(default_font)

    return f"""#pragma once

struct GeneratedFontGlyph {{
    bool present;
    float advance;
    vec4 plane_bounds;
    vec4 atlas_bounds;
}};

struct GeneratedFontInfo {{
    const char* name;
    uint32 id;
    float atlas_width;
    float atlas_height;
    float distance_range;
    float size;
    float line_height;
    float ascender;
    float descender;
    const GeneratedFontGlyph* glyphs;
}};

inline constexpr uint32 GENERATED_FONT_FIRST_CODEPOINT = {FIRST_PRINTABLE_ASCII}u;
inline constexpr uint32 GENERATED_FONT_LAST_CODEPOINT = {LAST_PRINTABLE_ASCII}u;
inline constexpr uint32 GENERATED_FONT_GLYPH_COUNT = {GLYPH_COUNT}u;
inline constexpr uint32 GENERATED_FONT_COUNT = {len(generated_fonts)}u;

{font_blocks_text}

inline constexpr GeneratedFontInfo GENERATED_FONTS[GENERATED_FONT_COUNT] = {{
{info_text}
}};

namespace fonts {{
{id_text}
    inline constexpr uint32 default_font = {default_ident};
}}
"""


def run_msdf_atlas_gen(args: argparse.Namespace, image_path: Path, json_path: Path) -> None:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(args.msdf_atlas_gen),
        "-font",
        str(args.font),
        "-type",
        "msdf",
        "-format",
        "png",
        "-size",
        str(args.size),
        "-pxrange",
        str(args.pxrange),
        "-imageout",
        str(image_path),
        "-json",
        str(json_path),
    ]
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MSDF font atlas and metrics header")
    parser.add_argument("--msdf-atlas-gen", required=True, type=Path)
    parser.add_argument("--font", action="append", default=[], type=Path)
    parser.add_argument(
        "--font-spec", action="append", default=[],
        help="name|path|size|pxrange; may be repeated")
    parser.add_argument("--font-root", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--header", default="aot_font.h")
    parser.add_argument("--size", default=32, type=int)
    parser.add_argument("--pxrange", default=4, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root: Path = args.output_root
    font_dir = output_root / "font"
    font_jobs: list[tuple[str | None, Path, int, int]] = [
        (None, path, args.size, args.pxrange) for path in args.font]
    for spec in args.font_spec:
        parts = spec.split("|", 3)
        if len(parts) != 4:
            raise ValueError("font spec must be name|path|size|pxrange")
        name, path, size, pxrange = parts
        font_jobs.append((name, Path(path), int(size), int(pxrange)))
    if args.font_root is not None:
        font_jobs.extend(
            (None, path, args.size, args.pxrange)
            for path in sorted(args.font_root.glob("*.ttf")))
    if not font_jobs:
        raise ValueError("No fonts were provided")

    generated_fonts: list[tuple[str, dict]] = []
    generated_paths: set[Path] = set()
    seen_names: set[str] = set()
    for declared_name, font_path, font_size, font_pxrange in font_jobs:
        font_name = cpp_identifier(declared_name or font_path.stem)
        if font_name in seen_names:
            raise ValueError(f"Duplicate font name after identifier cleanup: {font_name}")
        seen_names.add(font_name)

        image_path = font_dir / f"{font_name}__none.png"
        json_path = font_dir / f"{font_name}.json"
        generated_paths.add(image_path.resolve())
        generated_paths.add(json_path.resolve())
        args.font = font_path
        args.size = font_size
        args.pxrange = font_pxrange
        run_msdf_atlas_gen(args, image_path, json_path)
        generated_fonts.append((font_name, json.loads(json_path.read_text())))

    if font_dir.exists():
        for stale_path in list(font_dir.glob("*.png")) + list(font_dir.glob("*.json")):
            if stale_path.resolve() not in generated_paths:
                stale_path.unlink()

    header_path = Path(args.header)
    if not header_path.is_absolute():
        header_path = output_root / header_path
    write_text_if_changed(header_path, render_header(generated_fonts))

    print(f"Written {len(generated_fonts)} font atlases to: {font_dir}")
    print(f"Written font header: {header_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
