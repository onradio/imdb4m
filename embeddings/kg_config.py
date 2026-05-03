"""Configuration for RotatE knowledge-graph embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple

SCHEMA_NS = "http://schema.org/"

LABEL_PREDICATES: Dict[str, Tuple[str, ...]] = {
    "genre": (SCHEMA_NS + "genre",),
    "rating": (SCHEMA_NS + "contentRating",),
    "decade": (SCHEMA_NS + "datePublished",),
    "language": (SCHEMA_NS + "inLanguage",),
}

ALL_LABEL_PREDICATES: FrozenSet[str] = frozenset(
    pred for preds in LABEL_PREDICATES.values() for pred in preds
)

VARIANT_TO_MODALITY = {
    "full": "kg",
    "genre": "kg_heldout_genre",
    "rating": "kg_heldout_rating",
    "decade": "kg_heldout_decade",
    "language": "kg_heldout_language",
    "all-labels": "kg_heldout_all_labels",
}

VARIANT_TO_HELDOUT = {
    "full": frozenset(),
    "genre": frozenset(LABEL_PREDICATES["genre"]),
    "rating": frozenset(LABEL_PREDICATES["rating"]),
    "decade": frozenset(LABEL_PREDICATES["decade"]),
    "language": frozenset(LABEL_PREDICATES["language"]),
    "all-labels": ALL_LABEL_PREDICATES,
}

ALL_TRAINING_VARIANTS = ("full", "genre", "rating", "decade", "language", "all-labels")

DEFAULT_KG_PATH = "data/kg/imdb_kg_cleaned.pruned.ttl"
DEFAULT_KG_EMBED_DIM = 256
DEFAULT_KG_EPOCHS = 300
DEFAULT_KG_BATCH_SIZE = 4096
DEFAULT_KG_SEED = 0


@dataclass(frozen=True)
class KGRunConfig:
    """Runtime configuration for a single RotatE variant."""

    variant: str
    modality: str
    heldout_predicates: FrozenSet[str]
    dim: int = DEFAULT_KG_EMBED_DIM
    epochs: int = DEFAULT_KG_EPOCHS
    batch_size: int = DEFAULT_KG_BATCH_SIZE
    seed: int = DEFAULT_KG_SEED
