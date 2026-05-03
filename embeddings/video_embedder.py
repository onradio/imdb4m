"""
Video embedder using X-CLIP (Microsoft).

Loads ``microsoft/xclip-base-patch32`` from HuggingFace, uniformly samples
frames from each video, runs the video encoder in FP16, and returns
L2-normalised 512-d embeddings.
"""

import logging
from typing import Iterator, List, Tuple

import cv2
import numpy as np
import torch
from transformers import XCLIPModel, XCLIPProcessor

from .config import VIDEO_MODEL_ID, VIDEO_EMBED_DIM, VIDEO_BATCH_SIZE, VIDEO_NUM_FRAMES
from .scanner import MediaItem

logger = logging.getLogger(__name__)


def sample_frames(video_path: str, num_frames: int = VIDEO_NUM_FRAMES) -> List[np.ndarray]:
    """
    Uniformly sample *num_frames* RGB frames from a video file.

    Returns a list of HWC uint8 numpy arrays, or an empty list on failure.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Cannot open video: %s", video_path)
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []

    indices = np.linspace(0, total - 1, num_frames, dtype=int)
    frames: List[np.ndarray] = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            # duplicate previous frame as fallback
            if frames:
                frames.append(frames[-1].copy())

    cap.release()

    # pad to exactly num_frames if video was very short
    while len(frames) < num_frames and frames:
        frames.append(frames[-1].copy())

    return frames[:num_frames]


class VideoEmbedder:
    """Batch video embedder backed by X-CLIP."""

    def __init__(
        self,
        model_id: str = VIDEO_MODEL_ID,
        device: str = "cuda",
        dtype: str = "float16",
        batch_size: int = VIDEO_BATCH_SIZE,
        num_frames: int = VIDEO_NUM_FRAMES,
        normalize: bool = True,
    ):
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch.float16 if dtype == "float16" else torch.float32
        self.batch_size = batch_size
        self.num_frames = num_frames
        self.normalize = normalize
        self.embed_dim = VIDEO_EMBED_DIM

        self._model = None
        self._processor = None
        self.failures: List[Tuple[str, str]] = []  # (filepath, reason)

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading video model: %s (dtype=%s)", self.model_id, self.torch_dtype)
        self._processor = XCLIPProcessor.from_pretrained(self.model_id, local_files_only=True)
        self._model = XCLIPModel.from_pretrained(
            self.model_id, torch_dtype=self.torch_dtype, local_files_only=True,
        ).to(self.device)
        self._model.eval()
        logger.info("Video model loaded on %s", self.device)

    def unload_model(self) -> None:
        del self._model, self._processor
        self._model = self._processor = None
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Video model unloaded")

    # ------------------------------------------------------------------
    # Embedding logic
    # ------------------------------------------------------------------

    def _embed_batch(self, videos: List[List[np.ndarray]]) -> np.ndarray:
        """
        Embed a batch of videos.

        Args:
            videos: list of ``[num_frames x HWC-uint8]`` frame lists.

        Returns:
            ``(B, 512)`` float32 numpy array.
        """
        inputs = self._processor(images=videos, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)

        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=self.torch_dtype, enabled=(self.device == "cuda")):
            out = self._model.get_video_features(pixel_values=pixel_values)
            emb = out.pooler_output if hasattr(out, "pooler_output") else out

        if self.normalize:
            emb = emb / emb.norm(dim=-1, keepdim=True)

        return emb.float().cpu().numpy()

    def embed(self, items: List[MediaItem]) -> Iterator[Tuple[MediaItem, np.ndarray]]:
        """
        Embed a list of video :class:`MediaItem` objects in batches.

        Yields ``(item, embedding)`` pairs.
        Items that fail are recorded in :pyattr:`failures`.
        """
        self.load_model()
        self.failures.clear()

        batch_items: List[MediaItem] = []
        batch_videos: List[List[np.ndarray]] = []

        for item in items:
            frames = sample_frames(item.filepath, self.num_frames)
            if not frames:
                reason = "Could not extract frames from video"
                logger.warning("Skipping %s: %s", item.filepath, reason)
                self.failures.append((item.filepath, reason))
                continue

            batch_items.append(item)
            batch_videos.append(frames)

            if len(batch_videos) >= self.batch_size:
                yield from self._emit_batch(batch_items, batch_videos)
                batch_items, batch_videos = [], []

        if batch_videos:
            yield from self._emit_batch(batch_items, batch_videos)

    def _emit_batch(
        self,
        batch_items: List[MediaItem],
        batch_videos: List[List[np.ndarray]],
    ) -> Iterator[Tuple[MediaItem, np.ndarray]]:
        try:
            embeddings = self._embed_batch(batch_videos)
            for bi, emb in zip(batch_items, embeddings):
                yield bi, emb
        except Exception as e:
            reason = f"Model inference failed: {e}"
            logger.error("Batch of %d videos failed: %s", len(batch_items), reason)
            for bi in batch_items:
                self.failures.append((bi.filepath, reason))
