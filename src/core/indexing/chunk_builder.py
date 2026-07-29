"""ChunkBuilder for the EP-019 Project Index Engine.

Splits one document's text into an ordered tuple of immutable
`DocumentChunk`s. Responsible only for splitting -- no file I/O, no
manifest awareness, no AI logic.

Splitting strategy, in order of preference:
    1. Never cross a Markdown heading boundary within one chunk --
       each heading starts a fresh section.
    2. Within a section, split on paragraph boundaries (blank lines).
    3. If a single paragraph is still larger than `chunk_size`, split
       it on sentence boundaries.
    4. If a single sentence is still larger than `chunk_size`, split
       it on whitespace, packing whole words up to `chunk_size`.
    5. A word is never split, even if it alone exceeds `chunk_size`
       (an unavoidable exception to the size target -- "never split
       words" always wins).

Chunks within the same section overlap by up to `overlap` characters
of trailing context, carried into the next chunk. No chunk is ever
empty.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from src.core.indexing.chunk import DocumentChunk

__all__ = ["ChunkBuilder"]

_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\S+")

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 100


class ChunkBuilder:
    """Splits document text into immutable, ordered `DocumentChunk`s.

    Thread-safe: holds only its own configuration (`chunk_size`,
    `overlap`), which is set once at construction and never mutated.
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> None:
        """Initialize a ChunkBuilder.

        Args:
            chunk_size: Target maximum characters per chunk.
            overlap: Target characters of trailing context carried
                from one chunk into the next.

        Raises:
            ValueError: If `chunk_size` is not positive, `overlap` is
                negative, or `overlap` is not smaller than `chunk_size`.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if overlap < 0:
            raise ValueError("overlap must not be negative.")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size.")
        self._chunk_size = chunk_size
        self._overlap = overlap

    @property
    def chunk_size(self) -> int:
        """Return the configured target maximum characters per chunk."""
        return self._chunk_size

    @property
    def overlap(self) -> int:
        """Return the configured target overlap, in characters."""
        return self._overlap

    def build(self, document_id: str, relative_path: str, text: str) -> tuple[DocumentChunk, ...]:
        """Split `text` into an ordered tuple of immutable `DocumentChunk`s.

        Args:
            document_id: Identifier of the owning document, used as
                the prefix for every produced chunk's `chunk_id`.
            relative_path: The owning document's repository-relative
                path, copied onto every produced chunk.
            text: The document's full text content.

        Returns:
            An ordered tuple of chunks. Empty if `text` is empty or
            whitespace-only.
        """
        if not text or not text.strip():
            return ()

        line_offsets = _line_start_offsets(text)
        chunks: list[DocumentChunk] = []
        sequence = 0

        for heading, section_start, section_end in _heading_sections(text):
            if not text[section_start:section_end].strip():
                continue
            units = _atomic_units(text, section_start, section_end, self._chunk_size)
            for chunk_text, chunk_start, chunk_end in _pack_units(units, text, self._chunk_size, self._overlap):
                start_line = _line_number(line_offsets, chunk_start)
                end_line = _line_number(line_offsets, max(chunk_start, chunk_end - 1))
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{document_id}:{sequence:04d}",
                        document_id=document_id,
                        relative_path=relative_path,
                        heading=heading,
                        text=chunk_text,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )
                sequence += 1

        return tuple(chunks)


# ---------- Internal helpers ----------


def _line_start_offsets(text: str) -> list[int]:
    """Return the character offset each line (0-indexed) begins at."""
    offsets = [0]
    for match in re.finditer("\n", text):
        offsets.append(match.end())
    return offsets


def _line_number(line_offsets: list[int], char_offset: int) -> int:
    """Return the 1-based line number containing `char_offset`."""
    index = bisect_right(line_offsets, char_offset) - 1
    return max(0, index) + 1


def _heading_sections(text: str) -> list[tuple[str, int, int]]:
    """Split `text` into (heading, start, end) sections at each Markdown heading.

    A heading's section spans from its own heading line up to (but
    not including) the next heading. Content before the first heading
    (or the entire document, if it has no headings) is one section
    with heading "".
    """
    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        return [("", 0, len(text))]

    sections: list[tuple[str, int, int]] = []
    if matches[0].start() > 0:
        sections.append(("", 0, matches[0].start()))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(2).strip(), match.start(), end))
    return sections


def _atomic_units(text: str, start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    """Return non-empty (start, end) offset pairs covering `text[start:end]`.

    Always descends to sentence granularity (the finest unit greedy
    packing and overlap carry-back operate on), splitting further into
    word-groups only when a single sentence itself still exceeds
    `chunk_size`; a unit that is a single word is returned whole even
    if it still exceeds `chunk_size` (words are never split). Sentences
    belonging to the same paragraph remain adjacent in the returned
    list, so greedy packing naturally keeps a short paragraph whole.
    """
    units: list[tuple[int, int]] = []
    for paragraph_start, paragraph_end in _split_on(text, start, end, _PARAGRAPH_BOUNDARY):
        for sentence_start, sentence_end in _split_on(text, paragraph_start, paragraph_end, _SENTENCE_BOUNDARY):
            if sentence_end - sentence_start <= chunk_size:
                units.append((sentence_start, sentence_end))
            else:
                units.extend(_split_words(text, sentence_start, sentence_end, chunk_size))
    return units


def _split_on(text: str, start: int, end: int, boundary: re.Pattern[str]) -> list[tuple[int, int]]:
    """Split `text[start:end]` at every match of `boundary`, dropping empty/whitespace-only pieces."""
    segment = text[start:end]
    pieces: list[tuple[int, int]] = []
    cursor = 0
    for match in boundary.finditer(segment):
        piece = segment[cursor : match.start()]
        if piece.strip():
            pieces.append((start + cursor, start + match.start()))
        cursor = match.end()
    tail = segment[cursor:]
    if tail.strip():
        pieces.append((start + cursor, end))
    if not pieces and segment.strip():
        pieces.append((start, end))
    return pieces


def _split_words(text: str, start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    """Pack whitespace-delimited words from `text[start:end]` up to `chunk_size`, never splitting a word."""
    segment = text[start:end]
    words = [(match.start(), match.end()) for match in _WORD.finditer(segment)]
    if not words:
        return []

    pieces: list[tuple[int, int]] = []
    group_start, group_end = words[0]
    for word_start, word_end in words[1:]:
        if word_end - group_start <= chunk_size:
            group_end = word_end
        else:
            pieces.append((start + group_start, start + group_end))
            group_start, group_end = word_start, word_end
    pieces.append((start + group_start, start + group_end))
    return pieces


def _pack_units(
    units: list[tuple[int, int]], text: str, chunk_size: int, overlap: int
) -> list[tuple[str, int, int]]:
    """Greedily group atomic units into chunks up to `chunk_size`, overlapping consecutive chunks by up to `overlap`."""
    if not units:
        return []

    packed: list[tuple[str, int, int]] = []
    total = len(units)
    index = 0

    while index < total:
        chunk_start = units[index][0]
        last = index
        chunk_end = units[index][1]
        while last + 1 < total and (units[last + 1][1] - chunk_start) <= chunk_size:
            last += 1
            chunk_end = units[last][1]

        chunk_text = text[chunk_start:chunk_end]
        if chunk_text.strip():
            packed.append((chunk_text, chunk_start, chunk_end))

        if last + 1 >= total:
            break

        next_index = last + 1
        if overlap > 0:
            carry = last
            while carry > index and (chunk_end - units[carry][0]) <= overlap:
                carry -= 1
            if (chunk_end - units[carry][0]) > overlap:
                carry += 1
            if index < carry <= last:
                next_index = carry
        index = next_index

    return packed
