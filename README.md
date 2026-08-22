# EbookTranslator

A two-stage ebook processing tool:

1. **Input → Standard Ebook**: normalize source books into deterministic, chapter-based EPUB files.
2. **Standard Ebook → Translation**: translation is a separate stage and is not part of input normalization.

The first stage is **language-neutral**. It must not assume Japanese, English, Chinese, or any other source language.

## Standardization prototype

The current prototype accepts:

- `.txt`
- `.epub`

Run:

```text
python scripts/standardize_book.py <input.txt|input.epub> <output-dir>
```

The result is one or more standardized EPUB files. Each EPUB contains one XHTML document per detected chapter and uses a fixed, minimal EPUB structure and stylesheet.

If an input contains explicit volume markers such as `第1巻`, `第2巻`, `Vol. 1`, `Volume 2`, or `Book 3`, the prototype groups the chapters into separate volume EPUBs instead of treating the omnibus as one book.

A single input file therefore does not automatically mean a single output book.

## Language neutrality

Input parsing and standardization do not perform language detection or Japanese-only filtering. The same pipeline is intended to accept books in any language.

Language-specific rules belong to the later translation stage.

## Existing translation workflow

The existing translation components remain separate from the new standardization prototype. Translation will be redesigned after the standardization/volume-splitting behavior has been tested against real input books.
