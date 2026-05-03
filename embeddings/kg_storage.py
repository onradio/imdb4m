"""Storage helpers for knowledge-graph embeddings.

The media embedding writer is built around ``MediaItem`` objects.  KG entity
embeddings do not correspond to files on disk, but downstream tooling expects
the same Parquet columns and HDF5 group shape.  This module writes that schema
directly and appends KG groups without touching existing media groups.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KGEmbeddingRecord:
    """One exported entity embedding and its KG linkage metadata."""

    entity_id: str
    kg_uri: str
    embedding: np.ndarray
    source_url: str = ""
    filename: str = ""


@dataclass(frozen=True)
class PyKEENEntityEmbeddingRecord(KGEmbeddingRecord):
    """One exhaustive PyKEEN entity embedding with node metadata."""

    node_kind: str = ""
    pykeen_label: str = ""


def _normalize_records(records: Iterable[KGEmbeddingRecord]) -> List[KGEmbeddingRecord]:
    out: List[KGEmbeddingRecord] = []
    for rec in records:
        emb = np.asarray(rec.embedding, dtype=np.float32)
        if emb.ndim != 1:
            raise ValueError(f"Expected 1-D embedding for {rec.entity_id}, got {emb.shape}")
        norm = float(np.linalg.norm(emb))
        if norm > 0.0:
            emb = emb / norm
        out.append(
            KGEmbeddingRecord(
                entity_id=rec.entity_id,
                kg_uri=rec.kg_uri,
                source_url=rec.source_url,
                filename=rec.filename or f"kg_entity:{rec.entity_id}",
                embedding=np.ascontiguousarray(emb, dtype=np.float32),
            )
        )
    out.sort(key=lambda r: r.entity_id)
    return out


def _normalize_pykeen_records(
    records: Iterable[PyKEENEntityEmbeddingRecord],
) -> List[PyKEENEntityEmbeddingRecord]:
    out: List[PyKEENEntityEmbeddingRecord] = []
    for rec in records:
        emb = np.asarray(rec.embedding, dtype=np.float32)
        if emb.ndim != 1:
            raise ValueError(f"Expected 1-D embedding for {rec.entity_id}, got {emb.shape}")
        norm = float(np.linalg.norm(emb))
        if norm > 0.0:
            emb = emb / norm
        out.append(
            PyKEENEntityEmbeddingRecord(
                entity_id=rec.entity_id,
                kg_uri=rec.kg_uri,
                source_url=rec.source_url,
                filename=rec.filename or f"kg_entity:{rec.entity_id}",
                embedding=np.ascontiguousarray(emb, dtype=np.float32),
                node_kind=rec.node_kind,
                pykeen_label=rec.pykeen_label,
            )
        )
    out.sort(key=lambda r: (r.node_kind, r.entity_id, r.pykeen_label))
    return out


def write_kg_parquet(
    records: Iterable[KGEmbeddingRecord],
    output_dir: str | Path,
    modality: str,
    model_id: str,
) -> Optional[str]:
    """Write ``{modality}_embeddings.parquet`` using the media embedding schema."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    normalized = _normalize_records(records)
    if not normalized:
        return None

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    embeddings = np.vstack([r.embedding for r in normalized]).astype(np.float32, copy=False)
    dim = embeddings.shape[1]

    flat = pa.array(embeddings.reshape(-1), type=pa.float32())
    emb_column = pa.FixedSizeListArray.from_arrays(flat, dim)
    table = pa.table(
        {
            "entity_id": [r.entity_id for r in normalized],
            "kg_uri": [r.kg_uri for r in normalized],
            "source_url": [r.source_url for r in normalized],
            "filename": [r.filename for r in normalized],
            "model_id": [model_id] * len(normalized),
            "embedding": emb_column,
        }
    )

    fpath = out / f"{modality}_embeddings.parquet"
    pq.write_table(table, str(fpath), compression="zstd")
    logger.info("Wrote %d %s KG embeddings to %s", len(normalized), modality, fpath)
    return str(fpath)


def write_kg_hdf5(
    records: Iterable[KGEmbeddingRecord],
    output_dir: str | Path,
    modality: str,
    model_id: str,
    filename: str = "embeddings.h5",
    overwrite_group: bool = True,
) -> Optional[str]:
    """Append a KG modality group to the master HDF5 file."""

    import h5py

    normalized = _normalize_records(records)
    if not normalized:
        return None

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fpath = out / filename
    embeddings = np.vstack([r.embedding for r in normalized]).astype(np.float32, copy=False)
    now = datetime.now(timezone.utc).isoformat()

    with h5py.File(str(fpath), "a") as hf:
        if "created_at" not in hf.attrs:
            hf.attrs["created_at"] = now
        if modality in hf:
            if not overwrite_group:
                raise ValueError(f"HDF5 group /{modality} already exists in {fpath}")
            del hf[modality]

        grp = hf.create_group(modality)
        grp.create_dataset("embeddings", data=embeddings, dtype="float32")
        str_dt = h5py.string_dtype(encoding="utf-8")
        grp.create_dataset("entity_id", data=[r.entity_id for r in normalized], dtype=str_dt)
        grp.create_dataset("kg_uri", data=[r.kg_uri for r in normalized], dtype=str_dt)
        grp.create_dataset("source_url", data=[r.source_url for r in normalized], dtype=str_dt)
        grp.create_dataset("filename", data=[r.filename for r in normalized], dtype=str_dt)
        grp.attrs["model_id"] = model_id
        grp.attrs["embed_dim"] = int(embeddings.shape[1])
        grp.attrs["count"] = len(normalized)
        grp.attrs["created_at"] = now

    logger.info("Wrote HDF5 group /%s: %d embeddings (%d-d)", modality, len(normalized), embeddings.shape[1])
    return str(fpath)


