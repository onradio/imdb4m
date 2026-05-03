"""
Audio embedder using CLAP (LAION).

Loads ``laion/larger_clap_music_and_speech`` from HuggingFace, resamples
audio to 48 kHz mono, chunks files longer than 10 s, mean-pools the chunk
embeddings, and returns L2-normalised 512-d vectors.
"""

import logging
import os
import subprocess
import tempfile
from typing import Iterator, List, Tuple

import librosa
import numpy as np
import soundfile as sf
import torch
from transformers import ClapModel, ClapProcessor

from .config import (
    AUDIO_MODEL_ID,
    AUDIO_EMBED_DIM,
    AUDIO_BATCH_SIZE,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHUNK_SECONDS,
)
from .scanner import MediaItem

logger = logging.getLogger(__name__)

# Ensure the bundled FFmpeg (from imageio-ffmpeg) is on PATH so that
# audioread / pydub can find it even if system FFmpeg is not installed.
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        logger.debug("Added imageio-ffmpeg to PATH: %s", _ffmpeg_dir)
except ImportError:
    pass

_FFMPEG_EXE: str | None = None


def _get_ffmpeg() -> str | None:
    """Return path to an ffmpeg binary, or None."""
    global _FFMPEG_EXE
    if _FFMPEG_EXE is not None:
        return _FFMPEG_EXE
    try:
        import imageio_ffmpeg
        _FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        import shutil
        _FFMPEG_EXE = shutil.which("ffmpeg") or ""
    return _FFMPEG_EXE or None


def _load_with_ffmpeg(filepath: str, sr: int) -> np.ndarray | None:
    """Decode audio to mono float32 WAV via FFmpeg, then read with soundfile."""
    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            subprocess.run(
                [ffmpeg, "-y", "-i", filepath,
                 "-ac", "1", "-ar", str(sr), "-f", "wav", tmp.name],
                capture_output=True, check=True, timeout=120,
            )
            waveform, _ = sf.read(tmp.name, dtype="float32")
        return waveform
    except Exception as e:
        logger.debug("FFmpeg fallback failed for %s: %s", filepath, e)
        return None


def load_and_chunk_audio(
    filepath: str,
    sr: int = AUDIO_SAMPLE_RATE,
    chunk_seconds: int = AUDIO_CHUNK_SECONDS,
) -> List[np.ndarray]:
    """
    Load an audio file, resample to *sr* Hz mono, and split into
    non-overlapping chunks of *chunk_seconds*.

    Returns a list of 1-D float32 numpy arrays (at least one chunk).
    """
    waveform = None

    # Fast path: librosa + soundfile (handles wav, flac, ogg, opus, mp3)
    try:
        waveform, _ = librosa.load(filepath, sr=sr, mono=True)
    except Exception:
        pass

    # Fallback: decode via FFmpeg subprocess (handles m4a, aac, wma, etc.)
    if waveform is None or waveform.size == 0:
        waveform = _load_with_ffmpeg(filepath, sr)

    if waveform is None or waveform.size == 0:
        logger.warning("Cannot load audio %s: no usable decoder", filepath)
        return []

    chunk_samples = sr * chunk_seconds
    chunks: List[np.ndarray] = []
    for start in range(0, len(waveform), chunk_samples):
        chunk = waveform[start : start + chunk_samples]
        if chunk.size > 0:
            chunks.append(chunk)

    return chunks if chunks else [waveform]


