"""Copy ``embeddings.h5`` into a gzip-compressed release-ready variant.

In addition to compressing the embedding matrices (typically 2-3× on
disk savings with negligible decode overhead), this module enriches the
file with metadata that researchers need to reuse the vectors safely:

* per-group ``model_revision`` (pinned in :mod:`release.config`);
* per-group ``normalized`` flag recording whether vectors are L2-unit;
* per-group ``created_at`` copied from the original file;
* top-level ``provenance`` attribute referencing the pruned KG and the
  regenerated companion TTL.

A companion ``embeddings_card.json`` is also produced with the same
metadata in a machine-friendly format.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import h5py

from . import config as cfg

logger = logging.getLogger(__name__)

_MODALITY_META: Dict[str, Dict] = {
    "image": {"model_id": cfg.IMAGE_MODEL_ID, "embed_dim": cfg.IMAGE_EMBED_DIM},
    "video": {"model_id": cfg.VIDEO_MODEL_ID, "embed_dim": cfg.VIDEO_EMBED_DIM},
    "audio": {"model_id": cfg.AUDIO_MODEL_ID, "embed_dim": cfg.AUDIO_EMBED_DIM},
    "text": {"model_id": cfg.TEXT_MODEL_ID, "embed_dim": cfg.TEXT_EMBED_DIM},
}


def _copy_h5_with_compression(src: Path, dst: Path, compression: str = "gzip", compression_opts: int = 4) -> None:
    """Copy ``src`` → ``dst`` re-encoding every dataset with gzip."""
    logger.info("Rewriting %s → %s with %s%s compression", src, dst, compression, compression_opts)
    with h5py.File(str(src), "r") as src_h5, h5py.File(str(dst), "w") as dst_h5:
        for k, v in src_h5.attrs.items():
            dst_h5.attrs[k] = v
        for grp_name, grp in src_h5.items():
            new_grp = dst_h5.create_group(grp_name)
            for k, v in grp.attrs.items():
                new_grp.attrs[k] = v
            for ds_name, ds in grp.items():
                kwargs = {"data": ds[:]}
                # only compress datasets with >1 row (scalars don't benefit)
                if ds.ndim >= 1 and ds.shape[0] > 1:
                    kwargs["compression"] = compression
                    kwargs["compression_opts"] = compression_opts
                new_grp.create_dataset(ds_name, **kwargs)


def run(
    output_path: Path = cfg.ENHANCED_H5,
    card_path: Path = cfg.EMBEDDINGS_CARD,
    src: Path = cfg.EMBEDDINGS_H5,
    normalized: bool = True,
    compression_opts: int = 4,
) -> Dict[str, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _copy_h5_with_compression(src, output_path, compression_opts=compression_opts)

    enhanced_attrs: Dict[str, Dict] = {}
    with h5py.File(str(output_path), "a") as hf:
        hf.attrs["provenance_pruned_kg"] = cfg.PRUNED_KG.name
        hf.attrs["provenance_failed_kg"] = cfg.FAILED_KG.name
        hf.attrs["regenerated_ttl"] = cfg.REGENERATED_TTL.name
        hf.attrs["enhanced_at"] = datetime.now(timezone.utc).isoformat()
        hf.attrs["toolchain_version"] = "imdb4m-release-v1"

        for mod, meta in _MODALITY_META.items():
            if mod not in hf:
                continue
            grp = hf[mod]
            grp.attrs["normalized"] = bool(normalized)
            grp.attrs["model_revision"] = cfg.MODEL_REVISIONS.get(meta["model_id"], "main")
            grp.attrs["vector_dtype"] = "float32"
            grp.attrs["similarity_metric"] = "cosine" if normalized else "dot-product"
            enhanced_attrs[mod] = {
                "count": int(grp.attrs.get("count", grp["embeddings"].shape[0])),
                "embed_dim": int(grp.attrs.get("embed_dim", grp["embeddings"].shape[1])),
                "model_id": str(grp.attrs["model_id"]),
                "model_revision": str(grp.attrs["model_revision"]),
                "normalized": bool(grp.attrs["normalized"]),
                "similarity_metric": str(grp.attrs["similarity_metric"]),
                "vector_dtype": str(grp.attrs["vector_dtype"]),
                "created_at": str(grp.attrs.get("created_at", "")),
            }

    card = {
        "name": "IMDB4M Media Embeddings",
        "version": "v1",
        "enhanced_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "pruned_kg": cfg.PRUNED_KG.name,
            "failed_side_graph": cfg.FAILED_KG.name,
            "regenerated_metadata_ttl": cfg.REGENERATED_TTL.name,
            "alignment_report": cfg.ALIGNMENT_REPORT.name,
        },
        "storage": {
            "hdf5": output_path.name,
            "parquet": {
                "image": cfg.IMAGE_PARQUET.name,
                "video": cfg.VIDEO_PARQUET.name,
                "audio": cfg.AUDIO_PARQUET.name,
                "text": cfg.TEXT_PARQUET.name,
            },
            "compression": {"hdf5": f"gzip-{compression_opts}", "parquet": "zstd"},
        },
        "modalities": enhanced_attrs,
        "notes": [
            "Embeddings are L2-normalised; use cosine similarity (== dot product).",
            "HDF5 row indices match parquet row indices for the same modality.",
            "See `embedding_metadata.ttl` for SPARQL-friendly row pointers.",
        ],
    }
    with open(card_path, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    logger.info("Wrote embeddings card → %s", card_path)

    return {"hdf5": output_path, "card": card_path}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run()
