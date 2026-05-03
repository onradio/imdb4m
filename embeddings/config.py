"""
Configuration constants for the embedding pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Model identifiers (HuggingFace Hub)
# ---------------------------------------------------------------------------

IMAGE_MODEL_ID = "openai/clip-vit-large-patch14"
VIDEO_MODEL_ID = "microsoft/xclip-base-patch32"
AUDIO_MODEL_ID = "laion/larger_clap_music_and_speech"
TEXT_MODEL_ID = "BAAI/bge-large-en-v1.5"

# ---------------------------------------------------------------------------
# Embedding dimensions produced by each model
# ---------------------------------------------------------------------------

IMAGE_EMBED_DIM = 768
VIDEO_EMBED_DIM = 512
AUDIO_EMBED_DIM = 512
TEXT_EMBED_DIM = 1024

# ---------------------------------------------------------------------------
# Default batch sizes (tuned for RTX 3090 24 GB, FP16 inference)
# ---------------------------------------------------------------------------

IMAGE_BATCH_SIZE = 64
VIDEO_BATCH_SIZE = 4
AUDIO_BATCH_SIZE = 16
TEXT_BATCH_SIZE = 32

# ---------------------------------------------------------------------------
# Preprocessing constants
# ---------------------------------------------------------------------------

VIDEO_NUM_FRAMES = 8          # uniform-sample frame count for X-CLIP
AUDIO_SAMPLE_RATE = 48_000    # CLAP expects 48 kHz
AUDIO_CHUNK_SECONDS = 10      # max window per CLAP forward pass
TEXT_MAX_TOKENS = 512         # BGE encoder context window
TEXT_CHUNK_STRIDE = 64        # overlap between long-text chunks

# ---------------------------------------------------------------------------
# Output paths (relative to project root by default)
# ---------------------------------------------------------------------------

DEFAULT_MEDIA_DIR = "output"
DEFAULT_EMBED_OUTPUT_DIR = "embeddings_output"
DEFAULT_CACHE_PATH = "output/entity_cache.json"
DEFAULT_PROGRESS_FILE = "embeddings_output/embed_progress.json"
DEFAULT_KG_PATH = "data/kg/imdb_kg_cleaned.pruned.ttl"


@dataclass
class EmbedConfig:
    """Runtime configuration assembled from CLI flags."""

    media_dir: str = DEFAULT_MEDIA_DIR
    output_dir: str = DEFAULT_EMBED_OUTPUT_DIR
    cache_path: str = DEFAULT_CACHE_PATH
    progress_file: str = DEFAULT_PROGRESS_FILE

    device: str = "cuda"
    dtype: str = "float16"  # "float16" | "float32"

    image_batch_size: int = IMAGE_BATCH_SIZE
    video_batch_size: int = VIDEO_BATCH_SIZE
    audio_batch_size: int = AUDIO_BATCH_SIZE
    text_batch_size: int = TEXT_BATCH_SIZE

    modalities: list = field(default_factory=lambda: ["image", "video", "audio", "text"])
    storage_format: str = "all"  # "parquet" | "hdf5" | "all"

    resume: bool = True
    normalize: bool = True  # L2-normalize embeddings before storing
