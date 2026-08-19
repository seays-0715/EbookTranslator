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
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


def parse_translation(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: dict[str, str] = {}
    current = None
    body: list[str] = []
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            if current is not None:
                if current in result:
                    raise RuntimeError(f"duplicate translation id: {current}")
                result[current] = "\n".join(body).strip()
            current = line[1:-1]
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        if current in result:
            raise RuntimeError(f"duplicate translation id: {current}")
        result[current] = "\n".join(body).strip()
    return result


def source_text(node: etree._Element) -> str:
    return "".join(node.itertext()).strip()


def image_target(href: str, source_xhtml: Path) -> str:
    clean = unquote(href.split("#", 1)[0])
    if not clean:
        raise RuntimeError(f"invalid image href: {href}")
    source_image = (source_xhtml.parent / clean).resolve()
    if not source_image.is_file():
        raise RuntimeError(f"missing image: {href}")
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
    raise RuntimeError(f"cannot locate source paragraph: {paragraph['id']}")


def source_paragraphs(file: dict, source: Path) -> dict[str, str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    tree = etree.parse(str(source), parser)
    root = tree.getroot()
    candidates = eligible_paragraphs(root)
    result: dict[str, str] = {}
    for paragraph in file["paragraphs"]:
        result[paragraph["id"]] = source_text(locate_source_paragraph(root, paragraph, candidates))
    return result


def original_title(root: etree._Element) -> str:
    nodes = root.xpath("//*[local-name()='head']/*[local-name()='title']")
    return source_text(nodes[0]) if nodes else ""


def make_xhtml(title: str, content_nodes: list[etree._Element]) -> etree._ElementTree:
    html = etree.Element(f"{{{XHTML_NS}}}html", nsmap={None: XHTML_NS, "epub": EPUB_NS})
    html.set("{http://www.w3.org/XML/1998/namespace}lang", "zh-Hant")
    html.set("class", "ebook")

    head = etree.SubElement(html, f"{{{XHTML_NS}}}head")
    meta = etree.SubElement(head, f"{{{XHTML_NS}}}meta")
    meta.set("charset", "UTF-8")
    title_node = etree.SubElement(head, f"{{{XHTML_NS}}}title")
    title_node.text = title or "Ebook"

    body = etree.SubElement(html, f"{{{XHTML_NS}}}body")
    main = etree.SubElement(body, f"{{{XHTML_NS}}}div")
    main.set("class", "main")
    for node in content_nodes:
        main.append(node)
    return etree.ElementTree(html)


def build_document(file, translations, source_root, output_root):
    source = source_root / file["source"]
    target = output_root / file["source"]
    target.parent.mkdir(parents=True, exist_ok=True)

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    original = etree.parse(str(source), parser)
    root = original.getroot()
    candidates = eligible_paragraphs(root)

    paragraphs = {p["id"]: p for p in file["paragraphs"]}
    expected_ids = [p["id"] for p in file["paragraphs"]]
    actual_ids = list(translations)
    if not set(actual_ids).issubset(set(expected_ids)):
        raise RuntimeError(f"unexpected translation IDs: {file['source']}")

    missing = [pid for pid in expected_ids if pid not in translations]
    source_texts: dict[str, str] = {}
    for paragraph in file["paragraphs"]:
        node = locate_source_paragraph(root, paragraph, candidates)
        source_texts[paragraph["id"]] = source_text(node)

    translated_by_id: dict[str, str] = {}
    for paragraph in file["paragraphs"]:
        pid = paragraph["id"]
        translated_by_id[pid] = translations.get(pid, source_texts[pid])
        if not translated_by_id[pid]:
            raise RuntimeError(f"empty source/translation: {pid}")

    title = original_title(root)
    for paragraph in file["paragraphs"]:
        if paragraph.get("tag") == "title":
            title = translated_by_id[paragraph["id"]]
            break

    content_nodes: list[etree._Element] = []
    for item in file["content"]:
        if item["type"] == "paragraph":
            paragraph = paragraphs[item["id"]]
            tag = paragraph.get("tag", "p").lower()
            if tag == "title":
                continue
            if tag not in ELIGIBLE - {"title"}:
                tag = "p"
            node = etree.Element(f"{{{XHTML_NS}}}{tag}")
            node.text = translated_by_id[item["id"]]
            content_nodes.append(node)
        elif item["type"] == "image":
            href = image_target(item["href"], source)
            wrapper = etree.Element(f"{{{XHTML_NS}}}div")
            wrapper.set("class", "illustration")
            image = etree.SubElement(wrapper, f"{{{XHTML_NS}}}img")
            image.set("src", href)
            image.set("alt", "")
            content_nodes.append(wrapper)
        else:
            raise RuntimeError(f"unknown content type: {item['type']}")

    tree = make_xhtml(title, content_nodes)
    tree.write(str(target), encoding="utf-8", xml_declaration=True, doctype="<!DOCTYPE html>", pretty_print=True)
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
    try:
        result = rebuild(Path(sys.argv[1]), Path(sys.argv[2]))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(0 if result >= 0 else 1)


if __name__ == "__main__":
    main()
