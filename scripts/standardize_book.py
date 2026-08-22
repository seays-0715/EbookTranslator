#!/usr/bin/env python3
"""Convert text/EPUB input into deterministic, chapter-based EPUB files.

This stage is deliberately language-neutral. Translation is not involved.
"""
from __future__ import annotations

import html
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

HTML_EXTS = {".xhtml", ".html", ".htm"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOLUME_PATTERNS = (
    re.compile(r"^(?:第\s*)?([0-9０-９]+)\s*(?:巻|冊)\s*$", re.I),
    re.compile(r"^(?:vol(?:ume)?\.?|book)\s*([0-9０-９]+)\s*$", re.I),
    re.compile(r"^(?:第\s*)?([0-9０-９]+)\s*(?:部)\s*$", re.I),
    re.compile(r"^(?:上巻|中巻|下巻|前編|後編)$", re.I),
)


@dataclass
class Chapter:
    title: str
    paragraphs: list[str]


@dataclass
class Volume:
    title: str
    chapters: list[Chapter]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_volume_title(title: str) -> bool:
    normalized = clean_text(title)
    return any(pattern.match(normalized) for pattern in VOLUME_PATTERNS)


def text_from_element(el: etree._Element) -> str:
    return clean_text("".join(el.itertext()))


def epub_spine_paths(root: Path) -> list[Path]:
    container = etree.parse(str(root / "META-INF" / "container.xml"))
    package_rel = container.xpath("string(/*[local-name()='container']/*[local-name()='rootfiles']/*[local-name()='rootfile']/@full-path)")
    if not package_rel:
        raise RuntimeError("EPUB package document not found")
    package_path = root / package_rel
    package_tree = etree.parse(str(package_path))
    manifest = {}
    for item in package_tree.xpath("//*[local-name()='manifest']/*[local-name()='item']"):
        manifest[item.get("id")] = item.get("href")
    base = package_path.parent
    result: list[Path] = []
    for ref in package_tree.xpath("//*[local-name()='spine']/*[local-name()='itemref']"):
        href = manifest.get(ref.get("idref"))
        if href:
            result.append((base / href.split("#", 1)[0]).resolve())
    return result


def parse_epub(epub: Path) -> tuple[str, list[Chapter]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "epub"
        with zipfile.ZipFile(epub) as zf:
            zf.extractall(root)
        if (root / "mimetype").read_bytes() != b"application/epub+zip":
            raise RuntimeError("invalid EPUB mimetype")
        chapters: list[Chapter] = []
        for path in epub_spine_paths(root):
            if path.suffix.lower() not in HTML_EXTS or not path.is_file():
                continue
            tree = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True, recover=False))
            body = tree.xpath("//*[local-name()='body']")
            if not body:
                continue
            body = body[0]
            elements = []
            for el in body.iter():
                if not isinstance(el.tag, str):
                    continue
                local = etree.QName(el).localname.lower()
                if local in HEADING_TAGS:
                    title = text_from_element(el)
                    if title:
                        elements.append(("heading", title))
                elif local in {"p", "li", "blockquote", "dt", "dd", "pre", "figcaption"}:
                    text = text_from_element(el)
                    if text:
                        elements.append(("paragraph", text))
            current_title = path.stem
            current: list[str] = []
            for kind, text in elements:
                if kind == "heading" and current:
                    chapters.append(Chapter(current_title, current))
                    current = []
                    current_title = text
                elif kind == "heading":
                    current_title = text
                else:
                    current.append(text)
            if current:
                chapters.append(Chapter(current_title, current))
        title = epub_title(root, epub.stem)
    return title, chapters


def epub_title(root: Path, fallback: str) -> str:
    container = etree.parse(str(root / "META-INF" / "container.xml"))
    package_rel = container.xpath("string(/*[local-name()='container']/*[local-name()='rootfiles']/*[local-name()='rootfile']/@full-path)")
    if not package_rel:
        return fallback
    tree = etree.parse(str(root / package_rel))
    title = tree.xpath("string((//*[local-name()='metadata']/*[local-name()='title'])[1])")
    return clean_text(title) or fallback


