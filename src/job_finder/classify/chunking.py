"""Recursive text chunker for portfolio ingestion.

Target: ~512 tokens per chunk with 50-token overlap (per spec §5.1).
Token counts are approximated at 4 chars/token — cheap, no tokenizer dep.

Split hierarchy (splits on the first separator that produces child pieces
all smaller than the target):
    '\\n\\n'  →  paragraphs
    '\\n'    →  lines
    '. '     →  sentences
    ' '      →  words
    ''       →  character-level last resort
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_TOKENS = 512
DEFAULT_OVERLAP_TOKENS = 50

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


@dataclass(slots=True)
class Chunk:
    text: str
    start: int  # char offset in the source string
    end: int


def chunk_text(
    text: str,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split `text` into overlapping chunks near the target token size.

    Chunks are contiguous with the next one overlapping by `overlap_tokens`
    worth of characters, to preserve cross-boundary context for retrieval.
    """
    if not text or not text.strip():
        return []

    max_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    pieces = _recursive_split(text, max_chars, SEPARATORS)
    merged = _merge_small(pieces, max_chars)

    # Add overlap between adjacent chunks
    out: list[Chunk] = []
    for i, piece in enumerate(merged):
        if i == 0:
            out.append(piece)
            continue
        prev = out[-1]
        lookback_start = max(prev.start, prev.end - overlap_chars)
        overlap_text = text[lookback_start:prev.end]
        new_text = overlap_text + piece.text if overlap_text else piece.text
        out.append(Chunk(text=new_text, start=lookback_start, end=piece.end))

    return out


def _recursive_split(text: str, max_chars: int, seps: list[str]) -> list[Chunk]:
    """Split with the first separator that produces sub-pieces all ≤ max_chars.

    Returns non-overlapping `Chunk`s covering the input. Leaves small pieces
    intact; `_merge_small` will glue adjacent ones back together.
    """
    if len(text) <= max_chars:
        return [Chunk(text=text, start=0, end=len(text))]

    for sep in seps:
        if sep == "":
            # Fallback: hard character split
            out: list[Chunk] = []
            for i in range(0, len(text), max_chars):
                out.append(Chunk(text=text[i : i + max_chars], start=i, end=min(i + max_chars, len(text))))
            return out

        if sep not in text:
            continue

        # Split while preserving offsets
        cursor = 0
        sub_pieces: list[Chunk] = []
        for fragment in text.split(sep):
            # re-append separator to all but the last fragment so offsets match
            kept = fragment + sep
            end = cursor + len(kept)
            sub_pieces.append(Chunk(text=kept, start=cursor, end=end))
            cursor = end
        # The very last fragment doesn't have the separator
        if sub_pieces:
            last = sub_pieces[-1]
            real_text = last.text.removesuffix(sep) if last.text.endswith(sep) else last.text
            sub_pieces[-1] = Chunk(text=real_text, start=last.start, end=last.start + len(real_text))

        # If every sub-piece fits, we're done splitting at this level
        if all(len(p.text) <= max_chars for p in sub_pieces):
            return [p for p in sub_pieces if p.text.strip()]

        # Otherwise recurse on oversize pieces
        result: list[Chunk] = []
        for p in sub_pieces:
            if len(p.text) <= max_chars:
                if p.text.strip():
                    result.append(p)
            else:
                deeper = _recursive_split(p.text, max_chars, seps[seps.index(sep) + 1 :])
                # Rebase offsets into the parent coordinate system
                for d in deeper:
                    result.append(Chunk(text=d.text, start=p.start + d.start, end=p.start + d.end))
        return result

    return [Chunk(text=text, start=0, end=len(text))]  # pragma: no cover


def _merge_small(pieces: Iterable[Chunk], max_chars: int) -> list[Chunk]:
    """Glue small adjacent pieces until each merged chunk is near `max_chars`."""
    out: list[Chunk] = []
    for p in pieces:
        if not out:
            out.append(p)
            continue
        last = out[-1]
        merged_len = (p.end - last.start)
        if merged_len <= max_chars:
            out[-1] = Chunk(
                text=last.text + (" " if not last.text.endswith((" ", "\n")) else "") + p.text,
                start=last.start,
                end=p.end,
            )
        else:
            out.append(p)
    return out


def approx_tokens(text: str) -> int:
    """Cheap length estimate in ~tokens."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN
