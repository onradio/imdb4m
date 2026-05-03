"""Release-building pipeline for the IMDB4M KG + embeddings bundle.

Steps (each a module):

1. :mod:`release.verify_alignment` — confirm every embedding row still
   maps to a node in ``imdb_kg_cleaned.pruned.ttl`` and vice versa.
2. :mod:`release.regenerate_metadata` — emit a fresh
   ``embedding_metadata.ttl`` that references only entities kept in the
   pruned KG, with row-accurate parquet/HDF5 pointers.
3. :mod:`release.enhance_embeddings` — copy the HDF5 to a gzip-compressed
   version with ``normalized`` / ``model_revision`` attributes.  Emit a
   companion ``embeddings_card.json`` documenting the vectors.
4. :mod:`release.make_bundle` — assemble ``imdb4m-release-<tag>/``, copy
   every artefact, compute SHA-256 manifest, and drop in the README /
   LICENSE.

``python -m release`` runs the whole thing.
"""

__all__ = [
    "config",
    "verify_alignment",
    "regenerate_metadata",
    "enhance_embeddings",
    "make_bundle",
    "run",
]
