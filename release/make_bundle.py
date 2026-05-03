"""Assemble the final release bundle.

Copies every artefact into ``release_output/imdb4m-release-v1/`` and
emits ``MANIFEST.sha256`` listing every file's SHA-256 digest, filesize,
and relative path.  Also generates a top-level ``README.md`` / ``LICENSE``
for the bundle (populated from templates under :mod:`release`).
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Dict, List

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


def run(
    bundle_dir: Path = cfg.BUNDLE_DIR,
    manifest_path: Path | None = None,
) -> Dict[str, Path]:
    bundle_dir.mkdir(parents=True, exist_ok=True)

    kg_dir = bundle_dir / "kg"
    emb_dir = bundle_dir / "embeddings"
    doc_dir = bundle_dir

    plan: List[tuple] = [
        # (source, destination_within_bundle)
        (cfg.PRUNED_KG,            kg_dir / cfg.PRUNED_KG.name),
        (cfg.FAILED_KG,            kg_dir / cfg.FAILED_KG.name),
        (cfg.IMAGE_PARQUET,        emb_dir / cfg.IMAGE_PARQUET.name),
        (cfg.VIDEO_PARQUET,        emb_dir / cfg.VIDEO_PARQUET.name),
        (cfg.AUDIO_PARQUET,        emb_dir / cfg.AUDIO_PARQUET.name),
        (cfg.TEXT_PARQUET,         emb_dir / cfg.TEXT_PARQUET.name),
        (cfg.ENHANCED_H5,          emb_dir / "embeddings.h5"),
        (cfg.REGENERATED_TTL,      emb_dir / "embedding_metadata.ttl"),
        (cfg.EMBEDDINGS_CARD,      emb_dir / "embeddings_card.json"),
        (cfg.ALIGNMENT_REPORT,     doc_dir / "alignment_report.json"),
        (Path(__file__).parent / "README_bundle.md",  doc_dir / "README.md"),
        (Path(__file__).parent / "LICENSE_bundle.md", doc_dir / "LICENSE.md"),
    ]

    copied: List[Path] = []
    for src, dst in plan:
        if not src.exists():
            logger.warning("Missing artefact: %s — skipping", src)
            continue
        _copy(src, dst)
        copied.append(dst)
        logger.info("bundled: %s → %s", src.name, dst.relative_to(bundle_dir))

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

    logger.info("Bundle ready at %s", bundle_dir)
    return {"bundle": bundle_dir, "manifest": manifest_path}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run()