def write_kg_embeddings(
    records: Iterable[KGEmbeddingRecord],
    output_dir: str | Path,
    modality: str,
    model_id: str,
    storage_format: str = "all",
    hdf5_filename: str = "embeddings.h5",
    overwrite_group: bool = True,
) -> dict:
    """Write KG embeddings in Parquet, HDF5, or both formats."""

    normalized = _normalize_records(records)
    written = {}
    if storage_format in ("parquet", "all"):
        path = write_kg_parquet(normalized, output_dir, modality, model_id)
        if path:
            written["parquet"] = path
    if storage_format in ("hdf5", "all"):
        path = write_kg_hdf5(
            normalized,
            output_dir,
            modality,
            model_id,
            filename=hdf5_filename,
            overwrite_group=overwrite_group,
        )
        if path:
            written["hdf5"] = path
    if storage_format not in ("parquet", "hdf5", "all"):
        raise ValueError(f"Unknown storage format: {storage_format}")
    return written


def write_pykeen_entities_parquet(
    records: Iterable[PyKEENEntityEmbeddingRecord],
    output_dir: str | Path,
    modality: str,
    model_id: str,
) -> Optional[str]:
    """Write exhaustive PyKEEN entity embeddings with node metadata."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    normalized = _normalize_pykeen_records(records)
    if not normalized:
        return None

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    embeddings = np.vstack([r.embedding for r in normalized]).astype(np.float32, copy=False)
    dim = embeddings.shape[1]

    flat = pa.array(embeddings.reshape(-1), type=pa.float32())
    emb_column = pa.FixedSizeListArray.from_arrays(flat, dim)
    table = pa.table(
        {
            "entity_id": [r.entity_id for r in normalized],
            "kg_uri": [r.kg_uri for r in normalized],
            "source_url": [r.source_url for r in normalized],
            "filename": [r.filename for r in normalized],
            "model_id": [model_id] * len(normalized),
            "node_kind": [r.node_kind for r in normalized],
            "pykeen_label": [r.pykeen_label for r in normalized],
            "embedding": emb_column,
        }
    )

    fpath = out / f"{modality}.parquet"
    pq.write_table(table, str(fpath), compression="zstd")
    logger.info("Wrote %d exhaustive PyKEEN entities to %s", len(normalized), fpath)
    return str(fpath)


def write_pykeen_entities_hdf5(
    records: Iterable[PyKEENEntityEmbeddingRecord],
    output_dir: str | Path,
    group_name: str,
    model_id: str,
    filename: str = "embeddings.h5",
    overwrite_group: bool = True,
) -> Optional[str]:
    """Append exhaustive PyKEEN entity embeddings to the master HDF5 file."""

    import h5py

    normalized = _normalize_pykeen_records(records)
    if not normalized:
        return None

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fpath = out / filename
    embeddings = np.vstack([r.embedding for r in normalized]).astype(np.float32, copy=False)
    now = datetime.now(timezone.utc).isoformat()

    with h5py.File(str(fpath), "a") as hf:
        if "created_at" not in hf.attrs:
            hf.attrs["created_at"] = now
        if group_name in hf:
            if not overwrite_group:
                raise ValueError(f"HDF5 group /{group_name} already exists in {fpath}")
            del hf[group_name]

        grp = hf.create_group(group_name)
        grp.create_dataset("embeddings", data=embeddings, dtype="float32")
        str_dt = h5py.string_dtype(encoding="utf-8")
        grp.create_dataset("entity_id", data=[r.entity_id for r in normalized], dtype=str_dt)
        grp.create_dataset("kg_uri", data=[r.kg_uri for r in normalized], dtype=str_dt)
        grp.create_dataset("source_url", data=[r.source_url for r in normalized], dtype=str_dt)
        grp.create_dataset("filename", data=[r.filename for r in normalized], dtype=str_dt)
        grp.create_dataset("node_kind", data=[r.node_kind for r in normalized], dtype=str_dt)
        grp.create_dataset("pykeen_label", data=[r.pykeen_label for r in normalized], dtype=str_dt)
        grp.attrs["model_id"] = model_id
        grp.attrs["embed_dim"] = int(embeddings.shape[1])
        grp.attrs["count"] = len(normalized)
        grp.attrs["created_at"] = now

    logger.info(
        "Wrote HDF5 group /%s: %d exhaustive PyKEEN entities (%d-d)",
        group_name,
        len(normalized),
        embeddings.shape[1],
    )
    return str(fpath)


def write_pykeen_entity_embeddings(
    records: Iterable[PyKEENEntityEmbeddingRecord],
    output_dir: str | Path,
    file_stem: str,
    group_name: str,
    model_id: str,
    storage_format: str = "all",
    hdf5_filename: str = "embeddings.h5",
    overwrite_group: bool = True,
) -> dict:
    """Write exhaustive PyKEEN entity embeddings in Parquet, HDF5, or both."""

    normalized = _normalize_pykeen_records(records)
    written = {}
    if storage_format in ("parquet", "all"):
        path = write_pykeen_entities_parquet(normalized, output_dir, file_stem, model_id)
        if path:
            written["parquet"] = path
    if storage_format in ("hdf5", "all"):
        path = write_pykeen_entities_hdf5(
            normalized,
            output_dir,
            group_name,
            model_id,
            filename=hdf5_filename,
            overwrite_group=overwrite_group,
        )
        if path:
            written["hdf5"] = path
    if storage_format not in ("parquet", "hdf5", "all"):
        raise ValueError(f"Unknown storage format: {storage_format}")
    return written
