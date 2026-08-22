# EbookTranslator

Ebook processing is divided into two independent stages:

1. **Input → Standard Ebook** — parse arbitrary ebook sources into a canonical, language-neutral `Book` model and generate a fixed-format EPUB.
2. **Standard Ebook → Translation** — a separate translation pipeline to be designed after the standardization stage is validated.

## Canonical Book Model

```text
Book
├── Metadata
├── Volume 1
│   ├── Chapter 1
│   │   ├── Part 1
│   │   └── Part 2
│   └── Chapter 2
└── Volume 2
    └── ...
```

The canonical hierarchy is:

```text
Book → Volume → Chapter → Part
```

Every book has at least one volume. When a source has no explicit volumes, the parser creates `Volume 1`.

`Part` represents source fragments used to assemble one logical chapter. Parts are not independent TOC entries in the generated EPUB.

See [`docs/BOOK_MODEL_SPEC.md`](docs/BOOK_MODEL_SPEC.md) for the complete specification.

## Standardization rules

- Input is language-neutral.
- A physical input file is not assumed to equal one book, volume, or chapter.
- Multiple source files may form one chapter.
- Source filename patterns are signals, not authoritative structure.
- Ambiguous structure must remain editable rather than silently losing content.
- Original semantic content and images are preserved where available.
- Original presentation CSS/layout is replaced by one standard generator and stylesheet.
- Users can choose **Separate Volumes** or **Combined Edition** after structural analysis.
- Combined editions preserve volume boundaries in the internal model and EPUB TOC.

## Current implementation state

The canonical model and v1.0 specification are now established. The existing prototype parser is intentionally not treated as the final architecture; the next implementation step is to rebuild parsing and EPUB generation around the canonical model instead of adding more format-specific patches.

Translation remains untouched until this standardization layer has been validated against real books, including omnibus editions and extracted EPUB directory structures.
