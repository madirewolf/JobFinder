"""Profile ingest: chunk → embed → aggregate.

Reads markdown files under `profile/` (resume, portfolio, projects, prefs),
splits them into overlapping chunks, embeds each via Ollama, inserts them
into `portfolio_chunks`, and computes a single aggregate "primary" profile
vector in `profile_vectors` used downstream for cosine-gated candidate
selection before Haiku triage.

Convention for `portfolio_chunks.source`:
    "resume" | "portfolio" | "project:<slug>" | "prefs" | "notes"

`project` column holds the project slug (file stem) when source is `project:*`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import aconn
from ..logging_config import get_logger
from .chunking import Chunk, chunk_text
from .embeddings import embed_batch, format_for_pgvector

log = get_logger(__name__)

DEFAULT_PROFILE_DIR = Path("profile")


@dataclass(slots=True)
class IngestReport:
    files_processed: int
    chunks_inserted: int
    aggregate_written: bool


def _classify_source(path: Path) -> tuple[str, str | None]:
    """Derive (source, project) from a file's location.

    Rules, checked top-down:
      - file named `resume.md` → ("resume", None)
      - file named `prefs.md`  → ("prefs", None)
      - file in a `projects/` dir → ("project:<stem>", <stem>)
      - anything else          → ("portfolio", None)
    """
    stem = path.stem.lower()
    if stem == "resume":
        return "resume", None
    if stem in {"prefs", "preferences"}:
        return "prefs", None
    parts = {p.lower() for p in path.parts}
    if "projects" in parts:
        return f"project:{stem}", stem
    return "portfolio", None


def _is_example_or_doc(path: Path) -> bool:
    """True if this markdown file is an example template or directory README.

    Skips:
      - README.md anywhere under profile/ (documentation, not portfolio content)
      - <name>.example.md  (e.g. resume.example.md, prefs.example.md)
      - example-*.md, example_*.md  (e.g. projects/example-nerf-demo.md)

    Without this filter, the example template content (Jane Doe / vimy-nerf
    placeholder) lands in `portfolio_chunks` and pollutes the centroid that
    drives both retrieval and the gate-by-cosine triage step.
    """
    name = path.name.lower()
    stem = path.stem.lower()
    if name == "readme.md":
        return True
    if stem.endswith(".example"):
        return True
    if stem.startswith("example-") or stem.startswith("example_"):
        return True
    return False


def _collect_markdown(root: Path) -> list[Path]:
    """Return all markdown files under `root`, sorted for determinism.

    Excludes README.md and example/template files (see `_is_example_or_doc`).
    """
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*.md")
        if p.is_file() and not _is_example_or_doc(p)
    )


async def _clear_portfolio(conn) -> None:
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE portfolio_chunks RESTART IDENTITY")


async def _insert_chunk(
    conn,
    *,
    source: str,
    project: str | None,
    chunk: Chunk,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO portfolio_chunks (source, project, content, embedding, metadata)
            VALUES (%s, %s, %s, %s::vector, %s::jsonb)
            """,
            (
                source,
                project,
                chunk.text,
                format_for_pgvector(embedding),
                _json_dumps(metadata),
            ),
        )


async def _upsert_profile_vector(
    conn,
    *,
    label: str,
    centroid: list[float],
    source_meta: dict[str, Any],
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO profile_vectors (label, embedding, source_meta)
            VALUES (%s, %s::vector, %s::jsonb)
            ON CONFLICT (label) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    source_meta = EXCLUDED.source_meta,
                    updated_at = now()
            """,
            (label, format_for_pgvector(centroid), _json_dumps(source_meta)),
        )


def _centroid(vectors: list[list[float]]) -> list[float]:
    """Unnormalized mean of the input vectors. Cosine similarity is scale-invariant
    so normalization is unnecessary; pgvector's `<=>` handles it.
    """
    if not vectors:
        raise ValueError("_centroid requires at least one vector")
    dim = len(vectors[0])
    total = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            raise ValueError(f"dim mismatch: got {len(v)}, expected {dim}")
        for i, x in enumerate(v):
            total[i] += x
    n = len(vectors)
    return [x / n for x in total]


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


async def ingest_profile(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    *,
    label: str = "primary",
    replace: bool = True,
) -> IngestReport:
    """Ingest every `*.md` under `profile_dir`.

    Args:
      profile_dir: root of the profile tree (default ./profile)
      label:       identity key written into profile_vectors (default 'primary')
      replace:     TRUNCATE portfolio_chunks before inserting (default True)

    Returns a report with counts so the CLI can print a tidy summary.
    """
    files = _collect_markdown(profile_dir)
    if not files:
        log.warning("profile.ingest.no_files", dir=str(profile_dir))
        return IngestReport(files_processed=0, chunks_inserted=0, aggregate_written=False)

    all_chunks: list[tuple[str, str | None, Chunk, dict[str, Any]]] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        source, project = _classify_source(f)
        for c in chunk_text(raw):
            meta = {"path": str(f.relative_to(profile_dir)), "char_len": len(c.text)}
            all_chunks.append((source, project, c, meta))

    if not all_chunks:
        log.warning("profile.ingest.empty_after_chunk", files=len(files))
        return IngestReport(files_processed=len(files), chunks_inserted=0, aggregate_written=False)

    texts = [c.text for (_, _, c, _) in all_chunks]
    log.info("profile.ingest.embedding", files=len(files), chunks=len(texts))
    vectors = await embed_batch(texts, concurrency=4)

    async with aconn() as conn:
        if replace:
            await _clear_portfolio(conn)
        for (source, project, chunk, meta), vec in zip(all_chunks, vectors, strict=True):
            await _insert_chunk(
                conn,
                source=source,
                project=project,
                chunk=chunk,
                embedding=vec,
                metadata=meta,
            )

        centroid = _centroid(vectors)
        await _upsert_profile_vector(
            conn,
            label=label,
            centroid=centroid,
            source_meta={
                "files": [str(f.relative_to(profile_dir)) for f in files],
                "chunk_count": len(vectors),
            },
        )
        await conn.commit()

    log.info(
        "profile.ingest.ok",
        files=len(files),
        chunks=len(vectors),
        label=label,
    )
    return IngestReport(
        files_processed=len(files),
        chunks_inserted=len(vectors),
        aggregate_written=True,
    )
