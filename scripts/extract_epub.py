#!/usr/bin/env python3
"""Extract EPUB resources and paragraph IDs for translation."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

ELIGIBLE = {"title", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "caption", "dt", "dd"}
HTML_EXTS = {".xhtml", ".html", ".htm"}
JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def has_japanese(text: str) -> bool:
    return bool(JP.search(text))


def source_text(el: etree._Element) -> str:
    return "".join(el.itertext()).strip()


def build_xpath_map(root: etree._Element) -> dict[etree._Element, str]:
    result: dict[etree._Element, str] = {}

    def visit(parent: etree._Element, parent_path: str) -> None:
        counters: dict[str, int] = {}
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            local = etree.QName(child).localname
            counters[local] = counters.get(local, 0) + 1
            path = f"{parent_path}/*[local-name()='{local}'][{counters[local]}]"
            result[child] = path
            visit(child, path)

    local = etree.QName(root).localname
    root_path = f"/*[local-name()='{local}'][1]"
    result[root] = root_path
    visit(root, root_path)
    return result


def paragraph_id(rel: str, index: int) -> str:
    key = Path(rel).with_suffix("").as_posix().replace("/", "__")
    return f"{key}-{index:04d}"


def image_href(el: etree._Element) -> str:
    return el.get("src") or el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or ""


def has_eligible_ancestor(el: etree._Element) -> bool:
    parent = el.getparent()
    while parent is not None:
        if isinstance(parent.tag, str) and etree.QName(parent).localname.lower() in ELIGIBLE:
            return True
        parent = parent.getparent()
    return False


def extract_file(raw: bytes, rel: str) -> tuple[list[dict], list[dict]]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    root = etree.fromstring(raw, parser)
    paths = build_xpath_map(root)
    paragraphs: list[dict] = []
    content: list[dict] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname.lower()
        if local in ELIGIBLE and not has_eligible_ancestor(el):
            text = source_text(el)
            if text and has_japanese(text):
                index = len(paragraphs) + 1
                paragraph = {
                    "id": paragraph_id(rel, index),
                    "index": index - 1,
                    "tag": local,
                    "source": rel,
                    "xpath": paths[el],
                    "text_file": f"text/{Path(rel).with_suffix('.txt').as_posix()}",
                    "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "_text": text,
                }
                paragraphs.append(paragraph)
                content.append({"type": "paragraph", "id": paragraph["id"]})
                continue
        if local == "img" and not has_eligible_ancestor(el):
            href = image_href(el)
            if href:
                content.append({"type": "image", "href": href, "xpath": paths[el]})
    return paragraphs, content


def write_text(path: Path, paragraphs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for paragraph in paragraphs:
        lines.extend([f"[{paragraph['id']}]", paragraph["_text"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def extract(epub: Path, data_root: Path, book: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        unpack = Path(tmp) / "epub"
        with zipfile.ZipFile(epub) as zf:
            zf.extractall(unpack)
        if (unpack / "mimetype").read_bytes() != b"application/epub+zip":
            raise SystemExit("invalid EPUB mimetype")
        if not (unpack / "META-INF/container.xml").is_file():
            raise SystemExit("missing META-INF/container.xml")
        out = data_root / book
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(unpack, out / "epub")
        files = []
        total = 0
        for source in sorted((out / "epub").rglob("*")):
            if not source.is_file() or source.suffix.lower() not in HTML_EXTS:
                continue
            raw = source.read_bytes()
            rel = source.relative_to(out / "epub").as_posix()
            paragraphs, content = extract_file(raw, rel)
            if not paragraphs and not content:
                continue
            text_file = f"text/{Path(rel).with_suffix('.txt').as_posix()}"
            if paragraphs:
                write_text(out / text_file, paragraphs)
            for paragraph in paragraphs:
                paragraph.pop("_text", None)
            files.append({
                "source": rel,
                "text": text_file,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "paragraph_count": len(paragraphs),
                "paragraphs": paragraphs,
                "content": content,
            })
            total += len(paragraphs)
        manifest = {"version": 3, "book": book, "source_epub": epub.name, "paragraph_count": total, "files": files}
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: extract_epub.py <source-epub> <data-root> <book-name>")
    extract(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])


if __name__ == "__main__":
    main()
