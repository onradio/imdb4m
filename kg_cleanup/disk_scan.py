"""Scan the ``output/`` directory tree and produce a ground-truth inventory.

This module deliberately does **not** trust the JSON bookkeeping files
(``entity_cache.json`` / ``download_progress.json`` / ``integrity_audit.json``).
For each entity folder under ``output/<entity_id>/`` it simply enumerates the
``images/``, ``videos/`` and ``audio/`` subdirectories and records every file
with its basename, extension, size, and a set of lookup keys derived from the
downloaders' naming conventions.

The resulting JSON-serialisable structure is consumed by :mod:`reconcile`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import unquote, urlparse

from .config import (
    AUDIO_EXTS,
    DISK_SCAN_PATH,
    IMAGE_EXTS,
    MIN_VALID_BYTES,
    OUTPUT_DIR,
    VIDEO_EXTS,
)

logger = logging.getLogger(__name__)

ENTITY_ID_RE = re.compile(r"^(?:tt|nm)\d+$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MediaFile:
    """A single media file discovered on disk."""
    entity_id: str
    media_type: str          # images | videos | audio
    path: str
    filename: str
    stem: str                # filename without extension
    ext: str                 # lower-case extension including leading dot
    size: int
    valid: bool              # size >= MIN_VALID_BYTES

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EntityInventory:
    """All media files found under a single entity directory."""
    entity_id: str
    images: List[MediaFile] = field(default_factory=list)
    videos: List[MediaFile] = field(default_factory=list)
    audio: List[MediaFile] = field(default_factory=list)

    @property
    def image_index(self) -> Dict[str, MediaFile]:
        """Filename-stem lookup for images (stem = basename sans extension)."""
        return {mf.stem: mf for mf in self.images if mf.valid}

    @property
    def video_index(self) -> Dict[str, MediaFile]:
        """Index videos by the ``viNNN`` id embedded at the start of the filename."""
        out: Dict[str, MediaFile] = {}
        for mf in self.videos:
            if not mf.valid:
                continue
            m = re.match(r"(vi\d+)", mf.stem)
            if m:
                out[m.group(1)] = mf
        return out

    @property
    def audio_index(self) -> Dict[str, MediaFile]:
        """
        Index audio by **multiple** keys to tolerate the different naming schemes
        used by the initial run and the rescue scripts:

        * ``<performer>-<title>``          (canonical AudioDownloader format)
        * ``<title>``                      (no-performer variant)
        * ``<youtube_video_id>``           (rescue_tt0080455_audio.py format)
        """
        out: Dict[str, MediaFile] = {}
        for mf in self.audio:
            if not mf.valid:
                continue
            out[mf.stem] = mf
        return out


@dataclass
class DiskScan:
    """Full inventory of everything under ``output/``."""
    scanned_at: str
    root: str
    entities: Dict[str, EntityInventory] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        return sum(len(e.images) + len(e.videos) + len(e.audio)
                   for e in self.entities.values())

    def to_dict(self) -> dict:
        return {
            "scanned_at": self.scanned_at,
            "root": self.root,
            "total_entities": len(self.entities),
            "total_files": self.total_files,
            "entities": {
                eid: {
                    "images": [m.to_dict() for m in inv.images],
                    "videos": [m.to_dict() for m in inv.videos],
                    "audio":  [m.to_dict() for m in inv.audio],
                }
                for eid, inv in self.entities.items()
            },
        }


# ---------------------------------------------------------------------------
# Helpers — mirror the downloaders' filename rules exactly
# ---------------------------------------------------------------------------

def image_filename_from_url(url: str) -> str:
    """Reproduce :meth:`ImageDownloader._get_filename_from_url`.

    ``https://m.media-amazon.com/images/M/MV5B…@._V1_.jpg`` becomes
    ``MV5B…_._V1_.jpg`` on disk (the ``@`` collapses to ``_``).
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = Path(path).name
    filename = re.sub(r"[^\w\-_\.]", "_", filename)
    if not any(filename.lower().endswith(ext) for ext in IMAGE_EXTS):
        filename += ".jpg"
    return filename


