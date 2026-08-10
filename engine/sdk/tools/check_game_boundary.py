from __future__ import annotations

import argparse
import re
from pathlib import Path


FORBIDDEN = (
    (re.compile(r"(?:^|[/\\])src[/\\](?:engine|content_sdk)(?:[/\\]|$)", re.IGNORECASE), "obsolete source path"),
    (re.compile(r"(?:\.\.[/\\])+(?:tools|engine)(?:[/\\]|$)", re.IGNORECASE), "repository-relative engine/tool path"),
    (re.compile(r"\busing\s+namespace\s+engine\s*;"), "content-local engine namespace import"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    violations: list[str] = []
    for path in sorted(args.root.rglob("*")):
        if any(part.lower() in {"build", "out", ".git", "__pycache__"}
               for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in {".h", ".hpp", ".cpp", ".cmake", ".txt", ".bat"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, description in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path}:{line}: {description}")
    if violations:
        print("Standalone game boundary violations:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("Standalone game boundary OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
