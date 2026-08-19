#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
HEADER = re.compile(r"^\[([^\]]+)\]$")


def parse_txt(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    current = None
    body = []
    for line in lines:
        m = HEADER.match(line.strip())
        if m:
            if current is not None:
                records.append((current, "\n".join(body).strip()))
            current = m.group(1)
            body = []
        elif current is not None:
            body.append(line)
        elif line.strip():
            raise ValueError(f"text before first paragraph header: {path}")
    if current is not None:
        records.append((current, "\n".join(body).strip()))
    return records


def validate(book: Path, translating: Path, complete: bool = True) -> int:
    manifest = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    expected = []
    errors = []
    expected_translation_files = set()
    for file in manifest["files"]:
        expected_file = [p["id"] for p in file["paragraphs"]]
        expected.extend(expected_file)
        relative_text = Path(file["text"]).relative_to("text")
        source_epub = book / "epub" / file["source"]
        if not source_epub.is_file():
            errors.append(f"missing source XHTML: {source_epub}")
        elif hashlib.sha256(source_epub.read_bytes()).hexdigest() != file["source_sha256"]:
            errors.append(f"source XHTML changed: {file['source']}")
        source_path = book / file["text"]
        if file["paragraph_count"] == 0:
            continue
        expected_translation_files.add(relative_text.as_posix())
        translated_path = translating / manifest["book"] / relative_text
        if not source_path.is_file():
            errors.append(f"missing source TXT: {source_path}")
            continue
        if not translated_path.is_file():
            if complete:
                errors.append(f"missing translation TXT: {translated_path}")
            continue
        source_ids = [x[0] for x in parse_txt(source_path)]
        translated_records = parse_txt(translated_path)
        translated_ids = [x[0] for x in translated_records]
        if source_ids != expected_file:
            errors.append(f"source ID mismatch: {source_path}")
        if complete and translated_ids != expected_file:
            errors.append(f"translation ID/order mismatch: {translated_path}")
        elif not complete and not set(translated_ids).issubset(set(expected_file)):
            errors.append(f"translation ID mismatch: {translated_path}")
        if len(set(translated_ids)) != len(translated_ids):
            errors.append(f"duplicate translation IDs: {translated_path}")
        for pid, text in translated_records:
            if not text:
                errors.append(f"empty translation: {pid}")
            if JP.search(text):
                errors.append(f"Japanese residue: {pid}")
    translation_dir = translating / manifest["book"]
    if translation_dir.is_dir():
        actual_files = {p.relative_to(translation_dir).as_posix() for p in translation_dir.rglob("*.txt")}
        for extra in sorted(actual_files - expected_translation_files):
            errors.append(f"unexpected translation TXT: {extra}")
    if len(expected) != manifest["paragraph_count"]:
        errors.append("manifest paragraph_count mismatch")
    if errors:
        print("QA FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"QA PASSED ({'complete' if complete else 'partial'}): {len(expected)} paragraphs")
    return 0


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: validate_translation.py <data-book> <translating-root> [partial]")
    raise SystemExit(validate(Path(sys.argv[1]), Path(sys.argv[2]), complete=len(sys.argv) == 3 or sys.argv[3].lower() != "partial"))


if __name__ == "__main__":
    main()