class AudioEmbedder:
    """Batch audio embedder backed by CLAP."""

    def __init__(
        self,
        model_id: str = AUDIO_MODEL_ID,
        device: str = "cuda",
        dtype: str = "float16",
        batch_size: int = AUDIO_BATCH_SIZE,
        normalize: bool = True,
    ):
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch.float16 if dtype == "float16" else torch.float32
        self.batch_size = batch_size
        self.normalize = normalize
        self.embed_dim = AUDIO_EMBED_DIM

        self._model = None
        self._processor = None
        self.failures: List[Tuple[str, str]] = []  # (filepath, reason)

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        if self._model is not None:
            return
        # CLAP uses BatchNorm layers that are incompatible with FP16,
        # so we always load in FP32 (the model is small enough at ~300 MB).
        logger.info("Loading audio model: %s (fp32, BatchNorm constraint)", self.model_id)
        load_kwargs: dict = {"local_files_only": True}
        # The main branch only has pytorch_model.bin which requires torch>=2.6
        # due to CVE-2025-32434.  PR#1 provides a safetensors conversion.
        try:
            self._processor = ClapProcessor.from_pretrained(self.model_id, **load_kwargs)
            self._model = ClapModel.from_pretrained(self.model_id, **load_kwargs).to(self.device)
        except (ValueError, OSError):
            logger.info("Falling back to safetensors revision (refs/pr/1)")
            self._processor = ClapProcessor.from_pretrained(
                self.model_id, revision="refs/pr/1", **load_kwargs,
            )
            self._model = ClapModel.from_pretrained(
                self.model_id, revision="refs/pr/1", **load_kwargs,
            ).to(self.device)
        self._model.eval()
        logger.info("Audio model loaded on %s", self.device)

    def unload_model(self) -> None:
        del self._model, self._processor
        self._model = self._processor = None
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Audio model unloaded")

    # ------------------------------------------------------------------
    # Embedding logic
    # ------------------------------------------------------------------

    def _embed_waveforms(self, waveforms: List[np.ndarray]) -> np.ndarray:
        """Embed a flat list of waveform chunks. Returns (N, D) float32."""
        inputs = self._processor(
            audio=waveforms,
            sampling_rate=AUDIO_SAMPLE_RATE,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            out = self._model.get_audio_features(**inputs)
            emb = out.pooler_output if hasattr(out, "pooler_output") else out

        return emb.float().cpu().numpy()

    def _pool_chunks(self, chunk_embeds: np.ndarray) -> np.ndarray:
        """Mean-pool chunk embeddings then L2-normalize."""
        pooled = chunk_embeds.mean(axis=0)
        if self.normalize:
            norm = np.linalg.norm(pooled)
            if norm > 0:
                pooled = pooled / norm
        return pooled

    def embed(self, items: List[MediaItem]) -> Iterator[Tuple[MediaItem, np.ndarray]]:
        """
        Embed a list of audio :class:`MediaItem` objects.

        For files longer than ``AUDIO_CHUNK_SECONDS`` (10 s) the audio is
        split into non-overlapping chunks, each chunk is embedded, and the
        chunk embeddings are mean-pooled then L2-normalised.

        Yields ``(item, embedding)`` pairs.
        Items that fail are recorded in :pyattr:`failures`.
        """
        self.load_model()
        self.failures.clear()

        for item in items:
            chunks = load_and_chunk_audio(item.filepath)
            if not chunks:
                reason = "No audio data (file could not be loaded or is empty)"
                logger.warning("Skipping %s: %s", item.filepath, reason)
                self.failures.append((item.filepath, reason))
                continue

            try:
                all_chunk_embeds: List[np.ndarray] = []
                for i in range(0, len(chunks), self.batch_size):
                    batch = chunks[i : i + self.batch_size]
                    all_chunk_embeds.append(self._embed_waveforms(batch))

                chunk_matrix = np.concatenate(all_chunk_embeds, axis=0)

                if chunk_matrix.shape[0] == 1:
                    emb = chunk_matrix[0]
                    if self.normalize:
                        norm = np.linalg.norm(emb)
                        if norm > 0:
                            emb = emb / norm
                else:
                    emb = self._pool_chunks(chunk_matrix)

                yield item, emb
            except Exception as e:
                reason = f"Model inference failed: {e}"
                logger.error("Audio embedding failed for %s: %s", item.filepath, reason)
                self.failures.append((item.filepath, reason))
