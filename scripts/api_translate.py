#!/usr/bin/env python3
"""Translate extracted TXT through an OpenAI-compatible chat-completions API."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
HEADER = re.compile(r"^\[([^\]]+)\]$")

SYSTEM_PROMPT = """You are a professional literary translator.
Translate the supplied source text into Traditional Chinese (繁體中文).
Preserve every paragraph ID exactly. Do not add, remove, rename, reorder, or modify IDs.
Only translate the text under each ID. Do not add explanations, markdown fences, or commentary.
Keep punctuation, dialogue marks, paragraph boundaries, and intentional line breaks as naturally as possible.
Return exactly the same [ID] headers followed by their translated text."""


def parse_txt(path: Path) -> list[tuple[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    current = None
    body: list[str] = []
    for line in lines:
        match = HEADER.match(line.strip())
        if match:
            if current is not None:
                records.append((current, "\n".join(body).strip()))
            current = match.group(1)
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        records.append((current, "\n".join(body).strip()))
    return records


def parse_response(text: str) -> list[tuple[str, str]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)
    lines = text.splitlines()
    records = []
    current = None
    body: list[str] = []
    for line in lines:
        match = HEADER.match(line.strip())
        if match:
            if current is not None:
                records.append((current, "\n".join(body).strip()))
            current = match.group(1)
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        records.append((current, "\n".join(body).strip()))
    return records


def endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def call_api(base_url: str, api_key: str, model: str, records: list[tuple[str, str]]) -> list[tuple[str, str]]:
    payload_text = "\n\n".join(f"[{pid}]\n{text}" for pid, text in records)
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": payload_text},
        ],
    }
    request = urllib.request.Request(
        endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            result = parse_response(content)
            expected = [pid for pid, _ in records]
            actual = [pid for pid, _ in result]
            if actual != expected:
                raise RuntimeError(f"API returned incorrect IDs/order: expected {len(expected)}, got {len(actual)}")
            if any(not text for _, text in result):
                raise RuntimeError("API returned an empty translation")
            if any(JP.search(text) for _, text in result):
                raise RuntimeError("Japanese residue detected in API response")
            return result
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"API translation failed: {last_error}")


def translate_records(records, base_url, api_key, model, max_chars=24000):
    chunks = []
    current = []
    size = 0
    for record in records:
        record_size = len(record[0]) + len(record[1]) + 8
        if current and size + record_size > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append(record)
        size += record_size
    if current:
        chunks.append(current)
    translated = []
    for chunk in chunks:
        translated.extend(call_api(base_url, api_key, model, chunk))
    return translated, len(chunks)


def translate_book(book: Path, translating_root: Path, base_url: str, api_key: str, model: str, max_chars: int = 24000) -> tuple[int, int]:
    manifest = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    output_root = translating_root / manifest["book"]
    files = 0
    chunks = 0
    for file in manifest["files"]:
        source = book / file["text"]
        if not source.is_file() or not file["paragraph_count"]:
            continue
        records = parse_txt(source)
        translated, used_chunks = translate_records(records, base_url, api_key, model, max_chars)
        relative = Path(file["text"]).relative_to("text")
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n\n".join(f"[{pid}]\n{text}" for pid, text in translated) + "\n", encoding="utf-8")
        files += 1
        chunks += used_chunks
    return files, chunks
