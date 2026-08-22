"""Canonical, language-neutral book model for the standardization pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OutputMode(str, Enum):
    SEPARATE = "separate"
    COMBINED = "combined"


@dataclass
class Metadata:
    title: str = ""
    author: str = ""
    language: str | None = None
    publisher: str | None = None
    identifier: str | None = None
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentBlock:
    """Semantic content preserved from the source presentation."""

    kind: str
    content: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None


@dataclass
class Part:
    """A source fragment belonging to one logical chapter."""

    source_path: str
    blocks: list[ContentBlock] = field(default_factory=list)


@dataclass
class Chapter:
    number: int | None
    title: str
    parts: list[Part] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Volume:
    number: int
    title: str
    chapters: list[Chapter] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Book:
    metadata: Metadata
    volumes: list[Volume] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)

    def ensure_volume(self) -> Volume:
        """Return Volume 1 when the source has no explicit volume."""
        if not self.volumes:
            self.volumes.append(Volume(number=1, title="Volume 1"))
        return self.volumes[0]

    def validate(self) -> None:
        if not self.volumes:
            raise ValueError("Book must contain at least one volume")

        seen_volumes: set[int] = set()
        for volume in self.volumes:
            if volume.number in seen_volumes:
                raise ValueError(f"Duplicate volume number: {volume.number}")
            seen_volumes.add(volume.number)

            for chapter in volume.chapters:
                if not chapter.parts:
                    raise ValueError(
                        f"Chapter {chapter.number or chapter.title!r} has no source parts"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": {
                "title": self.metadata.title,
                "author": self.metadata.author,
                "language": self.metadata.language,
                "publisher": self.metadata.publisher,
                "identifier": self.metadata.identifier,
                "description": self.metadata.description,
                "extra": self.metadata.extra,
            },
            "volumes": [
                {
                    "number": volume.number,
                    "title": volume.title,
                    "metadata": volume.metadata,
                    "chapters": [
                        {
                            "number": chapter.number,
                            "title": chapter.title,
                            "metadata": chapter.metadata,
                            "parts": [
                                {
                                    "source_path": part.source_path,
                                    "blocks": [
                                        {
                                            "kind": block.kind,
                                            "content": block.content,
                                            "attributes": block.attributes,
                                            "source_path": block.source_path,
                                        }
                                        for block in part.blocks
                                    ],
                                }
                                for part in chapter.parts
                            ],
                        }
                        for chapter in volume.chapters
                    ],
                }
                for volume in self.volumes
            ],
            "source_files": self.source_files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Book":
        metadata_data = data.get("metadata", {})
        metadata = Metadata(**metadata_data)

        volumes: list[Volume] = []
        for volume_data in data.get("volumes", []):
            chapters: list[Chapter] = []
            for chapter_data in volume_data.get("chapters", []):
                parts: list[Part] = []
                for part_data in chapter_data.get("parts", []):
                    blocks = [ContentBlock(**block) for block in part_data.get("blocks", [])]
                    parts.append(Part(source_path=part_data["source_path"], blocks=blocks))
                chapters.append(
                    Chapter(
                        number=chapter_data.get("number"),
                        title=chapter_data.get("title", ""),
                        parts=parts,
                        metadata=chapter_data.get("metadata", {}),
                    )
                )
            volumes.append(
                Volume(
                    number=volume_data["number"],
                    title=volume_data.get("title", ""),
                    chapters=chapters,
                    metadata=volume_data.get("metadata", {}),
                )
            )

        return cls(
            metadata=metadata,
            volumes=volumes,
            source_files=data.get("source_files", []),
        )


def normalize_source_path(path: str | Path) -> str:
    """Keep source provenance stable without making it OS-specific."""
    return Path(path).as_posix()