def image_stem_from_url(url: str) -> str:
    """Same as :func:`image_filename_from_url` but without the extension."""
    fn = image_filename_from_url(url)
    return Path(fn).stem


def video_id_from_url(url: str) -> Optional[str]:
    """Extract the ``viNNN`` token from an IMDB embed URL."""
    m = re.search(r"(vi\d+)", url or "")
    return m.group(1) if m else None


def audio_stem_candidates(title: str, performer: Optional[str],
                          video_id: Optional[str]) -> List[str]:
    """Enumerate every filename stem an audio track may be saved under.

    Mirrors :meth:`AudioDownloader._sanitize_filename` plus the
    ``<video_id>`` fallback produced by the ``failed/rescue_*_audio.py`` scripts.
    """
    def _sanitize(s: str, max_len: int = 100) -> str:
        s = re.sub(r'[<>:"/\\|?*]', '', s)
        s = re.sub(r'\s+', '_', s)
        s = s.strip('._')
        if len(s) > max_len:
            s = s[:max_len]
        return s or "audio"

    stems: List[str] = []
    title_clean = _sanitize(title)
    if performer:
        stems.append(f"{_sanitize(performer)}-{title_clean}")
    stems.append(title_clean)
    if video_id:
        stems.append(video_id)
    # also accept youtube id without leading dash (some rescue files lose it)
    return stems


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _collect(entity_dir: Path, sub: str, exts: set) -> List[MediaFile]:
    out: List[MediaFile] = []
    d = entity_dir / sub
    if not d.is_dir():
        return out
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out.append(MediaFile(
            entity_id=entity_dir.name,
            media_type=sub,
            path=str(p),
            filename=p.name,
            stem=p.stem,
            ext=p.suffix.lower(),
            size=size,
            valid=size >= MIN_VALID_BYTES,
        ))
    return out


def scan_output(output_dir: Path = OUTPUT_DIR,
                entity_filter: Optional[Iterable[str]] = None) -> DiskScan:
    """Walk ``output/`` and return the full :class:`DiskScan`."""
    from datetime import datetime

    out = DiskScan(scanned_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                   root=str(output_dir))
    want = set(entity_filter) if entity_filter else None

    for entity_dir in sorted(output_dir.iterdir()):
        if not entity_dir.is_dir():
            continue
        eid = entity_dir.name
        if not ENTITY_ID_RE.match(eid):
            continue
        if want is not None and eid not in want:
            continue
        inv = EntityInventory(entity_id=eid)
        inv.images = _collect(entity_dir, "images", IMAGE_EXTS)
        inv.videos = _collect(entity_dir, "videos", VIDEO_EXTS)
        inv.audio  = _collect(entity_dir, "audio",  AUDIO_EXTS)
        # Keep the entity even when every sub-folder is empty: an empty
        # folder means we *attempted* to download something for this
        # entity but every asset failed.  Dropping it here would make the
        # reconciler treat the entity as "never attempted" and leave
        # stale KG triples behind.
        if (inv.images or inv.videos or inv.audio
                or any((entity_dir / sub).is_dir() for sub in ("images", "videos", "audio"))):
            out.entities[eid] = inv

    logger.info("Disk scan: %d entities, %d files",
                len(out.entities), out.total_files)
    return out


def save_disk_scan(scan: DiskScan, path: Path = DISK_SCAN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scan.to_dict(), f, indent=2)
    logger.info("Wrote %s", path)


def load_disk_scan(path: Path = DISK_SCAN_PATH) -> DiskScan:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = DiskScan(scanned_at=raw["scanned_at"], root=raw["root"])
    for eid, buckets in raw["entities"].items():
        inv = EntityInventory(entity_id=eid)
        for mt_key in ("images", "videos", "audio"):
            lst = [MediaFile(**m) for m in buckets.get(mt_key, [])]
            setattr(inv, mt_key, lst)
        out.entities[eid] = inv
    return out


if __name__ == "__main__":  # manual smoke test
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    scan = scan_output()
    save_disk_scan(scan)
    print(f"Entities: {len(scan.entities)}  Files: {scan.total_files}")
