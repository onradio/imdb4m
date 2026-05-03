"""Shared paths + constants for the release pipeline.

All paths resolve from the project root so the pipeline can be invoked
from anywhere (``python -m release``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

PRUNED_KG = PROJECT_ROOT / "data" / "kg" / "imdb_kg_cleaned.pruned.ttl"
FAILED_KG = PROJECT_ROOT / "data" / "kg" / "imdb_kg_failed_media.ttl"
SIDECAR_MANIFEST = PROJECT_ROOT / "output" / "kg_cleanup" / "manifest.json"

EMBED_DIR = PROJECT_ROOT / "embeddings_output"
IMAGE_PARQUET = EMBED_DIR / "image_embeddings.parquet"
VIDEO_PARQUET = EMBED_DIR / "video_embeddings.parquet"
AUDIO_PARQUET = EMBED_DIR / "audio_embeddings.parquet"
TEXT_PARQUET = EMBED_DIR / "text_embeddings.parquet"
EMBEDDINGS_H5 = EMBED_DIR / "embeddings.h5"
EMBED_METADATA_TTL = EMBED_DIR / "embedding_metadata.ttl"

MOVIES_DIR = PROJECT_ROOT / "data" / "movies"

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

RELEASE_ROOT = PROJECT_ROOT / "release_output"
BUNDLE_NAME = "imdb4m-release-v1"
BUNDLE_DIR = RELEASE_ROOT / BUNDLE_NAME
ALIGNMENT_REPORT = RELEASE_ROOT / "alignment_report.json"
EMBEDDINGS_CARD = RELEASE_ROOT / "embeddings_card.json"
REGENERATED_TTL = RELEASE_ROOT / "embedding_metadata.regenerated.ttl"
ENHANCED_H5 = RELEASE_ROOT / "embeddings.enhanced.h5"
MANIFEST_SHA = RELEASE_ROOT / "MANIFEST.sha256"

# ---------------------------------------------------------------------------
# Embedding model metadata (keep in sync with embeddings/config.py)
# ---------------------------------------------------------------------------

IMAGE_MODEL_ID = "openai/clip-vit-large-patch14"
VIDEO_MODEL_ID = "microsoft/xclip-base-patch32"
AUDIO_MODEL_ID = "laion/larger_clap_music_and_speech"
TEXT_MODEL_ID = "BAAI/bge-large-en-v1.5"

IMAGE_EMBED_DIM = 768
VIDEO_EMBED_DIM = 512
AUDIO_EMBED_DIM = 512
TEXT_EMBED_DIM = 1024

# Pinned HF revisions.  Left empty by default -- fill with actual commit
# SHAs at release time if known.  ``main`` means the snapshot of the
# model as it existed on HuggingFace at embedding time.
MODEL_REVISIONS = {
    IMAGE_MODEL_ID: "main",
    VIDEO_MODEL_ID: "main",
    AUDIO_MODEL_ID: "main",
    TEXT_MODEL_ID: "main",
}

SCHEMA_NS = "http://schema.org/"


@dataclass
class AudioKGRecord:
    """Minimal audio record pulled from the pruned KG."""

    entity_id: str
    title: str
    artists: tuple


IMAGE_EXT = ".jpg"