def parse_txt(path: Path) -> tuple[str, list[Chapter]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    chapters: list[Chapter] = []
    current_title = "Chapter 1"
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if is_chapter_heading(stripped):
            if current:
                chapters.append(Chapter(current_title, current))
                current = []
            current_title = stripped
        else:
            current.append(clean_text(stripped))
    if current:
        chapters.append(Chapter(current_title, current))
    return path.stem, chapters


def is_chapter_heading(line: str) -> bool:
    return bool(re.match(r"^(?:第\s*[0-9０-９一二三四五六七八九十百千]+\s*(?:章|話|回)|chapter\s+[0-9]+|prologue|epilogue|序章|終章|序|終)$", line, re.I))


def split_volumes(book_title: str, chapters: list[Chapter]) -> list[Volume]:
    volumes: list[Volume] = []
    current_title = book_title
    current: list[Chapter] = []
    for chapter in chapters:
        if is_volume_title(chapter.title) and current:
            volumes.append(Volume(current_title, current))
            current_title = f"{book_title} {chapter.title}"
            current = []
            if chapter.paragraphs:
                current.append(Chapter(chapter.title, chapter.paragraphs))
        else:
            if not current and is_volume_title(chapter.title):
                current_title = f"{book_title} {chapter.title}"
            else:
                current.append(chapter)
    if current:
        volumes.append(Volume(current_title, current))
    return volumes or [Volume(book_title, chapters)]


def epub_page(title: str, paragraphs: list[str]) -> str:
    body = [f"<h1>{html.escape(title)}</h1>"]
    body.extend(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    return "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" \
        "<html xmlns=\"http://www.w3.org/1999/xhtml\" xml:lang=\"und\">\n" \
        "<head><meta charset=\"utf-8\"/><title>" + html.escape(title) + "</title>" \
        "<style>body{line-height:1.8;margin:1em;}h1{font-size:1.4em;}p{margin:0 0 1em;text-indent:1em;}</style></head>" \
        "<body>" + "".join(body) + "</body></html>"


def write_epub(volume: Volume, output: Path) -> None:
    work = output.parent / f".{output.stem}_build"
    if work.exists():
        shutil.rmtree(work)
    (work / "META-INF").mkdir(parents=True)
    (work / "OEBPS").mkdir(parents=True)
    (work / "mimetype").write_bytes(b"application/epub+zip")
    (work / "META-INF" / "container.xml").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">"
        "<rootfiles><rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>",
        encoding="utf-8",
    )
    manifest = ["<item id=\"ncx\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\"/>"]
    spine = []
    nav_points = []
    for index, chapter in enumerate(volume.chapters, 1):
        filename = f"chapter-{index:04d}.xhtml"
        (work / "OEBPS" / filename).write_text(epub_page(chapter.title, chapter.paragraphs), encoding="utf-8")
        manifest.append(f"<item id=\"c{index}\" href=\"{filename}\" media-type=\"application/xhtml+xml\"/>")
        spine.append(f"<itemref idref=\"c{index}\"/>")
        nav_points.append(f"<navPoint id=\"n{index}\" playOrder=\"{index}\"><navLabel><text>{html.escape(chapter.title)}</text></navLabel><content src=\"{filename}\"/></navPoint>")
    (work / "OEBPS" / "content.opf").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"2.0\" unique-identifier=\"bookid\">"
        f"<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><dc:identifier id=\"bookid\">standard-{abs(hash(volume.title))}</dc:identifier><dc:title>{html.escape(volume.title)}</dc:title><dc:language>und</dc:language></metadata>"
        f"<manifest>{''.join(manifest)}</manifest><spine toc=\"ncx\">{''.join(spine)}</spine></package>",
        encoding="utf-8",
    )
    (work / "OEBPS" / "toc.ncx").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">"
        f"<head><meta name=\"dtb:uid\" content=\"standard-{abs(hash(volume.title))}\"/></head><docTitle><text>{html.escape(volume.title)}</text></docTitle><navMap>{''.join(nav_points)}</navMap></ncx>",
        encoding="utf-8",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w") as zf:
        zf.write(work / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(work.rglob("*")):
            if path.is_file() and path.name != "mimetype":
                zf.write(path, path.relative_to(work).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
    shutil.rmtree(work)


def standardize(source: Path, output_dir: Path) -> list[Path]:
    suffix = source.suffix.lower()
    if suffix == ".txt":
        title, chapters = parse_txt(source)
    elif suffix == ".epub":
        title, chapters = parse_epub(source)
    else:
        raise ValueError(f"unsupported input format: {suffix or '<none>'}; currently supported: .txt, .epub")
    if not chapters:
        raise ValueError("no readable chapters found")
    volumes = split_volumes(title, chapters)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index, volume in enumerate(volumes, 1):
        suffix = f"_vol{index:02d}" if len(volumes) > 1 else ""
        output = output_dir / f"{source.stem}{suffix}.epub"
        write_epub(volume, output)
        outputs.append(output)
    return outputs


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: standardize_book.py <input.txt|input.epub> <output-dir>")
    outputs = standardize(Path(sys.argv[1]), Path(sys.argv[2]))
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
