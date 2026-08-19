#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path
from lxml import etree

HTML_EXTS = {".xhtml", ".html", ".htm"}


def package(book: Path, template: Path, output: Path) -> None:
    root = book / "epub_translated"
    if not root.is_dir():
        raise RuntimeError(f"missing reconstructed EPUB: {root}")
    css_path = template / "style.css"
    if not css_path.is_file():
        raise RuntimeError(f"missing template style: {css_path}")
    work = book / "_packaged"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(root, work)
    css = css_path.read_text(encoding="utf-8")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    for path in work.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in HTML_EXTS:
            continue
        tree = etree.parse(str(path), parser)
        heads = tree.xpath("//*[local-name()='head']")
        if not heads:
            continue
        namespace = etree.QName(heads[0]).namespace
        node = etree.Element(f"{{{namespace}}}style" if namespace else "style", type="text/css")
        node.text = css
        heads[0].append(node)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    mimetype = work / "mimetype"
    if not mimetype.is_file():
        raise RuntimeError(f"missing EPUB mimetype: {mimetype}")
    if mimetype.read_bytes() != b"application/epub+zip":
        raise RuntimeError("invalid EPUB mimetype")
    with zipfile.ZipFile(output, "w") as zf:
        zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(work.rglob("*")):
            if path.is_dir() or path == mimetype:
                continue
            zf.write(path, path.relative_to(work).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
    shutil.rmtree(work)


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: package_epub.py <data-book> <template> <output-epub>")
    package(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))


if __name__ == "__main__":
    main()
