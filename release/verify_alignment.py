"""Diff the pruned KG against the embedding parquet tables.

For every modality this module answers two questions:

1. **Orphan embeddings** – parquet rows whose ``(entity_id, key)`` tuple
   is *not* present in the pruned KG.  These rows reference media that
   the KG no longer asserts; they should be removed or at least flagged.
2. **Un-embedded KG media** – KG triples that advertise media for which
   no embedding row exists.  These typically correspond to images/videos
   that failed to download after the pruning step, or audio tracks with
   no YouTube link.

The module does not modify the embeddings themselves; it produces a
JSON report at ``release_output/alignment_report.json`` that later
stages (e.g. :mod:`release.regenerate_metadata`) can consume.

Key extraction rules (must match the downloader conventions):

* **image**: stem of the CDN URL / filename, e.g.
  ``MV5B...XkEyXkFqcGc_._V1_`` (normalised to lowercase, trailing
  ``@`` and ``_`` collapsed).
* **video**: ``viNNN`` token extracted from the IMDB embed URL
  (``https://www.imdb.com/video/viNNN/``) or from the filename prefix.
* **audio**: entity-level only – we assume a track is covered if the
  entity has at least one ``schema:audio`` blank node in the KG, since
  the KG does not store the YouTube URL needed for a track-level match.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pyarrow.parquet as pq
from rdflib import Graph, URIRef

from . import config as cfg

logger = logging.getLogger(__name__)

SCHEMA_IMAGE = URIRef(cfg.SCHEMA_NS + "image")
SCHEMA_URL = URIRef(cfg.SCHEMA_NS + "url")
SCHEMA_EMBED_URL = URIRef(cfg.SCHEMA_NS + "embedUrl")
SCHEMA_TRAILER = URIRef(cfg.SCHEMA_NS + "trailer")
SCHEMA_VIDEO = URIRef(cfg.SCHEMA_NS + "video")
SCHEMA_AUDIO = URIRef(cfg.SCHEMA_NS + "audio")
SCHEMA_THUMBNAIL = URIRef(cfg.SCHEMA_NS + "thumbnail")
SCHEMA_THUMBNAIL_URL = URIRef(cfg.SCHEMA_NS + "thumbnailUrl")

IMAGE_PREDICATES = (SCHEMA_IMAGE, SCHEMA_THUMBNAIL, SCHEMA_THUMBNAIL_URL)

VI_RE = re.compile(r"(vi\d+)")
ENTITY_RE = re.compile(r"(nm\d+|tt\d+)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_id_from_uri(uri: str) -> str:
    m = ENTITY_RE.search(uri)
    return m.group(1) if m else ""


def _image_key_from_filename(name: str) -> str:
    """Normalise an image basename into a comparable stem."""
    stem = Path(name).stem
    # strip trailing ``_.V1_`` suffix that IMDB appends but not the
    # base image identifier
    stem = stem.lower()
    # collapse ``@._v1_`` / ``_._v1_`` tail
    stem = re.sub(r"[_@]+\._v1_.*$", "", stem)
    return stem


def _image_key_from_url(url: str) -> str:
    fname = url.rsplit("/", 1)[-1]
    return _image_key_from_filename(fname)


def _video_key(filename: str = "", url: str = "") -> str:
    for src in (url, filename):
        if not src:
            continue
        m = VI_RE.search(src)
        if m:
            return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# KG side
# ---------------------------------------------------------------------------


@dataclass
class KGTruth:
    images: Set[Tuple[str, str]] = field(default_factory=set)   # (entity_id, image_key)
    videos: Set[Tuple[str, str]] = field(default_factory=set)   # (entity_id, viNNN)
    audio_entities: Set[str] = field(default_factory=set)       # entity_ids with >=1 audio bnode
    image_count_per_entity: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    video_count_per_entity: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    audio_count_per_entity: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def load_kg_truth(kg_path: Path) -> KGTruth:
    logger.info("Parsing pruned KG %s …", kg_path)
    g = Graph()
    g.parse(kg_path, format="turtle")
    logger.info("  %d triples", len(g))

    truth = KGTruth()

    logger.info("Indexing images …")
    for pred in IMAGE_PREDICATES:
        for ent, _, img in g.triples((None, pred, None)):
            eid = _entity_id_from_uri(str(ent))
            if not eid:
                continue
            # ``img`` is usually a URIRef to the CDN URL (ImageObject) or a
            # direct literal/URI on the CDN.  Resolve its ``schema:url``
            # if it exists, otherwise use the node itself.
            url_node = g.value(img, SCHEMA_URL)
            target = str(url_node) if url_node is not None else str(img)
            key = _image_key_from_url(target)
            if not key:
                continue
            truth.images.add((eid, key))
            truth.image_count_per_entity[eid] += 1

    logger.info("Indexing videos …")
    for pred in (SCHEMA_TRAILER, SCHEMA_VIDEO):
        for ent, _, vid in g.triples((None, pred, None)):
            eid = _entity_id_from_uri(str(ent))
            if not eid:
                continue
            key = _video_key(url=str(vid))
            if not key:
                embed = g.value(vid, SCHEMA_EMBED_URL)
                if embed:
                    key = _video_key(url=str(embed))
            if not key:
                continue
            truth.videos.add((eid, key))
            truth.video_count_per_entity[eid] += 1

    logger.info("Indexing audio …")
    for ent, _, rec in g.triples((None, SCHEMA_AUDIO, None)):
        eid = _entity_id_from_uri(str(ent))
        if not eid:
            continue
        truth.audio_entities.add(eid)
        truth.audio_count_per_entity[eid] += 1

    logger.info(
        "  KG truth: %d images, %d videos, %d audio-entities",
        len(truth.images), len(truth.videos), len(truth.audio_entities),
    )
    return truth


# ---------------------------------------------------------------------------
# Parquet side
# ---------------------------------------------------------------------------


def _load_parquet_keys(path: Path, modality: str) -> List[Tuple[str, str, str, str]]:
    """Return a list of (entity_id, key, filename, source_url) tuples."""
    t = pq.read_table(str(path), columns=["entity_id", "source_url", "filename"])
    eids = t.column("entity_id").to_pylist()
    urls = t.column("source_url").to_pylist()
    names = t.column("filename").to_pylist()
    rows: List[Tuple[str, str, str, str]] = []
    for eid, url, fn in zip(eids, urls, names):
        if modality == "image":
            key = _image_key_from_filename(fn) or _image_key_from_url(url or "")
        elif modality == "video":
            key = _video_key(filename=fn, url=url or "")
        else:
            key = fn  # audio: keep the full filename
        rows.append((eid or "", key, fn, url or ""))
    return rows


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _diff_modality(
    modality: str,
    parquet_rows: List[Tuple[str, str, str, str]],
    kg_keys: Set[Tuple[str, str]],
    kg_entities: Set[str],
) -> Dict:
    per_entity_emb: Dict[str, int] = defaultdict(int)
    orphan_rows: List[Dict] = []

    if modality in ("image", "video"):
        for row_idx, (eid, key, fn, url) in enumerate(parquet_rows):
            per_entity_emb[eid] += 1
            if (eid, key) not in kg_keys:
                orphan_rows.append(
                    {"row": row_idx, "entity_id": eid, "key": key,
                     "filename": fn, "source_url": url}
                )
        missing = [
            {"entity_id": eid, "key": key}
            for (eid, key) in kg_keys
            if (eid, key) not in {(r[0], r[1]) for r in parquet_rows}
        ]
    else:  # audio -> entity-level
        emb_entities: Set[str] = set()
        for row_idx, (eid, _key, fn, url) in enumerate(parquet_rows):
            per_entity_emb[eid] += 1
            emb_entities.add(eid)
            if eid not in kg_entities:
                orphan_rows.append(
                    {"row": row_idx, "entity_id": eid,
                     "filename": fn, "source_url": url}
                )
        missing = [
            {"entity_id": eid} for eid in sorted(kg_entities) if eid not in emb_entities
        ]

    return {
        "parquet_rows": len(parquet_rows),
        "kg_keys": len(kg_keys) if modality != "audio" else len(kg_entities),
        "orphan_rows": orphan_rows,
        "orphan_count": len(orphan_rows),
        "missing_in_embeddings": missing,
        "missing_count": len(missing),
        "per_entity_embedding_count": dict(per_entity_emb),
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run(write_report: bool = True) -> Dict:
    truth = load_kg_truth(cfg.PRUNED_KG)

    logger.info("Loading parquet files …")
    image_rows = _load_parquet_keys(cfg.IMAGE_PARQUET, "image")
    video_rows = _load_parquet_keys(cfg.VIDEO_PARQUET, "video")
    audio_rows = _load_parquet_keys(cfg.AUDIO_PARQUET, "audio")

    logger.info("Diffing …")
    report = {
        "pruned_kg": str(cfg.PRUNED_KG),
        "image": _diff_modality("image", image_rows, truth.images, set()),
        "video": _diff_modality("video", video_rows, truth.videos, set()),
        "audio": _diff_modality("audio", audio_rows, set(), truth.audio_entities),
    }

    # Summary
    summary = {
        m: {
            "parquet_rows": report[m]["parquet_rows"],
            "kg_keys": report[m]["kg_keys"],
            "orphans_in_embeddings": report[m]["orphan_count"],
            "missing_in_embeddings": report[m]["missing_count"],
        }
        for m in ("image", "video", "audio")
    }
    report["summary"] = summary

    if write_report:
        cfg.ALIGNMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        # Trim per-entity counts from file to keep it human-readable; they
        # remain available in-memory for callers that want them.
        persisted = json.loads(json.dumps(report))
        for m in ("image", "video", "audio"):
            persisted[m].pop("per_entity_embedding_count", None)
            # Cap orphan list to a sample so the file stays compact.
            persisted[m]["orphan_sample"] = persisted[m]["orphan_rows"][:50]
            persisted[m].pop("orphan_rows", None)
            persisted[m]["missing_sample"] = persisted[m]["missing_in_embeddings"][:50]
            persisted[m].pop("missing_in_embeddings", None)
        with open(cfg.ALIGNMENT_REPORT, "w", encoding="utf-8") as f:
            json.dump(persisted, f, indent=2)
        logger.info("Wrote alignment report → %s", cfg.ALIGNMENT_REPORT)

    logger.info("Alignment summary: %s", summary)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run()
