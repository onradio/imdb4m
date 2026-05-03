"""Compare the on-disk inventory against the KG index → decide actions.

For every media node in the KG that belongs to an entity we actually tried
to download (i.e. an entity that has a directory under ``output/``), we
produce one of three actions:

* **KEEP**     the expected file is on disk — nothing to do.
* **REWRITE**  the file exists under a *different* URL recorded in
  :mod:`rescue_map`; we'll rewrite the KG URI (and its back-references)
  to the new URL.
* **DELETE**   no acceptable file exists anywhere; the node and every
  reference to it will be moved to the side graph.

Audio nodes are special: their URL is not in the main KG but in
``data/movies/<tt>/movie_soundtrack/soundtrack_links.json``.  An audio
``MusicRecording`` only counts as "attempted to download" when that JSON
side-car resolved it to a YouTube URL; pure KG-only tracks without a
YouTube link are always kept (they represent "no audio modality
available", not a download failure).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from rdflib import URIRef
from rdflib.term import BNode

from .config import DATA_MOVIES
from .disk_scan import (
    DiskScan,
    MediaFile,
    audio_stem_candidates,
    image_stem_from_url,
    video_id_from_url,
)
from .kg_index import (
    AudioRecord,
    ImageRecord,
    IMAGE_BACKREF_PREDICATES,
    KGIndex,
    SCHEMA_IMAGE,
    SCHEMA_THUMBNAIL,
    SCHEMA_TRAILER,
    SCHEMA_VIDEO,
    VIDEO_BACKREF_PREDICATES,
    VideoRecord,
    _entity_id_from_uri,
)
from .rescue_map import RescueEntry, index_rescues

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action records
# ---------------------------------------------------------------------------

class Action(str, Enum):
    KEEP = "keep"
    REWRITE = "rewrite"
    DELETE = "delete"


@dataclass
class Decision:
    media_type: str                     # images | videos | audio
    action: Action
    entity_id: str                      # owning entity (for video decisions this is the back-reference source)
    reason: str = ""
    # For URI-identified media:
    old_uri: Optional[str] = None
    new_uri: Optional[str] = None
    old_url: Optional[str] = None       # CDN / embed / YouTube URL
    new_url: Optional[str] = None
    # For video back-reference decisions
    backref_predicate: Optional[str] = None   # fully-qualified predicate URI
    # For bnode audio:
    audio_bnode: Optional[str] = None   # serialised BNode id for audit
    audio_title: Optional[str] = None
    audio_file_on_disk: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


@dataclass
class Manifest:
    decisions: List[Decision] = field(default_factory=list)
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add(self, d: Decision) -> None:
        self.decisions.append(d)
        by_type = self.stats.setdefault(d.media_type, {"keep": 0, "rewrite": 0, "delete": 0})
        by_type[d.action.value] = by_type.get(d.action.value, 0) + 1

    def to_dict(self) -> dict:
        return {
            "stats": self.stats,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# ---------------------------------------------------------------------------
# Soundtrack JSON loader
# ---------------------------------------------------------------------------

@dataclass
class _SoundtrackEntry:
    title: str
    performer: Optional[str]
    composer: Optional[str]
    youtube_url: str
    video_id: Optional[str]


def _load_soundtrack_links(entity_id: str) -> Dict[str, _SoundtrackEntry]:
    """Return ``{normalised_title: _SoundtrackEntry}`` for a movie."""
    for cand in (
        DATA_MOVIES / entity_id / "movie_soundtrack" / "soundtrack_links.json",
        DATA_MOVIES.parent / "sample" / entity_id / "movie_soundtrack" / "soundtrack_links.json",
    ):
        if cand.exists():
            try:
                with open(cand, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:   # pragma: no cover
                logger.warning("Failed to read %s: %s", cand, e)
                return {}
            out: Dict[str, _SoundtrackEntry] = {}
            for item in data:
                best = item.get("best_match") or {}
                st = item.get("soundtrack") or {}
                title = st.get("title") or best.get("title")
                url = best.get("url")
                if not title or not url:
                    continue
                out[_norm_title(title)] = _SoundtrackEntry(
                    title=title,
                    performer=st.get("performer"),
                    composer=st.get("composer"),
                    youtube_url=url,
                    video_id=best.get("video_id"),
                )
            return out
    return {}


def _norm_title(s: str) -> str:
    return re.sub(r"[^\w]+", "", (s or "").lower())


# ---------------------------------------------------------------------------
# Per-media reconciliation
# ---------------------------------------------------------------------------

def _reconcile_images(scan: DiskScan, kg: KGIndex, manifest: Manifest) -> None:
    """Reconcile image **back-references** (``?ent schema:image ?img`` and
    ``?ent schema:thumbnail ?img``).

    ImageObject URIs are CDN URLs and do *not* encode the owning entity,
    so we cannot derive ownership from the image subject alone.  Instead,
    every decision is keyed by the ``(entity, predicate, image_uri)``
    triple.  An image kept by one entity but missing on another's disk
    will therefore lose only the specific back-reference that lacks a
    matching file; the ``ImageObject`` survives as long as at least one
    entity still points at it.  Unreferenced ``ImageObject`` nodes are
    garbage-collected by :func:`apply._apply_image_backref_deletions`.
    """
    g = kg.graph
    for pred in IMAGE_BACKREF_PREDICATES:
        for entity_uri, _, img_uri in g.triples((None, pred, None)):
            eid = _entity_id_from_uri(str(entity_uri))
            if not eid or eid not in scan.entities:
                continue
            inv = scan.entities[eid]
            rec = kg.images.get(img_uri)
            cdn_url = rec.cdn_url if rec is not None else str(img_uri)
            expected_stem = image_stem_from_url(cdn_url) if cdn_url else None

            if expected_stem and expected_stem in inv.image_index:
                manifest.add(Decision(
                    media_type="images", action=Action.KEEP,
                    entity_id=eid, old_uri=str(img_uri),
                    old_url=cdn_url,
                    backref_predicate=str(pred),
                    reason="file-on-disk"))
                continue

            manifest.add(Decision(
                media_type="images", action=Action.DELETE,
                entity_id=eid, old_uri=str(img_uri),
                old_url=cdn_url,
                backref_predicate=str(pred),
                reason="missing-on-disk"))


def _reconcile_videos(scan: DiskScan, kg: KGIndex,
                      per_entity_rewrite,
                      manifest: Manifest) -> None:
    """Reconcile **per back-reference**, not per ``VideoObject``.

    The same ``VideoObject`` can appear under multiple entities (several
    names point at the same trailer URI) but each entity may disk-contain
    a *different* rescued file.  So the unit of decision is the
    ``(entity, predicate, video_uri)`` triple.
    """
    g = kg.graph
    for pred in VIDEO_BACKREF_PREDICATES:
        for entity_uri, _, video_uri in g.triples((None, pred, None)):
            eid = _entity_id_from_uri(str(entity_uri))
            if not eid or eid not in scan.entities:
                continue
            rec = kg.videos.get(video_uri)
            if rec is None:
                continue  # back-reference to something that isn't a VideoObject; skip
            inv = scan.entities[eid]
            vid = rec.video_id

            # 1. Is the original viNNN on disk? Keep.
            if vid and vid in inv.video_index:
                manifest.add(Decision(media_type="videos", action=Action.KEEP,
                                      entity_id=eid,
                                      backref_predicate=str(pred),
                                      old_uri=str(video_uri),
                                      old_url=rec.embed_url,
                                      reason="file-on-disk"))
                continue

            # 2. Was this (entity, vid) rescued to a new URL?
            new_vid = per_entity_rewrite.get((eid, vid)) if vid else None
            if new_vid and new_vid in inv.video_index:
                new_uri = re.sub(r"vi\d+", new_vid, str(video_uri))
                new_embed = re.sub(r"vi\d+", new_vid,
                                   rec.embed_url or f"https://www.imdb.com/video/{vid}/")
                manifest.add(Decision(media_type="videos", action=Action.REWRITE,
                                      entity_id=eid,
                                      backref_predicate=str(pred),
                                      old_uri=str(video_uri), new_uri=new_uri,
                                      old_url=rec.embed_url, new_url=new_embed,
                                      reason="rescued-url-mismatch"))
                continue

            # 3. Nothing on disk → delete (just the back-reference; the VideoObject
            #    itself will be garbage-collected by apply.py if no references remain).
            manifest.add(Decision(media_type="videos", action=Action.DELETE,
                                  entity_id=eid,
                                  backref_predicate=str(pred),
                                  old_uri=str(video_uri),
                                  old_url=rec.embed_url,
                                  reason="missing-on-disk"))


def _reconcile_audio(scan: DiskScan, kg: KGIndex,
                     rescues_by_old_url: Dict[str, RescueEntry],
                     manifest: Manifest) -> None:
    for eid, records in kg.audio.items():
        if eid not in scan.entities:
            continue
        inv = scan.entities[eid]
        audio_stems = inv.audio_index  # stem -> MediaFile
        soundtrack = _load_soundtrack_links(eid)

        for rec in records:
            title = rec.title or ""
            st_entry = soundtrack.get(_norm_title(title))

            if not st_entry:
                # Track had no YouTube URL → never attempted.  Keep.
                manifest.add(Decision(media_type="audio", action=Action.KEEP,
                                      entity_id=eid,
                                      audio_bnode=str(rec.bnode),
                                      audio_title=title,
                                      reason="no-youtube-link"))
                continue

            candidates = audio_stem_candidates(
                title=st_entry.title,
                performer=st_entry.performer,
                video_id=st_entry.video_id,
            )
            found: Optional[MediaFile] = None
            for stem in candidates:
                mf = audio_stems.get(stem)
                if mf:
                    found = mf
                    break

            if found:
                manifest.add(Decision(media_type="audio", action=Action.KEEP,
                                      entity_id=eid,
                                      audio_bnode=str(rec.bnode),
                                      audio_title=title,
                                      old_url=st_entry.youtube_url,
                                      audio_file_on_disk=found.path,
                                      reason="file-on-disk"))
                continue

            # Was this URL rescued?  Audio rescues keep the same URL, only normalise
            # the on-disk filename — if we got here we already checked every plausible
            # filename, so this is a genuine delete.
            manifest.add(Decision(media_type="audio", action=Action.DELETE,
                                  entity_id=eid,
                                  audio_bnode=str(rec.bnode),
                                  audio_title=title,
                                  old_url=st_entry.youtube_url,
                                  reason="missing-on-disk"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile(scan: DiskScan, kg: KGIndex,
              rescues: List[RescueEntry]) -> Manifest:
    rescues_by_old, per_entity_rewrite = index_rescues(rescues)
    manifest = Manifest()

    logger.info("Reconciling images…")
    _reconcile_images(scan, kg, manifest)
    logger.info("Reconciling videos…")
    _reconcile_videos(scan, kg, per_entity_rewrite, manifest)
    logger.info("Reconciling audio…")
    _reconcile_audio(scan, kg, rescues_by_old, manifest)

    logger.info("Reconciliation result: %s", manifest.stats)
    return manifest
