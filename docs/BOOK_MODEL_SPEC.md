# Book Model & Standard Ebook Specification v1.0

## Scope

This specification defines only the input-to-standard-ebook pipeline. Translation is a separate system and is not part of this model.

## Core model

```text
Book
├── Metadata
├── Volume 1
│   ├── Chapter 1
│   │   ├── Part 1
│   │   └── Part 2
│   ├── Chapter 2
│   └── ...
├── Volume 2
│   └── ...
└── ...
```

The canonical hierarchy is:

```text
Book → Volume → Chapter → Part
```

Every `Book` has at least one `Volume`. If the source does not explicitly contain volumes, the parser creates `Volume 1`.

`Part` is an internal source-fragment representation. It exists to preserve source ordering and provenance, but it is not a user-facing chapter and does not create an additional TOC entry by itself.

## Language neutrality

The standardization pipeline is language-neutral. Structural parsing must not depend on the source language. Language is metadata, not a routing condition.

## Input processing

```text
Input
  ↓
Format detection
  ↓
Format parser
  ↓
Structural analysis
  ↓
Canonical Book Model
  ↓
User review / correction
  ↓
Output mode
  ├── Separate Volumes
  └── Combined Edition
  ↓
Standard EPUB Generator
```

A physical input file is not assumed to equal one book, one volume, or one chapter.

## Structural analysis

The parser may use:

- source file order
- EPUB spine/order
- EPUB navigation and package metadata
- filenames
- headings
- volume/chapter markers
- metadata
- semantic HTML structure

Filename patterns are signals, not authoritative truth.

When the structure cannot be determined reliably, the system preserves the discovered source fragments and allows manual correction instead of silently discarding or inventing content.

## Chapters and source fragments

Multiple source files may form one chapter:

```text
chapter01-001.txt
chapter01-002.txt
chapter01-003.txt
```

becomes:

```text
Volume 1
└── Chapter 1
    ├── Part 1
    ├── Part 2
    └── Part 3
```

When generating the standard EPUB, these parts are rendered as one continuous Chapter unless the source contains an actual semantic section boundary that should remain visible.

## Unknown structure

Unknown or ambiguous source material must remain representable in the Book Model. The first implementation may expose this through a machine-readable structure/preview rather than a full GUI editor.

The user must be able to correct volume/chapter assignment before generation.

## Standard EPUB

All output books use one generator and one standard stylesheet/layout.

The generator preserves semantic content from the source while replacing the source presentation layer.

Preserve where available:

- metadata
- headings
- paragraphs
- emphasis/strong text
- links
- lists
- tables
- block quotes
- images
- image placement
- meaningful semantic structure

Do not depend on preserving:

- original CSS
- original fonts
- original margins
- original page-break styling
- original HTML class names
- source-specific presentation positioning

## Images

Original book images are part of the canonical content and must be retained when available. The generator copies the required assets into the standard EPUB and applies the standard layout around them.

## Output modes

### Separate Volumes

```text
Book Vol.1.epub
Book Vol.2.epub
Book Vol.3.epub
```

### Combined Edition

```text
Book Complete Edition.epub
```

The combined edition does not flatten the model. Volume boundaries remain visible in the EPUB structure and TOC:

```text
Volume 1
  Chapter 1
  Chapter 2
Volume 2
  Chapter 1
  Chapter 2
```

Both modes are generated from the same canonical Book Model.

## Design constraints

- Do not couple parsing to translation.
- Do not couple the Book Model to EPUB-specific presentation details.
- Do not add language-specific structural rules to the canonical model.
- Do not treat a filename convention as proof of book structure.
- Do not silently delete content that cannot be classified.
- Do not add compatibility layers for obsolete implementations; the new model is the source of truth.
