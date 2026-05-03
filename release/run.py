"""Release orchestrator.

Runs in order:

1. :mod:`release.verify_alignment` — compute the alignment report.
2. :mod:`release.regenerate_metadata` — emit a fresh companion TTL.
3. :mod:`release.enhance_embeddings` — gzip-compress + enrich HDF5.
4. :mod:`release.make_bundle` — copy artefacts and compute SHA-256
   manifest into ``release_output/imdb4m-release-v1/``.

Each stage can be skipped via CLI flags so you can re-run individual
steps without repeating expensive work.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from . import config as cfg
from . import verify_alignment, regenerate_metadata, enhance_embeddings, make_bundle

logger = logging.getLogger("release")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the IMDB4M release bundle.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip the alignment report (requires a pre-existing one).")
    parser.add_argument("--skip-regen", action="store_true", help="Skip regenerating embedding_metadata.ttl.")
    parser.add_argument("--skip-enhance", action="store_true", help="Skip re-writing the HDF5 with gzip compression.")
    parser.add_argument("--skip-bundle", action="store_true", help="Skip the final copy + manifest step.")
    parser.add_argument("--bundle-dir", type=Path, default=cfg.BUNDLE_DIR)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    t0 = time.time()

    if not args.skip_verify:
        logger.info("[1/4] verify_alignment")
        verify_alignment.run(write_report=True)
    else:
        logger.info("[1/4] verify_alignment (skipped)")

    if not args.skip_regen:
        logger.info("[2/4] regenerate_metadata")
        regenerate_metadata.run()
    else:
        logger.info("[2/4] regenerate_metadata (skipped)")

    if not args.skip_enhance:
        logger.info("[3/4] enhance_embeddings")
        enhance_embeddings.run()
    else:
        logger.info("[3/4] enhance_embeddings (skipped)")

    if not args.skip_bundle:
        logger.info("[4/4] make_bundle")
        make_bundle.run(bundle_dir=args.bundle_dir)
    else:
        logger.info("[4/4] make_bundle (skipped)")

    logger.info("Done in %.1fs", time.time() - t0)
    logger.info("Bundle: %s", args.bundle_dir)


if __name__ == "__main__":
    main()
