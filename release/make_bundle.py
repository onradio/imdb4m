"""Assemble the final release bundle.

Copies the IMDB4M code/KG artefacts into
``release_output/imdb4m-release-v1/`` and emits ``MANIFEST.sha256``
listing every file's SHA-256 digest, filesize, and relative path.  Also
generates a top-level ``README.md`` / ``LICENSE`` for the bundle
(populated from templates under :mod:`release`) and an empty
``embeddings_output/`` directory with a placeholder README that points
to the Zenodo deposit hosting the actual vectors.

The embedding parquet/HDF5 tables and the ``embedding_metadata.ttl``
pointer file are **not** included here — they live on Zenodo at
``10.5281/zenodo.20057840`` and are several orders of magnitude too
large for git/GitHub-Releases distribution.

Layout produced::

    imdb4m-release-v1/
    ├── kg/                       cleaned KG TTL + side-graph of removed media triples
    ├── embeddings_output/        empty; user drops Zenodo files here
    │   └── README.md             instructions pointing at Zenodo
    ├── alignment_report.json
    ├── README.md
    ├── LICENSE.md
    └── MANIFEST.sha256

Source files that are missing on disk are skipped with a warning rather
than aborting the run, so a partially-produced bundle is still useful
for inspection (the manifest will only list what was actually copied).
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from . import config as cfg

logger = logging.getLogger(__name__)


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


ZENODO_DOI = "10.5281/zenodo.20057840"
ZENODO_URL = f"https://doi.org/{ZENODO_DOI}"

EMBEDDINGS_OUTPUT_README = f"""# embeddings_output/

This directory is intentionally empty in the IMDB4M release bundle.

The pre-computed embedding tables, the master HDF5 file
(``embeddings.h5``), the RDF pointer file (``embedding_metadata.ttl``),
and the per-variant RotatE training manifests live on Zenodo:

  {ZENODO_URL}
  (DOI: {ZENODO_DOI})

Download every file from that record and place it directly into this
directory. The IMDB4M project code reads from ``embeddings_output/`` by
default (see ``embeddings/config.py``), so no further configuration is
needed once the Zenodo files are in place.

Quick download with ``zenodo_get``::

    pip install zenodo_get
    zenodo_get {ZENODO_DOI} -o embeddings_output/

After the download completes, ``embeddings_output/`` should contain the
parquet files, ``embeddings.h5``, ``embedding_metadata.ttl``, the
``kg_rotate_*_manifest.json`` files, and ``embed_progress.json``.
"""


def _build_plan(bundle_dir: Path) -> List[Tuple[Path, Path]]:
    kg_dir = bundle_dir / "kg"
    doc_dir = bundle_dir

    plan: List[Tuple[Path, Path]] = [
        (cfg.PRUNED_KG, kg_dir / cfg.PRUNED_KG.name),
        (cfg.FAILED_KG, kg_dir / cfg.FAILED_KG.name),
        (cfg.ALIGNMENT_REPORT,    doc_dir / "alignment_report.json"),
        (Path(__file__).parent / "README_bundle.md",  doc_dir / "README.md"),
        (Path(__file__).parent / "LICENSE_bundle.md", doc_dir / "LICENSE.md"),
    ]
    return plan


def _write_embeddings_output_placeholder(bundle_dir: Path) -> Path:
    """Create an empty ``embeddings_output/`` with a Zenodo-pointer README.

    The bundle deliberately ships an empty directory so users have a
    well-known drop-zone for the files they download from Zenodo.
    """
    target = bundle_dir / "embeddings_output"
    target.mkdir(parents=True, exist_ok=True)
    readme = target / "README.md"
    readme.write_text(EMBEDDINGS_OUTPUT_README, encoding="utf-8")
    return readme


def run(
    bundle_dir: Path = cfg.BUNDLE_DIR,
    manifest_path: Path | None = None,
) -> Dict[str, Path]:
    bundle_dir.mkdir(parents=True, exist_ok=True)

    plan = _build_plan(bundle_dir)

    copied: List[Path] = []
    skipped: List[Path] = []
    for src, dst in plan:
        if not src.exists():
            logger.warning("Missing artefact: %s — skipping", src)
            skipped.append(src)
            continue
        _copy(src, dst)
        copied.append(dst)
        logger.info("bundled: %s → %s", src.name, dst.relative_to(bundle_dir))

    placeholder = _write_embeddings_output_placeholder(bundle_dir)
    copied.append(placeholder)
    logger.info(
        "embeddings_output/ placeholder written: %s",
        placeholder.relative_to(bundle_dir),
    )

    manifest_path = manifest_path or (bundle_dir / "MANIFEST.sha256")
    logger.info("Computing SHA-256 manifest → %s", manifest_path)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("# IMDB4M Release Manifest\n")
        f.write("# <sha256>  <bytes>  <path>\n")
        for p in sorted(copied):
            if p == manifest_path:
                continue
            digest = _sha256(p)
            rel = p.relative_to(bundle_dir)
            f.write(f"{digest}  {p.stat().st_size}  {rel}\n")

    logger.info(
        "Bundle ready at %s (copied=%d, skipped=%d)",
        bundle_dir, len(copied), len(skipped),
    )
    return {"bundle": bundle_dir, "manifest": manifest_path}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run()
