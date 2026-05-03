#!/usr/bin/env python3
"""
Compute embeddings for all downloaded IMDB4M media.

Usage
-----
::

    # Embed everything (images + videos + audio), both formats
    python -m embeddings.embed_all

    # Only images, Parquet only
    python -m embeddings.embed_all --modality image --format parquet

    # Resume after interruption (default behaviour)
    python -m embeddings.embed_all --resume

    # Override batch sizes
    python -m embeddings.embed_all --image-batch 128 --video-batch 2

    # Use CPU (much slower)
    python -m embeddings.embed_all --device cpu --dtype float32
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from tqdm import tqdm

from .config import (
    DEFAULT_KG_PATH,
    DEFAULT_CACHE_PATH,
    DEFAULT_EMBED_OUTPUT_DIR,
    DEFAULT_MEDIA_DIR,
    DEFAULT_PROGRESS_FILE,
    IMAGE_BATCH_SIZE,
    VIDEO_BATCH_SIZE,
    AUDIO_BATCH_SIZE,
    TEXT_BATCH_SIZE,
)
from .scanner import MediaItem, MediaScanner
from .storage import EmbeddingAccumulator, write_all
from .text_scanner import TextItem

logger = logging.getLogger(__name__)


# ======================================================================
# Progress tracker
# ======================================================================

class ProgressTracker:
    """Tracks which files have been embedded so runs can be resumed."""

    def __init__(self, progress_file: str):
        self.path = Path(progress_file)
        self._done: Dict[str, Set[str]] = {"image": set(), "video": set(), "audio": set(), "text": set()}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for mod in ("image", "video", "audio", "text"):
                self._done[mod] = set(data.get(mod, []))
            logger.info(
                "Resumed progress: %d images, %d videos, %d audio, %d text already embedded",
                len(self._done["image"]),
                len(self._done["video"]),
                len(self._done["audio"]),
                len(self._done["text"]),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse progress file, starting fresh")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {mod: sorted(paths) for mod, paths in self._done.items()}
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def is_done(self, item: MediaItem) -> bool:
        return item.filepath in self._done[item.modality]

    def mark_done(self, item: MediaItem) -> None:
        self._done[item.modality].add(item.filepath)

    def filter_pending(self, items: List[MediaItem]) -> List[MediaItem]:
        return [it for it in items if not self.is_done(it)]


# ======================================================================
# Failure log
# ======================================================================

class FailureLog:
    """Collects per-item embedding failures and writes them to a JSON file."""

    def __init__(self, output_dir: str, filename: str = "embed_failures.json"):
        self._path = Path(output_dir) / filename
        self._records: List[Dict[str, str]] = []

    def add(self, filepath: str, modality: str, reason: str) -> None:
        self._records.append({
            "filepath": filepath,
            "modality": modality,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_all(self, failures: List[tuple], modality: str) -> None:
        """Ingest ``[(filepath, reason), …]`` from an embedder."""
        for filepath, reason in failures:
            self.add(filepath, modality, reason)

    @property
    def total(self) -> int:
        return len(self._records)

    def save(self) -> Optional[str]:
        if not self._records:
            return None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._records, f, indent=2)
        logger.info(
            "Wrote %d failure record(s) to %s", len(self._records), self._path
        )
        return str(self._path)


# ======================================================================
# Per-modality embedding drivers
# ======================================================================

def _embed_images(
    items: List[MediaItem],
    accumulator: EmbeddingAccumulator,
    tracker: ProgressTracker,
    failure_log: FailureLog,
    device: str,
    dtype: str,
    batch_size: int,
    normalize: bool,
) -> int:
    from .image_embedder import ImageEmbedder

    embedder = ImageEmbedder(device=device, dtype=dtype, batch_size=batch_size, normalize=normalize)
    count = 0
    try:
        for item, emb in tqdm(embedder.embed(items), total=len(items), desc="Images", unit="img"):
            accumulator.add(item, emb)
            tracker.mark_done(item)
            count += 1
            if count % 500 == 0:
                tracker.save()
    finally:
        failure_log.add_all(embedder.failures, "image")
        embedder.unload_model()
    tracker.save()
    return count


def _embed_videos(
    items: List[MediaItem],
    accumulator: EmbeddingAccumulator,
    tracker: ProgressTracker,
    failure_log: FailureLog,
    device: str,
    dtype: str,
    batch_size: int,
    normalize: bool,
) -> int:
    from .video_embedder import VideoEmbedder

    embedder = VideoEmbedder(device=device, dtype=dtype, batch_size=batch_size, normalize=normalize)
    count = 0
    try:
        for item, emb in tqdm(embedder.embed(items), total=len(items), desc="Videos", unit="vid"):
            accumulator.add(item, emb)
            tracker.mark_done(item)
            count += 1
            if count % 100 == 0:
                tracker.save()
    finally:
        failure_log.add_all(embedder.failures, "video")
        embedder.unload_model()
    tracker.save()
    return count


def _embed_audio(
    items: List[MediaItem],
    accumulator: EmbeddingAccumulator,
    tracker: ProgressTracker,
    failure_log: FailureLog,
    device: str,
    dtype: str,
    batch_size: int,
    normalize: bool,
) -> int:
    from .audio_embedder import AudioEmbedder

    embedder = AudioEmbedder(device=device, dtype=dtype, batch_size=batch_size, normalize=normalize)
    count = 0
    try:
        for item, emb in tqdm(embedder.embed(items), total=len(items), desc="Audio", unit="trk"):
            accumulator.add(item, emb)
            tracker.mark_done(item)
            count += 1
            if count % 100 == 0:
                tracker.save()
    finally:
        failure_log.add_all(embedder.failures, "audio")
        embedder.unload_model()
    tracker.save()
    return count


def _embed_text(
    items: List[TextItem],
    accumulator: EmbeddingAccumulator,
    tracker: ProgressTracker,
    failure_log: FailureLog,
    device: str,
    dtype: str,
    batch_size: int,
    normalize: bool,
    text_local_files_only: bool,
) -> int:
    from .text_embedder import TextEmbedder

    embedder = TextEmbedder(
        device=device,
        dtype=dtype,
        batch_size=batch_size,
        normalize=normalize,
        local_files_only=text_local_files_only,
    )
    count = 0
    try:
        for item, emb in tqdm(embedder.embed(items), total=len(items), desc="Text", unit="txt"):
            accumulator.add(item, emb)
            tracker.mark_done(item)
            count += 1
            if count % 500 == 0:
                tracker.save()
    finally:
        failure_log.add_all(embedder.failures, "text")
        embedder.unload_model()
    tracker.save()
    return count


# ======================================================================
# Main orchestrator
# ======================================================================

def embed_all(
    media_dir: str = DEFAULT_MEDIA_DIR,
    kg_path: str = DEFAULT_KG_PATH,
    output_dir: str = DEFAULT_EMBED_OUTPUT_DIR,
    cache_path: str = DEFAULT_CACHE_PATH,
    progress_file: str = DEFAULT_PROGRESS_FILE,
    modalities: Optional[List[str]] = None,
    device: str = "cuda",
    dtype: str = "float16",
    image_batch: int = IMAGE_BATCH_SIZE,
    video_batch: int = VIDEO_BATCH_SIZE,
    audio_batch: int = AUDIO_BATCH_SIZE,
    text_batch: int = TEXT_BATCH_SIZE,
    storage_format: str = "all",
    resume: bool = True,
    normalize: bool = True,
    text_local_files_only: bool = False,
) -> Dict[str, str]:
    """
    End-to-end embedding pipeline.

    Returns a dict mapping output format names to written file paths.
    """
    modalities = modalities or ["image", "video", "audio", "text"]
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # ---- Scan media --------------------------------------------------
    logger.info("Scanning media directory: %s", media_dir)
    scanner = MediaScanner(media_dir, cache_path)
    all_items: Dict[str, List[MediaItem | TextItem]] = {"image": [], "video": [], "audio": [], "text": []}

    media_modalities = [m for m in modalities if m in {"image", "video", "audio"}]
    if media_modalities:
        for item in scanner.scan(media_modalities):
            all_items[item.modality].append(item)
    if "text" in modalities:
        from .text_scanner import KGTextScanner

        all_items["text"] = list(KGTextScanner(kg_path).scan())

    for mod in modalities:
        logger.info("  %s items found: %d", mod, len(all_items[mod]))

    # ---- Filter already-done items -----------------------------------
    tracker = ProgressTracker(progress_file) if resume else ProgressTracker("/dev/null")

    pending: Dict[str, List[MediaItem | TextItem]] = {}
    for mod in modalities:
        pending[mod] = tracker.filter_pending(all_items[mod]) if resume else all_items[mod]
        if len(pending[mod]) < len(all_items[mod]):
            logger.info("  %s pending (after resume filter): %d", mod, len(pending[mod]))

    # Guard against stale progress: the progress tracker may claim items
    # are "done" from a previous run that was interrupted before writing
    # storage files.  If any items were filtered out but no output files
    # exist on disk, the progress is stale and we must re-embed everything.
    total_done = sum(len(all_items[m]) - len(pending[m]) for m in modalities)
    if resume and total_done > 0:
        out = Path(output_dir)
        _expected = [out / f"{m}_embeddings.parquet" for m in modalities]
        _expected.append(out / "embeddings.h5")
        if not any(p.exists() for p in _expected):
            logger.warning(
                "Progress file says %d items are done, but no output files "
                "exist in %s -- previous run likely crashed before writing. "
                "Resetting progress and re-embedding everything.",
                total_done,
                output_dir,
            )
            tracker = ProgressTracker("/dev/null")
            for mod in modalities:
                pending[mod] = all_items[mod]

    total_pending = sum(len(v) for v in pending.values())
    if total_pending == 0:
        logger.info("Nothing to embed -- all files already processed.")
        return {}

    # ---- Embed -------------------------------------------------------
    accumulator = EmbeddingAccumulator()
    failure_log = FailureLog(output_dir)
    stats: Dict[str, int] = {}
    t0 = time.time()

    if "image" in modalities and pending["image"]:
        stats["image"] = _embed_images(
            pending["image"], accumulator, tracker, failure_log,
            device, dtype, image_batch, normalize,
        )
        logger.info("Flushing image embeddings to storage …")
        results = write_all(accumulator, output_dir, formats=storage_format)

    if "video" in modalities and pending["video"]:
        stats["video"] = _embed_videos(
            pending["video"], accumulator, tracker, failure_log,
            device, dtype, video_batch, normalize,
        )
        logger.info("Flushing image+video embeddings to storage …")
        results = write_all(accumulator, output_dir, formats=storage_format)

    if "audio" in modalities and pending["audio"]:
        stats["audio"] = _embed_audio(
            pending["audio"], accumulator, tracker, failure_log,
            device, dtype, audio_batch, normalize,
        )
        logger.info("Flushing all embeddings to storage …")
        results = write_all(accumulator, output_dir, formats=storage_format)

    if "text" in modalities and pending["text"]:
        stats["text"] = _embed_text(
            pending["text"], accumulator, tracker, failure_log,
            device, dtype, text_batch, normalize, text_local_files_only,
        )
        logger.info("Flushing all embeddings including text to storage …")
        results = write_all(accumulator, output_dir, formats=storage_format)

    elapsed = time.time() - t0
    logger.info(
        "Embedding complete in %.1fs -- images: %d, videos: %d, audio: %d, text: %d",
        elapsed,
        stats.get("image", 0),
        stats.get("video", 0),
        stats.get("audio", 0),
        stats.get("text", 0),
    )

    if failure_log.total:
        logger.warning("%d item(s) failed to embed", failure_log.total)

    # Final write ensures storage is up-to-date even if only the last
    # modality had pending items (in which case earlier flushes were skipped).
    logger.info("Final write (format=%s) to %s", storage_format, output_dir)
    results = write_all(accumulator, output_dir, formats=storage_format)

    failure_path = failure_log.save()
    if failure_path:
        results["failures"] = failure_path

    for fmt, path in results.items():
        logger.info("  %s -> %s", fmt, path)

    return results


# ======================================================================
# CLI
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute media embeddings for the IMDB4M Knowledge Graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--media-dir", default=DEFAULT_MEDIA_DIR, help="Root directory of downloaded media (default: output)")
    parser.add_argument("--kg", default=DEFAULT_KG_PATH, help="KG Turtle file for text embeddings (default: data/kg/imdb_kg_cleaned.pruned.ttl)")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_EMBED_OUTPUT_DIR, help="Where to write embedding files (default: embeddings_output)")
    parser.add_argument("--cache-path", default=DEFAULT_CACHE_PATH, help="Path to entity_cache.json (default: output/entity_cache.json)")
    parser.add_argument("--progress-file", default=DEFAULT_PROGRESS_FILE, help="Progress checkpoint file (default: embeddings_output/embed_progress.json)")

    parser.add_argument(
        "--modality", "-m",
        nargs="+",
        choices=["image", "video", "audio", "text"],
        default=["image", "video", "audio", "text"],
        help="Which modalities to embed (default: all four)",
    )

    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Torch device (default: cuda)")
    parser.add_argument("--dtype", default="float16", choices=["float16", "float32"], help="Model dtype (default: float16)")

    parser.add_argument("--image-batch", type=int, default=IMAGE_BATCH_SIZE, help=f"Image batch size (default: {IMAGE_BATCH_SIZE})")
    parser.add_argument("--video-batch", type=int, default=VIDEO_BATCH_SIZE, help=f"Video batch size (default: {VIDEO_BATCH_SIZE})")
    parser.add_argument("--audio-batch", type=int, default=AUDIO_BATCH_SIZE, help=f"Audio batch size (default: {AUDIO_BATCH_SIZE})")
    parser.add_argument("--text-batch", type=int, default=TEXT_BATCH_SIZE, help=f"Text batch size (default: {TEXT_BATCH_SIZE})")

    parser.add_argument(
        "--format", "-f",
        dest="storage_format",
        default="all",
        choices=["parquet", "hdf5", "all"],
        help="Output format: parquet (+ TTL), hdf5, or all (default: all)",
    )

    parser.add_argument("--no-resume", action="store_true", help="Ignore previous progress and re-embed everything")
    parser.add_argument("--no-normalize", action="store_true", help="Skip L2 normalisation of embeddings")
    parser.add_argument(
        "--text-local-files-only",
        action="store_true",
        help="Require the text model to already exist in the local HuggingFace cache",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(name)-28s  %(levelname)-8s  %(message)s",
    )

    logger.info("=" * 60)
    logger.info("IMDB4M Embedding Pipeline")
    logger.info("=" * 60)
    logger.info("Media dir:    %s", args.media_dir)
    logger.info("KG:           %s", args.kg)
    logger.info("Output dir:   %s", args.output_dir)
    logger.info("Modalities:   %s", ", ".join(args.modality))
    logger.info("Device:       %s", args.device)
    logger.info("Dtype:        %s", args.dtype)
    logger.info("Format:       %s", args.storage_format)
    logger.info("Resume:       %s", not args.no_resume)
    logger.info("Normalize:    %s", not args.no_normalize)
    logger.info("Text offline: %s", args.text_local_files_only)
    logger.info("Batch sizes:  img=%d  vid=%d  aud=%d  text=%d", args.image_batch, args.video_batch, args.audio_batch, args.text_batch)
    logger.info("=" * 60)

    try:
        results = embed_all(
            media_dir=args.media_dir,
            kg_path=args.kg,
            output_dir=args.output_dir,
            cache_path=args.cache_path,
            progress_file=args.progress_file,
            modalities=args.modality,
            device=args.device,
            dtype=args.dtype,
            image_batch=args.image_batch,
            video_batch=args.video_batch,
            audio_batch=args.audio_batch,
            text_batch=args.text_batch,
            storage_format=args.storage_format,
            resume=not args.no_resume,
            normalize=not args.no_normalize,
            text_local_files_only=args.text_local_files_only,
        )

        print("\n" + "=" * 60)
        print("Embedding Pipeline Complete")
        print("=" * 60)
        for fmt, path in results.items():
            print(f"  {fmt:10s} -> {path}")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress saved -- re-run to resume.")
        sys.exit(130)
    except Exception:
        logger.exception("Embedding pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
