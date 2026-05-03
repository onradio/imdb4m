"""Regenerate ``embedding_metadata.ttl`` against the pruned KG.

The file produced by ``embeddings/storage.py`` predates the KG clean-up
pass.  It might therefore contain ``imdb4m:hasEmbedding`` triples whose
subjects do not appear in the pruned KG (because the URL was rescued or
the media was purged).

This module re-emits an equivalent TTL but:

* skips any parquet row whose ``entity_id`` is not present in the pruned
  KG;
* adds a ``imdb4m:embeddingsNormalized true`` flag to every record;
* records the HuggingFace model revision pinned in
  :mod:`release.config` alongside the model id;
* records the parquet / HDF5 row index (already present in the original
  schema) but guarantees it is monotonic per modality.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import pyarrow.parquet as pq
from rdflib import Graph, URIRef

from . import config as cfg

logger = logging.getLogger(__name__)

ENTITY_RE = re.compile(r"(nm\d+|tt\d+)")
SCHEMA_URL = URIRef(cfg.SCHEMA_NS + "url")


_TTL_HEADER = """\
@prefix imdb4m: <http://imdb4m.org/embedding/> .
@prefix schema1: <http://schema.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# ---------------------------------------------------------------
# IMDB4M Embedding Metadata (regenerated against pruned KG)
# Generated: {timestamp}
# Pruned KG:  {kg_file}
#
# Each record links an IMDB4M media resource to its pre-computed
# embedding vector stored in the companion Parquet and HDF5 files.
# ---------------------------------------------------------------

"""


def _load_kg_entities(kg_path: Path) -> Set[str]:
    """Return the set of ``nm*``/``tt*`` ids that appear anywhere in the KG."""
    logger.info("Parsing pruned KG %s for entity allow-list …", kg_path)
    g = Graph()
    g.parse(kg_path, format="turtle")
    ids: Set[str] = set()
    for s, _, _ in g:
        m = ENTITY_RE.search(str(s))
        if m:
            ids.add(m.group(1))
    for _, _, o in g:
        m = ENTITY_RE.search(str(o))
        if m:
            ids.add(m.group(1))
    logger.info("  %d distinct entity ids in pruned KG", len(ids))
    return ids


def _iter_parquet_rows(path: Path) -> Iterable[Tuple[int, Dict]]:
    t = pq.read_table(
        str(path),
        columns=["entity_id", "kg_uri", "source_url", "filename", "model_id"],
    )
    cols = t.to_pydict()
    n = len(cols["entity_id"])
    for i in range(n):
        yield i, {
            "entity_id": cols["entity_id"][i] or "",
            "kg_uri": cols["kg_uri"][i] or "",
            "source_url": cols["source_url"][i] or "",
            "filename": cols["filename"][i] or "",
            "model_id": cols["model_id"][i] or "",
        }


_MODALITY_TO_DIM = {
    "image": cfg.IMAGE_EMBED_DIM,
    "video": cfg.VIDEO_EMBED_DIM,
    "audio": cfg.AUDIO_EMBED_DIM,
    "text": cfg.TEXT_EMBED_DIM,
}


def run(
    output_path: Path = cfg.REGENERATED_TTL,
    parquet_basenames: Dict[str, str] | None = None,
    hdf5_basename: str = "embeddings.h5",
    alignment_report_path: Path | None = cfg.ALIGNMENT_REPORT,
) -> Path:
    parquet_basenames = parquet_basenames or {
        "image": cfg.IMAGE_PARQUET.name,
        "video": cfg.VIDEO_PARQUET.name,
        "audio": cfg.AUDIO_PARQUET.name,
        "text": cfg.TEXT_PARQUET.name,
    }
    sources = {
        "image": cfg.IMAGE_PARQUET,
        "video": cfg.VIDEO_PARQUET,
        "audio": cfg.AUDIO_PARQUET,
        "text": cfg.TEXT_PARQUET,
    }

    entity_ids = _load_kg_entities(cfg.PRUNED_KG)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dropped_counts = {m: 0 for m in sources}
    emitted_counts = {m: 0 for m in sources}

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(
            _TTL_HEADER.format(
                timestamp=datetime.now(timezone.utc).isoformat(),
                kg_file=cfg.PRUNED_KG.name,
            )
        )

        for modality in ("image", "video", "audio", "text"):
            src = sources[modality]
            if not src.exists():
                logger.warning("Parquet missing: %s — skipping", src)
                continue
            model_id = {
                "image": cfg.IMAGE_MODEL_ID,
                "video": cfg.VIDEO_MODEL_ID,
                "audio": cfg.AUDIO_MODEL_ID,
                "text": cfg.TEXT_MODEL_ID,
            }[modality]
            revision = cfg.MODEL_REVISIONS.get(model_id, "main")
            embed_dim = _MODALITY_TO_DIM[modality]
            pq_basename = parquet_basenames[modality]

            logger.info("Regenerating %s records …", modality)
            for row_idx, row in _iter_parquet_rows(src):
                if row["entity_id"] not in entity_ids:
                    dropped_counts[modality] += 1
                    continue
                subject = row["source_url"] or row["kg_uri"]
                if not subject:
                    dropped_counts[modality] += 1
                    continue

                f.write(f"<{subject}>\n")
                f.write("    imdb4m:hasEmbedding [\n")
                f.write(f'        imdb4m:modality "{modality}" ;\n')
                f.write(f'        imdb4m:model "{model_id}" ;\n')
                f.write(f'        imdb4m:modelRevision "{revision}" ;\n')
                f.write(f"        imdb4m:embeddingDim {embed_dim} ;\n")
                f.write('        imdb4m:embeddingsNormalized true ;\n')
                f.write(f'        imdb4m:entityId "{row["entity_id"]}" ;\n')
                f.write(f'        imdb4m:parquetFile "{pq_basename}" ;\n')
                f.write(f"        imdb4m:parquetRow {row_idx} ;\n")
                f.write(f'        imdb4m:hdf5File "{hdf5_basename}" ;\n')
                f.write(f'        imdb4m:hdf5Group "/{modality}" ;\n')
                f.write(f"        imdb4m:hdf5Index {row_idx} ;\n")
                safe_fname = row["filename"].replace('"', '\\"')
                f.write(f'        imdb4m:sourceFile "{safe_fname}"\n')
                f.write("    ] .\n\n")
                emitted_counts[modality] += 1

    logger.info(
        "Regenerated TTL: emitted=%s  dropped=%s  → %s",
        emitted_counts, dropped_counts, output_path,
    )
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run()
