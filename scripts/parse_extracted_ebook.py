#!/usr/bin/env python3
"""Inspect an extracted ebook text directory and group files into chapters.

Language-neutral: grouping is based on filenames and ordering, not language.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.name.casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def group_files(directory: Path) -> list[tuple[str, list[Path]]]:
    groups: dict[tuple[str, int], list[Path]] = {}
    loose: list[Path] = []
    ignored = {"cover", "message", "poem", "character_gallery"}

    for path in sorted(directory.glob("*.txt"), key=natural_key):
        name = path.stem

        match = re.match(r"^chapter[-_]?(\d+)[-_](\d+)$", name, re.I)
        if match:
            groups.setdefault(("chapter", int(match.group(1))), []).append(path)
            continue

        match = re.match(r"^(intro|epilogue)[-_](\d+)$", name, re.I)
        if match:
            groups.setdefault((match.group(1).lower(), int(match.group(2))), []).append(path)
            continue

        if name.casefold() in ignored:
            continue
        loose.append(path)

    result: list[tuple[str, list[Path]]] = []
    order = {"intro": 0, "chapter": 1, "epilogue": 2}
    for (kind, number), paths in sorted(groups.items(), key=lambda item: (order[item[0][0]], item[0][1])):
        if kind == "chapter":
            title = f"Chapter {number}"
        elif kind == "intro":
            title = "Introduction" if number == 0 else f"Introduction {number}"
        else:
            title = f"Epilogue {number}"
        result.append((title, sorted(paths, key=natural_key)))

    for path in sorted(loose, key=natural_key):
        result.append((path.stem, [path]))

    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: parse_extracted_ebook.py <text-directory>")
    directory = Path(sys.argv[1])
    for title, paths in group_files(directory):
        print(f"[{title}]")
        for path in paths:
            print(f"  {path.name}")


if __name__ == "__main__":
    main()
