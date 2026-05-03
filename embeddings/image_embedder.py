"""
Image embedder using CLIP ViT-L/14.

Loads ``openai/clip-vit-large-patch14`` from HuggingFace, runs the vision
encoder in FP16 on GPU, and returns L2-normalised 768-d embeddings.
"""

import logging
from typing import Iterator, List, Tuple

import numpy as np
import torch
from PIL import Image, ImageFile
from transformers import CLIPModel, CLIPProcessor

from .config import IMAGE_MODEL_ID, IMAGE_EMBED_DIM, IMAGE_BATCH_SIZE
from .scanner import MediaItem

logger = logging.getLogger(__name__)

# Allow loading truncated images (partial downloads) instead of crashing.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Max edge length before we downsample.  CLIP resizes to 224×224 internally,
# so anything much larger just wastes RAM.  Keep some headroom for quality.
_MAX_PIXELS_EDGE = 2048


def _maybe_downsample(img: Image.Image) -> Image.Image:
    """Downsample to fit within ``_MAX_PIXELS_EDGE`` px, keeping aspect ratio."""
    w, h = img.size
    if max(w, h) <= _MAX_PIXELS_EDGE:
        return img
    scale = _MAX_PIXELS_EDGE / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    logger.debug("Downsampling %dx%d -> %dx%d", w, h, new_w, new_h)
    return img.resize((new_w, new_h), Image.LANCZOS)


class ImageEmbedder:
    """Batch image embedder backed by CLIP ViT-L/14."""

    def __init__(
        self,
        model_id: str = IMAGE_MODEL_ID,
        device: str = "cuda",
        dtype: str = "float16",
        batch_size: int = IMAGE_BATCH_SIZE,
        normalize: bool = True,
    ):
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch.float16 if dtype == "float16" else torch.float32
        self.batch_size = batch_size
        self.normalize = normalize
        self.embed_dim = IMAGE_EMBED_DIM

        self._model = None
        self._processor = None
        self.failures: List[Tuple[str, str]] = []  # (filepath, reason)

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading image model: %s (dtype=%s)", self.model_id, self.torch_dtype)
        self._processor = CLIPProcessor.from_pretrained(self.model_id, local_files_only=True)
        self._model = CLIPModel.from_pretrained(
            self.model_id, torch_dtype=self.torch_dtype, local_files_only=True,
        ).to(self.device)
        self._model.eval()
        logger.info("Image model loaded on %s", self.device)

    def unload_model(self) -> None:
        del self._model, self._processor
        self._model = self._processor = None
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Image model unloaded")

    # ------------------------------------------------------------------
    # Embedding logic
    # ------------------------------------------------------------------

    def _embed_batch(self, pil_images: List[Image.Image]) -> np.ndarray:
        """Return (B, D) float32 numpy array."""
        inputs = self._processor(images=pil_images, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)

        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=self.torch_dtype, enabled=(self.device == "cuda")):
            out = self._model.get_image_features(pixel_values=pixel_values)
            emb = out.pooler_output if hasattr(out, "pooler_output") else out

        if self.normalize:
            emb = emb / emb.norm(dim=-1, keepdim=True)

        return emb.float().cpu().numpy()

    def embed(self, items: List[MediaItem]) -> Iterator[Tuple[MediaItem, np.ndarray]]:
        """
        Embed a list of :class:`MediaItem` images in batches.

        Yields ``(item, embedding)`` pairs where *embedding* is a 1-D float32
        numpy array of length :pyattr:`embed_dim`.

        Items that fail to load or embed are recorded in :pyattr:`failures`.
        """
        self.load_model()
        self.failures.clear()

        batch_items: List[MediaItem] = []
        batch_images: List[Image.Image] = []

        for item in items:
            try:
                img = Image.open(item.filepath)
                img.load()  # force full decode so we can close the file handle
                img = img.convert("RGB")
                img = _maybe_downsample(img)
            except Exception as e:
                reason = f"Failed to open image: {e}"
                logger.warning("Skipping %s: %s", item.filepath, reason)
                self.failures.append((item.filepath, reason))
                continue

            batch_items.append(item)
            batch_images.append(img)

            if len(batch_images) >= self.batch_size:
                yield from self._emit_batch(batch_items, batch_images)
                for im in batch_images:
                    im.close()
                batch_items, batch_images = [], []

        if batch_images:
            yield from self._emit_batch(batch_items, batch_images)
            for im in batch_images:
                im.close()

    def _emit_batch(
        self,
        batch_items: List[MediaItem],
        batch_images: List[Image.Image],
    ) -> Iterator[Tuple[MediaItem, np.ndarray]]:
        try:
            embeddings = self._embed_batch(batch_images)
            for bi, emb in zip(batch_items, embeddings):
                yield bi, emb
        except Exception as e:
            reason = f"Model inference failed: {e}"
            logger.error("Batch of %d images failed: %s", len(batch_items), reason)
            for bi in batch_items:
                self.failures.append((bi.filepath, reason))
