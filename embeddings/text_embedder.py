"""Text embedder using BGE sentence embeddings."""

from __future__ import annotations

import logging
from typing import Iterator, List, Tuple

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from .config import (
    TEXT_BATCH_SIZE,
    TEXT_CHUNK_STRIDE,
    TEXT_EMBED_DIM,
    TEXT_MAX_TOKENS,
    TEXT_MODEL_ID,
)
from .text_scanner import TextItem

logger = logging.getLogger(__name__)


class TextEmbedder:
    """Batch text embedder backed by ``BAAI/bge-large-en-v1.5``."""

    def __init__(
        self,
        model_id: str = TEXT_MODEL_ID,
        device: str = "cuda",
        dtype: str = "float16",
        batch_size: int = TEXT_BATCH_SIZE,
        max_tokens: int = TEXT_MAX_TOKENS,
        chunk_stride: int = TEXT_CHUNK_STRIDE,
        normalize: bool = True,
        local_files_only: bool = False,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch.float16 if dtype == "float16" else torch.float32
        self.batch_size = batch_size
        self.max_tokens = max_tokens
        self.chunk_stride = chunk_stride
        self.normalize = normalize
        self.embed_dim = TEXT_EMBED_DIM
        self.local_files_only = local_files_only

        self._tokenizer = None
        self._model = None
        self.failures: List[Tuple[str, str]] = []

    def load_model(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading text model: %s (dtype=%s)", self.model_id, self.torch_dtype)
        try:
            self._load_model(local_files_only=True)
        except OSError as local_error:
            if self.local_files_only:
                raise
            logger.warning(
                "Text model %s is not available in the local cache; trying HuggingFace download. "
                "Use --text-local-files-only to require an offline cache. Local error: %s",
                self.model_id,
                local_error,
            )
            self._load_model(local_files_only=False)
        self._model.eval()
        logger.info("Text model loaded on %s", self.device)

    def _load_model(self, local_files_only: bool) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            local_files_only=local_files_only,
        )
        self._model = AutoModel.from_pretrained(
            self.model_id,
            torch_dtype=self.torch_dtype,
            local_files_only=local_files_only,
        ).to(self.device)

    def unload_model(self) -> None:
        del self._model, self._tokenizer
        self._model = self._tokenizer = None
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Text model unloaded")

    def embed(self, items: List[TextItem]) -> Iterator[Tuple[TextItem, np.ndarray]]:
        self.load_model()
        self.failures.clear()

        batch_items: List[TextItem] = []
        batch_texts: List[str] = []
        for item in items:
            if not item.text.strip():
                self.failures.append((item.filepath, "Empty text"))
                continue
            batch_items.append(item)
            batch_texts.append(item.text)
            if len(batch_items) >= self.batch_size:
                yield from self._emit_batch(batch_items, batch_texts)
                batch_items, batch_texts = [], []

        if batch_items:
            yield from self._emit_batch(batch_items, batch_texts)

    def _emit_batch(
        self,
        batch_items: List[TextItem],
        batch_texts: List[str],
    ) -> Iterator[Tuple[TextItem, np.ndarray]]:
        for item, text in zip(batch_items, batch_texts):
            try:
                emb = self._embed_one(text)
                yield item, emb
            except Exception as e:
                reason = f"Text inference failed: {e}"
                logger.error("Skipping %s: %s", item.filepath, reason)
                self.failures.append((item.filepath, reason))

    def _embed_one(self, text: str) -> np.ndarray:
        chunks = self._chunk_text(text)
        embeddings = self._embed_chunks(chunks)
        emb = embeddings.mean(axis=0)
        if self.normalize:
            norm = np.linalg.norm(emb)
            if norm > 0.0:
                emb = emb / norm
        return np.ascontiguousarray(emb, dtype=np.float32)

    def _chunk_text(self, text: str) -> List[str]:
        encoded = self._tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )
        token_ids = encoded["input_ids"]
        special_tokens = self._tokenizer.num_special_tokens_to_add(pair=False)
        payload_window = max(1, self.max_tokens - special_tokens)
        if len(token_ids) <= payload_window:
            return [text]

        step = max(1, payload_window - self.chunk_stride)
        chunks: List[str] = []
        for start in range(0, len(token_ids), step):
            piece_ids = token_ids[start : start + payload_window]
            if not piece_ids:
                continue
            chunks.append(self._tokenizer.decode(piece_ids, skip_special_tokens=True))
            if start + payload_window >= len(token_ids):
                break
        return chunks or [text]

    def _embed_chunks(self, chunks: List[str]) -> np.ndarray:
        outputs: List[np.ndarray] = []
        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_tokens,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad(), torch.autocast(
                device_type="cuda",
                dtype=self.torch_dtype,
                enabled=(self.device == "cuda"),
            ):
                model_out = self._model(**inputs)
                emb = self._mean_pool(model_out.last_hidden_state, inputs["attention_mask"])
                if self.normalize:
                    emb = emb / emb.norm(dim=-1, keepdim=True).clamp_min(1e-12)
            outputs.append(emb.float().cpu().numpy())
        return np.vstack(outputs).astype(np.float32, copy=False)

    @staticmethod
    def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        mask = attention_mask.unsqueeze(-1).type_as(last_hidden_state)
        summed = (last_hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp_min(1e-12)
        return summed / counts
