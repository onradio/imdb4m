"""
MediaScanner -- walks the media output directory and maps every file back to
its KG entity URI and original source URL using the entity cache.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov"}
AUDIO_EXTENSIONS = {".m4a", ".opus", ".mp3", ".wav", ".webm", ".ogg", ".flac"}


@dataclass(frozen=True)
class MediaItem:
    """A single media file with its KG linkage metadata."""

    entity_id: str       # e.g. "tt0120338" or "nm0000138"
    kg_uri: str          # full schema.org URI of the *entity*
    source_url: str      # original CDN / IMDB / YouTube URL
    modality: str        # "image" | "video" | "audio"
    filepath: str        # absolute path on disk
    filename: str        # basename of the file


class MediaScanner:
    """
    Scans the media directory and yields :class:`MediaItem` objects that tie
    each file on disk to its KG entity and original source URL.
    """

    def __init__(self, media_dir: str, cache_path: str):
        self.media_dir = Path(media_dir)
        self.cache_path = Path(cache_path)
        self._cache: Optional[Dict] = None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cache(self) -> Dict:
        if self._cache is not None:
            return self._cache
        if not self.cache_path.exists():
            logger.warning("Entity cache not found at %s – source URLs will be empty", self.cache_path)
            self._cache = {}
            return self._cache
        with open(self.cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._cache = raw.get("entities", {})
        logger.info("Loaded entity cache with %d entities", len(self._cache))
        return self._cache

    def _entity_uri(self, entity_id: str) -> str:
        cache = self._load_cache()
        entry = cache.get(entity_id, {})
        if entry:
            return entry.get("uri", "")
        if entity_id.startswith("tt"):
            return f"https://www.imdb.com/title/{entity_id}/"
        if entity_id.startswith("nm"):
            return f"https://www.imdb.com/name/{entity_id}/"
        return ""

    # ------------------------------------------------------------------
    # Source-URL resolution
    # ------------------------------------------------------------------

    def _image_source_urls(self, entity_id: str) -> Dict[str, str]:
        """Map image filenames to their original CDN URL."""
        cache = self._load_cache()
        entry = cache.get(entity_id, {})
        urls: Dict[str, str] = {}
        for img in entry.get("images", []):
            url = img.get("url", "")
            if url:
                fname = url.rsplit("/", 1)[-1]
                urls[fname] = url
        return urls

    def _video_source_urls(self, entity_id: str) -> Dict[str, str]:
        """Map video filenames (vi<id>_*.mp4) to their IMDB embed URL."""
        cache = self._load_cache()
        entry = cache.get(entity_id, {})
        urls: Dict[str, str] = {}
        for vid in entry.get("videos", []):
            embed = vid.get("embed_url", "")
            if embed:
                vid_id = embed.rstrip("/").rsplit("/", 1)[-1]
                urls[vid_id] = embed
        return urls

    def _audio_source_urls(self, entity_id: str) -> Dict[str, str]:
        """Map audio filenames to their YouTube URL."""
        cache = self._load_cache()
        entry = cache.get(entity_id, {})
        urls: Dict[str, str] = {}
        for aud in entry.get("audio", []):
            yt_url = aud.get("youtube_url", "")
            if yt_url:
                title = aud.get("title", "")
                performer = aud.get("performer", "")
                key = self._sanitize_audio_key(performer, title)
                urls[key] = yt_url
        return urls

    @staticmethod
    def _sanitize_audio_key(performer: str, title: str) -> str:
        """Reproduce the naming logic used by audio_downloader."""
        def clean(s: str) -> str:
            s = re.sub(r'[<>:"/\\|?*]', "", s)
            s = s.replace(" ", "_")
            return s.strip("._")
        parts = []
        if performer:
            parts.append(clean(performer))
        if title:
            parts.append(clean(title))
        return "-".join(parts) if parts else ""

    def _resolve_video_source(self, filename: str, url_map: Dict[str, str]) -> str:
        for vid_id, url in url_map.items():
            if vid_id in filename:
                return url
        return ""

    def _resolve_audio_source(self, filename: str, url_map: Dict[str, str]) -> str:
        stem = Path(filename).stem
        for key, url in url_map.items():
            if key and key in stem:
                return url
        return ""

    # ------------------------------------------------------------------
    # Public scanning API
    # ------------------------------------------------------------------

    def scan(self, modalities: Optional[List[str]] = None) -> Iterator[MediaItem]:
        """
        Yield :class:`MediaItem` for every media file found on disk.

        Args:
            modalities: subset of ``["image", "video", "audio"]`` to scan;
                        ``None`` means all three.
        """
        modalities = modalities or ["image", "video", "audio"]
        mod_set = set(modalities)

        if not self.media_dir.is_dir():
            logger.error("Media directory does not exist: %s", self.media_dir)
            return

        for entity_dir in sorted(self.media_dir.iterdir()):
            if not entity_dir.is_dir():
                continue
            entity_id = entity_dir.name
            if not (entity_id.startswith("tt") or entity_id.startswith("nm")):
                continue

            kg_uri = self._entity_uri(entity_id)

            if "image" in mod_set:
                yield from self._scan_modality(entity_id, kg_uri, entity_dir / "images", "image")
            if "video" in mod_set:
                yield from self._scan_modality(entity_id, kg_uri, entity_dir / "videos", "video")
            if "audio" in mod_set:
                yield from self._scan_modality(entity_id, kg_uri, entity_dir / "audio", "audio")

    def _scan_modality(
        self, entity_id: str, kg_uri: str, subdir: Path, modality: str
    ) -> Iterator[MediaItem]:
        if not subdir.is_dir():
            return

        exts = {"image": IMAGE_EXTENSIONS, "video": VIDEO_EXTENSIONS, "audio": AUDIO_EXTENSIONS}[modality]

        if modality == "image":
            url_map = self._image_source_urls(entity_id)
        elif modality == "video":
            url_map = self._video_source_urls(entity_id)
        else:
            url_map = self._audio_source_urls(entity_id)

        for fp in sorted(subdir.iterdir()):
            if not fp.is_file():
                continue
            if fp.suffix.lower() not in exts:
                continue

            if modality == "image":
                source_url = url_map.get(fp.name, "")
            elif modality == "video":
                source_url = self._resolve_video_source(fp.name, url_map)
            else:
                source_url = self._resolve_audio_source(fp.name, url_map)

            yield MediaItem(
                entity_id=entity_id,
                kg_uri=kg_uri,
                source_url=source_url,
                modality=modality,
                filepath=str(fp),
                filename=fp.name,
            )

    def count(self, modalities: Optional[List[str]] = None) -> Dict[str, int]:
        """Quick count of files per modality without loading cache URLs."""
        modalities = modalities or ["image", "video", "audio"]
        counts: Dict[str, int] = {m: 0 for m in modalities}
        for item in self.scan(modalities):
            counts[item.modality] += 1
        return counts
