"""
Embedding storage backends.

Two formats are supported and can be produced in the same run:

* **Parquet** -- one file per modality, each row contains the embedding
  vector alongside its KG linkage metadata (entity_id, kg_uri,
  source_url, filename, model_id).  A companion TTL file is generated
  that extends the KG with ``imdb4m:*Embedding*`` triples.

* **HDF5** -- a single master ``.h5`` file with one group per modality.
  Inside each group: ``embeddings`` dataset (N x D float32), plus 1-D
  string datasets for every metadata column.  Attributes on each group
  record the model id and embedding dimension.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import (
    IMAGE_MODEL_ID,
    VIDEO_MODEL_ID,
    AUDIO_MODEL_ID,
    TEXT_MODEL_ID,
    IMAGE_EMBED_DIM,
    VIDEO_EMBED_DIM,
    AUDIO_EMBED_DIM,
    TEXT_EMBED_DIM,
)
from .scanner import MediaItem

logger = logging.getLogger(__name__)

# Modality -> (model_id, embed_dim)
_MODALITY_META: Dict[str, Tuple[str, int]] = {
    "image": (IMAGE_MODEL_ID, IMAGE_EMBED_DIM),
    "video": (VIDEO_MODEL_ID, VIDEO_EMBED_DIM),
    "audio": (AUDIO_MODEL_ID, AUDIO_EMBED_DIM),
    "text": (TEXT_MODEL_ID, TEXT_EMBED_DIM),
}
_MODALITY_ORDER = ("image", "video", "audio", "text")


# ======================================================================
# In-memory accumulator (shared by both writers)
# ======================================================================

class EmbeddingAccumulator:
    """
    Collects ``(MediaItem, np.ndarray)`` pairs in RAM and flushes them
    to one or both storage backends on demand.
    """

    def __init__(self) -> None:
        self._items: Dict[str, List[MediaItem]] = {m: [] for m in _MODALITY_ORDER}
        self._embeddings: Dict[str, List[np.ndarray]] = {m: [] for m in _MODALITY_ORDER}

    def add(self, item: MediaItem, embedding: np.ndarray) -> None:
        self._items[item.modality].append(item)
        self._embeddings[item.modality].append(embedding)

    def count(self, modality: Optional[str] = None) -> int:
        if modality:
            return len(self._items[modality])
        return sum(len(v) for v in self._items.values())

    def get(self, modality: str) -> Tuple[List[MediaItem], np.ndarray]:
        items = self._items[modality]
        if not items:
            return items, np.empty((0,))
        # Use vstack + ascontiguousarray so the result shares memory when
        # the individual arrays are already contiguous 1-D float32 vectors.
        embeddings = np.vstack(self._embeddings[modality])
        return items, embeddings

    @property
    def modalities(self) -> List[str]:
        return [m for m in _MODALITY_ORDER if self._items[m]]


# ======================================================================
# Parquet writer
# ======================================================================

def write_parquet(
    accumulator: EmbeddingAccumulator,
    output_dir: str,
) -> List[str]:
    """
    Write one Parquet file per modality into *output_dir*.

    Returns the list of written file paths.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: List[str] = []

    for modality in accumulator.modalities:
        items, embeddings = accumulator.get(modality)
        if len(items) == 0:
            continue

        model_id, _ = _MODALITY_META[modality]
        n = len(items)

        entity_ids = [it.entity_id for it in items]
        kg_uris = [it.kg_uri for it in items]
        source_urls = [it.source_url for it in items]
        filenames = [it.filename for it in items]
        model_ids = [model_id] * n

        # Wrap the (N, D) numpy matrix as a fixed-size-list column directly,
        # avoiding a .tolist() that would expand every float32 into a ~28-byte
        # Python float and blow up memory by ~7x.
        embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[0] != n:
            raise ValueError(
                f"Expected ({n}, D) embeddings, got shape {embeddings.shape}"
            )
        actual_dim = embeddings.shape[1]
        flat = pa.array(embeddings.reshape(-1), type=pa.float32())
        emb_column = pa.FixedSizeListArray.from_arrays(flat, actual_dim)

        table = pa.table(
            {
                "entity_id": entity_ids,
                "kg_uri": kg_uris,
                "source_url": source_urls,
                "filename": filenames,
                "model_id": model_ids,
                "embedding": emb_column,
            }
        )

        fpath = out / f"{modality}_embeddings.parquet"
        pq.write_table(table, str(fpath), compression="zstd")
        logger.info("Wrote %d %s embeddings to %s", len(items), modality, fpath)
        written.append(str(fpath))

    return written


# ======================================================================
# HDF5 writer (single master file)
# ======================================================================

