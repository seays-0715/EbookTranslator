#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

ELIGIBLE = {"title", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "caption", "dt", "dd"}
JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def parse_translation(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: dict[str, str] = {}
    current = None
    body: list[str] = []
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            if current is not None:
                if current in result:
                    raise SystemExit(f"duplicate translation id: {current}")
                result[current] = "\n".join(body).strip()
            current = line[1:-1]
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        if current in result:
            raise SystemExit(f"duplicate translation id: {current}")
        result[current] = "\n".join(body).strip()
    return result


def source_text(node: etree._Element) -> str:
    return "".join(node.itertext()).strip()


def image_target(href: str, source_xhtml: Path) -> str:
    clean = unquote(href.split("#", 1)[0])
    if not clean:
        raise SystemExit(f"invalid image href: {href}")
    source_image = (source_xhtml.parent / clean).resolve()
    if not source_image.is_file():
        raise SystemExit(f"missing image: {href}")
    return href


def eligible_paragraphs(root: etree._Element) -> list[etree._Element]:
    result = []
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        local = etree.QName(node).localname.lower()
        if local not in ELIGIBLE:
            continue
        parent = node.getparent()
        nested = False
        while parent is not None:
            if isinstance(parent.tag, str) and etree.QName(parent).localname.lower() in ELIGIBLE:
                nested = True
                break
            parent = parent.getparent()
        if not nested:
            text = source_text(node)
            if text and JP.search(text):
                result.append(node)
    return result


def locate_source_paragraph(root, paragraph, candidates):
    expected_hash = paragraph.get("source_text_sha256")
    xpath = paragraph.get("xpath")
    if xpath:
        nodes = root.xpath(xpath)
        if len(nodes) == 1:
            node = nodes[0]
            text = source_text(node)
            if not expected_hash or hashlib.sha256(text.encode("utf-8")).hexdigest() == expected_hash:
                return node
    index = paragraph.get("index")
    if isinstance(index, int) and 0 <= index < len(candidates):
        node = candidates[index]
        text = source_text(node)
        if not expected_hash or hashlib.sha256(text.encode("utf-8")).hexdigest() == expected_hash:
            return node
    raise SystemExit(f"cannot locate source paragraph: {paragraph['id']}")


def source_paragraphs(file: dict, source: Path) -> dict[str, str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    tree = etree.parse(str(source), parser)
    root = tree.getroot()
    candidates = eligible_paragraphs(root)
    result: dict[str, str] = {}
    for paragraph in file["paragraphs"]:
        result[paragraph["id"]] = source_text(locate_source_paragraph(root, paragraph, candidates))
    return result


def has_text_descendants(node: etree._Element) -> bool:
    for child in node.iterdescendants():
        if not isinstance(child.tag, str):
            continue
        if child.text and child.text.strip():
            return True
        if child.tail and child.tail.strip():
            return True
    return False


def replace_plain_text(node: etree._Element, translated: str) -> None:
    """Replace text in a simple container without destroying its own structure."""
    if has_text_descendants(node):
        raise SystemExit(
            f"cannot safely replace nested inline markup in source paragraph: "
            f"{node.getroottree().getpath(node)}"
        )
    node.text = translated


def build_document(file, translations, source_root, output_root):
    source = source_root / file["source"]
    target = output_root / file["source"]
    target.parent.mkdir(parents=True, exist_ok=True)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    original = etree.parse(str(source), parser)
    root = original.getroot()
    candidates = eligible_paragraphs(root)
    source_texts: dict[str, str] = {}
    for paragraph in file["paragraphs"]:
        node = locate_source_paragraph(root, paragraph, candidates)
        source_texts[paragraph["id"]] = source_text(node)

    paragraphs = {p["id"]: p for p in file["paragraphs"]}
    expected_ids = [p["id"] for p in file["paragraphs"]]
    actual_ids = list(translations)
    if not set(actual_ids).issubset(set(expected_ids)):
        raise SystemExit(f"unexpected translation IDs: {file['source']}")

    missing = [pid for pid in expected_ids if pid not in translations]
    for item in file["content"]:
        if item["type"] == "paragraph":
            paragraph = paragraphs[item["id"]]
            node = locate_source_paragraph(root, paragraph, candidates)
            translated = translations.get(item["id"], source_texts[item["id"]])
            if not translated:
                raise SystemExit(f"empty source/translation: {item['id']}")
            replace_plain_text(node, translated)
        elif item["type"] == "image":
            href = image_target(item["href"], source)
            nodes = root.xpath(item.get("xpath", "")) if item.get("xpath") else []
            if len(nodes) != 1:
                raise SystemExit(f"cannot locate source image: {item['href']}")
            image = nodes[0]
            if etree.QName(image).localname.lower() != "img":
                raise SystemExit(f"source image target is not img: {item['href']}")
            if not image.get("src") and not image.get("{http://www.w3.org/1999/xlink}href"):
                image.set("src", href)
        else:
            raise SystemExit(f"unknown content type: {item['type']}")

    original.write(str(target), encoding="utf-8", xml_declaration=True, doctype="<!DOCTYPE html>")
    return len(missing) if translations else 0


def rebuild(book: Path, translating_root: Path) -> int:
    manifest = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    translation_root = translating_root / manifest["book"]
    out = book / "epub_translated"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(book / "epub", out)
    missing_total = 0
    for file in manifest["files"]:
        translation_file = translation_root / Path(file["text"]).relative_to("text")
        translations = parse_translation(translation_file) if translation_file.is_file() else {}
        missing_total += build_document(file, translations, book / "epub", out)
    return missing_total


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: reconstruct_epub.py <data-book> <translating-root>")
    raise SystemExit(rebuild(Path(sys.argv[1]), Path(sys.argv[2])))


if __name__ == "__main__":
    main()
