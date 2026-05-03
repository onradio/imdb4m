"""Keep the JSON book-keeping files in sync with the pruned KG.

Only the *main* JSON sidecars are touched:

* ``output/entity_cache.json``       — remove/rewrite media entries
* ``output/download_progress.json``  — move purged URLs into a new
                                       ``purged`` bucket (audit trail)

Per the user's instruction we deliberately **do not** touch
``data/movies/<tt>/movie_soundtrack/soundtrack_links.json`` nor the
per-movie ``tt<id>_soundtrack.ttl`` — that metadata is preserved so
researchers can still analyse which tracks exist at IMDB even if the
audio file wasn't recoverable.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .config import ENTITY_CACHE_PATH, PROGRESS_PATH
from .reconcile import Action, Decision, Manifest

logger = logging.getLogger(__name__)


def _video_id(url: str) -> str:
    m = re.search(r"(vi\d+)", url or "")
    return m.group(1) if m else ""


def sync_entity_cache(manifest: Manifest,
                      cache_path: Path = ENTITY_CACHE_PATH,
                      dry_run: bool = False) -> Dict[str, int]:
    if not cache_path.exists():
        logger.warning("entity_cache.json not found at %s", cache_path)
        return {}

    backup = cache_path.with_suffix(".json.bak")
    if not dry_run and not backup.exists():
        shutil.copy2(cache_path, backup)
        logger.info("Backed up %s → %s", cache_path, backup)

    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)

    stats = {"images_removed": 0, "videos_removed": 0, "videos_rewritten": 0,
             "audio_removed": 0}

    # Group decisions by entity for efficient iteration
    by_entity: Dict[str, List[Decision]] = {}
    for d in manifest.decisions:
        if d.action is Action.KEEP:
            continue
        by_entity.setdefault(d.entity_id, []).append(d)

    entities = cache.get("entities", {})
    for eid, decisions in by_entity.items():
        ent = entities.get(eid)
        if not ent:
            continue

        # --- IMAGES: delete by cdn url -------------------------------------
        img_deletes = {d.old_url for d in decisions
                       if d.media_type == "images" and d.action is Action.DELETE}
        if img_deletes:
            before = len(ent.get("images", []))
            ent["images"] = [i for i in ent.get("images", []) if i.get("url") not in img_deletes]
            stats["images_removed"] += before - len(ent["images"])

        # --- VIDEOS: rewrite URI+embed; delete --------------------------------
        vid_rewrites = {_video_id(d.old_url): _video_id(d.new_url)
                        for d in decisions if d.media_type == "videos"
                        and d.action is Action.REWRITE}
        vid_deletes = {d.old_url for d in decisions
                       if d.media_type == "videos" and d.action is Action.DELETE}
        new_videos = []
        for v in ent.get("videos", []):
            vid = _video_id(v.get("uri", "") or v.get("embed_url", ""))
            if vid_rewrites.get(vid):
                new_vid = vid_rewrites[vid]
                v["uri"] = re.sub(r"vi\d+", new_vid, v.get("uri", ""))
                v["embed_url"] = re.sub(r"vi\d+", new_vid, v.get("embed_url", ""))
                stats["videos_rewritten"] += 1
                new_videos.append(v)
                continue
            if v.get("uri") in vid_deletes or v.get("embed_url") in vid_deletes:
                stats["videos_removed"] += 1
                continue
            new_videos.append(v)
        ent["videos"] = new_videos

        # --- AUDIO: delete by YouTube URL -------------------------------------
        aud_deletes = {d.old_url for d in decisions
                       if d.media_type == "audio" and d.action is Action.DELETE
                       and d.old_url}
        if aud_deletes:
            before = len(ent.get("audio", []))
            ent["audio"] = [a for a in ent.get("audio", [])
                            if a.get("youtube_url") not in aud_deletes]
            stats["audio_removed"] += before - len(ent["audio"])

    if dry_run:
        logger.info("entity_cache dry run: %s", stats)
        return stats

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    logger.info("Rewrote %s: %s", cache_path.name, stats)
    return stats


def sync_progress(manifest: Manifest,
                  progress_path: Path = PROGRESS_PATH,
                  dry_run: bool = False) -> Dict[str, int]:
    """Move purged failure URLs into a ``purged`` bucket for audit trail."""
    if not progress_path.exists():
        logger.warning("download_progress.json not found at %s", progress_path)
        return {}

    backup = progress_path.with_suffix(".json.bak")
    if not dry_run and not backup.exists():
        shutil.copy2(progress_path, backup)
        logger.info("Backed up %s → %s", progress_path, backup)

    with open(progress_path, encoding="utf-8") as f:
        prog = json.load(f)

    stats = {"images_purged": 0, "videos_purged": 0, "audio_purged": 0,
             "videos_promoted": 0, "audio_promoted": 0}

    deletes_by_entity: Dict[str, Dict[str, set]] = {}
    rewrites_by_entity: Dict[str, Dict[str, Dict[str, str]]] = {}
    for d in manifest.decisions:
        if d.action is Action.DELETE:
            deletes_by_entity.setdefault(d.entity_id, {}).setdefault(d.media_type, set())
            if d.old_url:
                deletes_by_entity[d.entity_id][d.media_type].add(d.old_url)
        elif d.action is Action.REWRITE and d.old_url and d.new_url:
            rewrites_by_entity.setdefault(d.entity_id, {}).setdefault(d.media_type, {})
            rewrites_by_entity[d.entity_id][d.media_type][d.old_url] = d.new_url

    for eid, ent in prog.get("entities", {}).items():
        del_sets = deletes_by_entity.get(eid, {})
        rew_sets = rewrites_by_entity.get(eid, {})

        for mt in ("images", "videos", "audio"):
            bucket = ent.get(mt, {})
            if not bucket:
                continue

            # DELETE: move from failed → purged
            urls_to_purge = del_sets.get(mt, set())
            if urls_to_purge:
                purged = bucket.setdefault("purged", [])
                new_failed = []
                for item in bucket.get("failed", []):
                    if item.get("url") in urls_to_purge:
                        purged.append({
                            **item,
                            "purged_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        })
                        stats[f"{mt}_purged"] += 1
                    else:
                        new_failed.append(item)
                bucket["failed"] = new_failed

            # REWRITE for videos: make sure the new URL is in downloaded and old not in failed
            rew_map = rew_sets.get(mt, {})
            if rew_map:
                downloaded = bucket.setdefault("downloaded", [])
                bucket["failed"] = [f for f in bucket.get("failed", [])
                                    if f.get("url") not in rew_map]
                for old, new in rew_map.items():
                    if new not in downloaded:
                        downloaded.append(new)
                        stats[f"{mt}_promoted"] += 1

    if dry_run:
        logger.info("download_progress dry run: %s", stats)
        return stats

    prog["last_updated"] = datetime.now().isoformat()
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(prog, f, indent=2)
    logger.info("Rewrote %s: %s", progress_path.name, stats)
    return stats