def write_hdf5(
    accumulator: EmbeddingAccumulator,
    output_dir: str,
    filename: str = "embeddings.h5",
) -> Optional[str]:
    """
    Write all modalities into a single HDF5 master file.

    Structure::

        /image/
            embeddings   (N, 768)  float32
            entity_id    (N,)      UTF-8 string
            kg_uri       (N,)      UTF-8 string
            source_url   (N,)      UTF-8 string
            filename     (N,)      UTF-8 string
          attrs: model_id, embed_dim, count, created_at
        /video/  ...
        /audio/  ...
      attrs: created_at

    Returns the written file path, or ``None`` if nothing was written.
    """
    import h5py

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fpath = out / filename

    if not accumulator.modalities:
        return None

    with h5py.File(str(fpath), "a") as hf:
        if "created_at" not in hf.attrs:
            hf.attrs["created_at"] = datetime.now(timezone.utc).isoformat()

        for modality in accumulator.modalities:
            items, embeddings = accumulator.get(modality)
            if len(items) == 0:
                continue

            model_id, embed_dim = _MODALITY_META[modality]
            if modality in hf:
                del hf[modality]
            grp = hf.create_group(modality)

            grp.create_dataset("embeddings", data=embeddings, dtype="float32")

            str_dt = h5py.string_dtype(encoding="utf-8")
            grp.create_dataset("entity_id", data=[it.entity_id for it in items], dtype=str_dt)
            grp.create_dataset("kg_uri", data=[it.kg_uri for it in items], dtype=str_dt)
            grp.create_dataset("source_url", data=[it.source_url for it in items], dtype=str_dt)
            grp.create_dataset("filename", data=[it.filename for it in items], dtype=str_dt)

            grp.attrs["model_id"] = model_id
            grp.attrs["embed_dim"] = embed_dim
            grp.attrs["count"] = len(items)
            grp.attrs["created_at"] = datetime.now(timezone.utc).isoformat()

            logger.info("HDF5 group /%s: %d embeddings (%d-d)", modality, len(items), embed_dim)

    logger.info("Wrote HDF5 master file: %s", fpath)
    return str(fpath)


# ======================================================================
# Companion TTL writer (extends the KG with embedding pointers)
# ======================================================================

_TTL_HEADER = """\
@prefix imdb4m: <http://imdb4m.org/embedding/> .
@prefix schema1: <http://schema.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# ---------------------------------------------------------------
# IMDB4M Embedding Metadata
# Generated: {timestamp}
#
# This file extends the IMDB4M Knowledge Graph with triples that
# link media resources to their pre-computed embeddings stored in
# the accompanying Parquet / HDF5 files.
# ---------------------------------------------------------------

"""


def write_ttl(
    accumulator: EmbeddingAccumulator,
    output_dir: str,
    filename: str = "embedding_metadata.ttl",
    parquet_files: Optional[Dict[str, str]] = None,
    hdf5_file: Optional[str] = None,
) -> Optional[str]:
    """
    Write a companion TTL file that links KG URIs to embedding locations.

    Each media item gets triples like::

        <https://www.imdb.com/name/nm0000002/mediaviewer/rm1504202241/>
            imdb4m:hasEmbedding [
                imdb4m:modality "image" ;
                imdb4m:model "openai/clip-vit-large-patch14" ;
                imdb4m:embeddingDim 768 ;
                imdb4m:parquetFile "image_embeddings.parquet" ;
                imdb4m:parquetRow 42 ;
                imdb4m:hdf5File "embeddings.h5" ;
                imdb4m:hdf5Group "/image" ;
                imdb4m:hdf5Index 42 ;
                imdb4m:sourceFile "MV5B...jpg"
            ] .
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fpath = out / filename

    lines: List[str] = [
        _TTL_HEADER.format(timestamp=datetime.now(timezone.utc).isoformat())
    ]

    for modality in accumulator.modalities:
        items, _ = accumulator.get(modality)
        if not items:
            continue

        model_id, embed_dim = _MODALITY_META[modality]
        pq_file = parquet_files.get(modality, "") if parquet_files else ""
        h5_file = hdf5_file or ""

        for idx, item in enumerate(items):
            subject = item.source_url if item.source_url else item.kg_uri
            if not subject:
                continue

            lines.append(f"<{subject}>")
            lines.append(f"    imdb4m:hasEmbedding [")
            lines.append(f'        imdb4m:modality "{modality}" ;')
            lines.append(f'        imdb4m:model "{model_id}" ;')
            lines.append(f"        imdb4m:embeddingDim {embed_dim} ;")
            lines.append(f'        imdb4m:entityId "{item.entity_id}" ;')

            if pq_file:
                pq_basename = Path(pq_file).name
                lines.append(f'        imdb4m:parquetFile "{pq_basename}" ;')
                lines.append(f"        imdb4m:parquetRow {idx} ;")
            if h5_file:
                h5_basename = Path(h5_file).name
                lines.append(f'        imdb4m:hdf5File "{h5_basename}" ;')
                lines.append(f'        imdb4m:hdf5Group "/{modality}" ;')
                lines.append(f"        imdb4m:hdf5Index {idx} ;")

            lines.append(f'        imdb4m:sourceFile "{item.filename}"')
            lines.append(f"    ] .\n")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    total = accumulator.count()
    logger.info("Wrote companion TTL with %d embedding references: %s", total, fpath)
    return str(fpath)


# ======================================================================
# Convenience: write all requested formats at once
# ======================================================================

def write_all(
    accumulator: EmbeddingAccumulator,
    output_dir: str,
    formats: str = "all",
) -> Dict[str, str]:
    """
    Write embeddings in the requested format(s).

    Args:
        accumulator: populated accumulator
        output_dir: target directory
        formats: ``"parquet"`` | ``"hdf5"`` | ``"all"``

    Returns:
        dict mapping format names to written file paths.
    """
    results: Dict[str, str] = {}
    parquet_files: Dict[str, str] = {}
    hdf5_file: Optional[str] = None

    if formats in ("parquet", "all"):
        written = write_parquet(accumulator, output_dir)
        for path in written:
            name = Path(path).stem.replace("_embeddings", "")
            parquet_files[name] = path
        results["parquet"] = ", ".join(written)

    if formats in ("hdf5", "all"):
        hdf5_file = write_hdf5(accumulator, output_dir)
        if hdf5_file:
            results["hdf5"] = hdf5_file

    # Always write the companion TTL when Parquet or HDF5 was produced
    if parquet_files or hdf5_file:
        ttl_path = write_ttl(
            accumulator,
            output_dir,
            parquet_files=parquet_files,
            hdf5_file=hdf5_file,
        )
        if ttl_path:
            results["ttl"] = ttl_path

    return results
