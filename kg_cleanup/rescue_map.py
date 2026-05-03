"""Extract the ``old URL → new URL`` rewrite table from the rescue scripts.

The manual rescue scripts live in ``failed/`` and define Python literals
such as::

    RESCUES = [
        {"entity_id": "nm0491259",
         "old_url":  "https://www.imdb.com/video/vi2136393753/",
         "new_url":  "https://www.imdb.com/video/vi3679700505/",
         "name":     "Official Trailer"},
        …
    ]

We parse them with :mod:`ast` (never imported — they pull in Selenium) and
produce a flat list of :class:`RescueEntry` records the reconciler can use.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import FAILED_DIR

logger = logging.getLogger(__name__)


@dataclass
class RescueEntry:
    entity_id: str
    media_type: str                 # images | videos | audio
    old_url: Optional[str]          # None for audio rescues that only provide yt id
    new_url: Optional[str]          # None when the rescue only normalises the on-disk filename
    title: Optional[str] = None
    performer: Optional[str] = None
    video_id: Optional[str] = None  # for audio — the yt-id used as filename
    source_script: str = ""


# ---------------------------------------------------------------------------
# Generic AST helper
# ---------------------------------------------------------------------------

def _extract_literal(script_path: Path, names: List[str]) -> Dict[str, Any]:
    """Return the literal values of top-level assignments matching *names*."""
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    out: Dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in names:
                    try:
                        out[tgt.id] = ast.literal_eval(node.value)
                    except ValueError:
                        logger.warning("Could not literal-eval %s in %s",
                                       tgt.id, script_path.name)
    return out


# ---------------------------------------------------------------------------
# Per-script parsers
# ---------------------------------------------------------------------------

def _parse_video_batch(path: Path) -> List[RescueEntry]:
    data = _extract_literal(path, ["RESCUES"])
    out = []
    for item in data.get("RESCUES", []):
        out.append(RescueEntry(
            entity_id=item["entity_id"],
            media_type="videos",
            old_url=item["old_url"],
            new_url=item["new_url"],
            title=item.get("name"),
            source_script=path.name,
        ))
    return out


def _parse_nm0089185_video(path: Path) -> List[RescueEntry]:
    data = _extract_literal(path, ["ENTITY_ID", "OLD_VIDEO_URL", "NEW_VIDEO_URL", "VIDEO_NAME"])
    if not data:
        return []
    return [RescueEntry(
        entity_id=data.get("ENTITY_ID", "nm0089185"),
        media_type="videos",
        old_url=data.get("OLD_VIDEO_URL"),
        new_url=data.get("NEW_VIDEO_URL"),
        title=data.get("VIDEO_NAME"),
        source_script=path.name,
    )]


def _parse_audio_batch(path: Path) -> List[RescueEntry]:
    data = _extract_literal(path, ["RESCUES"])
    out = []
    for item in data.get("RESCUES", []):
        out.append(RescueEntry(
            entity_id=item["entity_id"],
            media_type="audio",
            old_url=item["url"],           # original YouTube URL (is in KG soundtrack files)
            new_url=item["url"],           # same — no URL rewrite, just filename normalisation
            title=item.get("title"),
            performer=item.get("performer"),
            source_script=path.name,
        ))
    return out


def _parse_tt0080455_audio(path: Path) -> List[RescueEntry]:
    data = _extract_literal(path, ["ENTITY_ID", "FAILED_YOUTUBE_IDS"])
    eid = data.get("ENTITY_ID", "tt0080455")
    out = []
    for vid_id in data.get("FAILED_YOUTUBE_IDS", []):
        out.append(RescueEntry(
            entity_id=eid,
            media_type="audio",
            old_url=f"https://www.youtube.com/watch?v={vid_id}",
            new_url=f"https://www.youtube.com/watch?v={vid_id}",
            video_id=vid_id,
            source_script=path.name,
        ))
    return out


_PARSERS = {
    "rescue_video_batch.py":   _parse_video_batch,
    "rescue_nm0089185_video.py": _parse_nm0089185_video,
    "rescue_audio_batch.py":   _parse_audio_batch,
    "rescue_tt0080455_audio.py": _parse_tt0080455_audio,
}


def load_rescue_map(failed_dir: Path = FAILED_DIR) -> List[RescueEntry]:
    entries: List[RescueEntry] = []
    for name, parser in _PARSERS.items():
        path = failed_dir / name
        if not path.exists():
            logger.warning("Rescue script missing: %s", path)
            continue
        try:
            new = parser(path)
            entries.extend(new)
            logger.info("Parsed %d entries from %s", len(new), name)
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("Failed to parse %s: %s", path, e)
    return entries


# ---------------------------------------------------------------------------
# Indexing helpers
# ---------------------------------------------------------------------------

def index_rescues(entries: List[RescueEntry]):
    """Return ``(by_old_url, per_entity_video_rewrite)``.

    * ``by_old_url``             — ``{old_url_no_slash: RescueEntry}``.
    * ``per_entity_video_rewrite`` — ``{(entity_id, old_viNNN): new_viNNN}``.
      This is per-entity because the same KG ``VideoObject`` is sometimes
      rescued to *different* new URLs for different owning entities (several
      persons shared a single broken IMDB trailer URL).
    """
    by_old_url: Dict[str, RescueEntry] = {}
    per_entity_video_rewrite: Dict = {}
    for e in entries:
        if e.old_url:
            by_old_url[e.old_url.rstrip("/")] = e
        if e.media_type == "videos" and e.old_url and e.new_url:
            m_old = re.search(r"(vi\d+)", e.old_url)
            m_new = re.search(r"(vi\d+)", e.new_url)
            if m_old and m_new:
                per_entity_video_rewrite[(e.entity_id, m_old.group(1))] = m_new.group(1)
    return by_old_url, per_entity_video_rewrite


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rescues = load_rescue_map()
    print(f"Total rescues: {len(rescues)}")
    for r in rescues[:5]:
        print(" ", r)
