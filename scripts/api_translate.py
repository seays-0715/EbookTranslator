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
DEFAULT_PROMPT = """你是一名專業的文學翻譯者。
將提供的原文翻譯成自然、流暢的繁體中文。
保留每一個 paragraph ID 完全不變。不可新增、刪除、改名、修改或重新排列 ID。
只翻譯各 ID 下的文字，不要加入說明、Markdown code fence 或其他評論。
保留原有的段落邊界、對話符號、標點及有意義的換行。
輸出必須只有相同的 [ID] 標題及其繁體中文翻譯。"""
DEFAULT_POLISH_PROMPT = """在不改變原意、人物語氣、專有名詞及段落結構的前提下，潤色繁體中文，使其更自然、流暢，符合小說閱讀習慣。不要重新翻譯，不要新增內容。"""


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


def build_system_prompt(prompt: str, glossary: str, polish: bool, polish_prompt: str) -> str:
    parts = [prompt.strip() or DEFAULT_PROMPT]
    if glossary.strip():
        parts.append("\n全局 Glossary（必須遵守；優先於一般翻譯習慣）：\n" + glossary.strip())
    if polish:
        parts.append("\n翻譯完成後，請再執行一次以下潤色要求：\n" + (polish_prompt.strip() or DEFAULT_POLISH_PROMPT))
    return "\n".join(parts)


def call_api(base_url: str, api_key: str, model: str, records: list[tuple[str, str]], system_prompt: str) -> list[tuple[str, str]]:
    payload_text = "\n\n".join(f"[{pid}]\n{text}" for pid, text in records)
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
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


def translate_records(records, base_url, api_key, model, max_chars=24000, system_prompt=DEFAULT_PROMPT):
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
        translated.extend(call_api(base_url, api_key, model, chunk, system_prompt))
    return translated, len(chunks)


def translate_book(
    book: Path,
    translating_root: Path,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 24000,
    prompt: str = DEFAULT_PROMPT,
    glossary: str = "",
    polish: bool = False,
    polish_prompt: str = DEFAULT_POLISH_PROMPT,
    selected_files: set[str] | None = None,
) -> tuple[int, int]:
    manifest = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    output_root = translating_root / manifest["book"]
    system_prompt = build_system_prompt(prompt, glossary, polish, polish_prompt)
    files = 0
    chunks = 0
    for file in manifest["files"]:
        relative_text = str(Path(file["text"]).relative_to("text")).replace("\\", "/")
        if selected_files is not None and relative_text not in selected_files:
            continue
        source = book / file["text"]
        if not source.is_file() or not file["paragraph_count"]:
            continue
        records = parse_txt(source)
        translated, used_chunks = translate_records(records, base_url, api_key, model, max_chars, system_prompt)
        relative = Path(file["text"]).relative_to("text")
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n\n".join(f"[{pid}]\n{text}" for pid, text in translated) + "\n", encoding="utf-8")
        files += 1
        chunks += used_chunks
    return files, chunks
