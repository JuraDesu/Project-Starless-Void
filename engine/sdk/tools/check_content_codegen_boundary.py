from __future__ import annotations

import argparse
import re
from pathlib import Path


FORBIDDEN = re.compile(
    r"(?i)(?:\$pass\b|(?:^|[\"'])g/|aot_[A-Za-z0-9_]*|flecs(?:::|/)|content/legacy|passes/)"
)
NAME_BASED_ECS = re.compile(
    r"\b(?:component_(?:has|get|get_mut|add|set|remove|modified)"
    r"|entity_spawn)\s*\([^;\n]*[\"'][ce]_[A-Za-z0-9_]*[\"']"
)
CLEANUP_FORBIDDEN = (
    (re.compile(r"\bfloat[234]\b"), "obsolete vector spelling"),
    (re.compile(r"\bg_logged_[A-Za-z0-9_]*\b"), "gameplay diagnostic flag"),
    (re.compile(r"\bdispatch\s*\([^;\n]*[\"'][A-Za-z][A-Za-z0-9_:-]*[\"']"),
     "runtime string event dispatch"),
    (re.compile(r"\bcentripetal\b", re.IGNORECASE), "obsolete interpolation terminology"),
    (re.compile(r"\buv_rect\s*=\s*\{\s*[-+]?\d"), "hardcoded gameplay UV rectangle"),
)
CONTENT_STYLE_FORBIDDEN = (
    (re.compile(r"\bengine::"), "redundant engine namespace qualifier"),
    (re.compile(r"\bEntity\b"), "obsolete capitalized entity type"),
    (re.compile(r"\b(?:EventRegistry|EventBindingRegistry)\b"),
     "manual event registry; use generated e_* declarations"),
    (re.compile(r"\bcontent_register_events\b"),
     "manual event registration export"),
    (re.compile(r"item_contracts\.hpp"),
     "manual item event contract header"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    violations: list[str] = []
    for root in args.paths:
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in {".py", ".h", ".cpp"}:
                continue
            text = path.read_text(encoding="utf-8")
            for match in FORBIDDEN.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path}:{line}: {match.group(0)}")
            for match in NAME_BASED_ECS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(
                    f"{path}:{line}: name-based ECS runtime call")
            for pattern, description in CLEANUP_FORBIDDEN:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    violations.append(f"{path}:{line}: {description}")
            if any(part.lower() in {"content", "public"} for part in path.parts):
                for pattern, description in CONTENT_STYLE_FORBIDDEN:
                    for match in pattern.finditer(text):
                        line = text.count("\n", 0, match.start()) + 1
                        violations.append(f"{path}:{line}: {description}")
    if violations:
        print("Content codegen boundary violations:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("Content codegen boundary OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
