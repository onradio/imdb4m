"""End-to-end orchestrator for the KG cleanup pipeline.

Typical usage::

    # full pipeline, writes pruned KG + side graph + report
    python -m kg_cleanup

    # scan + reconcile, no mutations (safe to run anytime)
    python -m kg_cleanup --dry-run

    # just the disk scan (builds output/kg_cleanup/disk_scan.json)
    python -m kg_cleanup --scan-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .apply import apply_manifest
from .config import (
    CLEANUP_DIR,
    DISK_SCAN_PATH,
    KG_PATH,
    MANIFEST_PATH,
    PRUNED_KG_PATH,
    REPORT_PATH,
    SIDE_GRAPH_PATH,
)
from .disk_scan import load_disk_scan, save_disk_scan, scan_output
from .kg_index import build_index, load_graph
from .reconcile import reconcile
from .report import write_report
from .rescue_map import load_rescue_map
from .sync_sidecars import sync_entity_cache, sync_progress

logger = logging.getLogger(__name__)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the KG with the actual media on disk "
                    "and prune failed entries."
    )
    parser.add_argument("--scan-only", action="store_true",
                        help="only run the disk scan and exit")
    parser.add_argument("--reuse-scan", action="store_true",
                        help="load an existing disk_scan.json instead of re-walking the tree")
    parser.add_argument("--reuse-graph", action="store_true",
                        help="reuse the pickled graph cache if available")
    parser.add_argument("--apply", action="store_true",
                        help="actually mutate files.  Without this flag the pipeline "
                             "runs as a dry-run: only manifest.json and report.xlsx "
                             "are written.")
    parser.add_argument("--skip-sidecars", action="store_true",
                        help="do not update entity_cache.json / download_progress.json")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    args.dry_run = not args.apply

    _setup_logging(args.log_level)
    CLEANUP_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # ---- Step 1. disk scan --------------------------------------------------
    if args.reuse_scan and DISK_SCAN_PATH.exists():
        logger.info("[1/6] reusing disk scan at %s", DISK_SCAN_PATH)
        scan = load_disk_scan()
    else:
        logger.info("[1/6] scanning %s", Path("output").resolve())
        scan = scan_output()
        save_disk_scan(scan)
    logger.info("  → %d entities, %d files", len(scan.entities), scan.total_files)

    if args.scan_only:
        return 0

    # ---- Step 2. load KG + index -------------------------------------------
    logger.info("[2/6] loading KG %s", KG_PATH)
    g = load_graph(use_cache=args.reuse_graph)
    kg = build_index(g)
    logger.info("  → %s", kg.describe())

    # ---- Step 3. rescue map ------------------------------------------------
    logger.info("[3/6] loading rescue scripts")
    rescues = load_rescue_map()
    logger.info("  → %d rescue entries", len(rescues))

    # ---- Step 4. reconcile -------------------------------------------------
    logger.info("[4/6] reconciling")
    manifest = reconcile(scan, kg, rescues)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)
    logger.info("  → manifest saved → %s", MANIFEST_PATH)

    write_report(manifest)

    # ---- Step 5. apply -----------------------------------------------------
    logger.info("[5/6] applying manifest (dry_run=%s)", args.dry_run)
    stats = apply_manifest(kg, manifest, dry_run=args.dry_run)
    logger.info("  → graph stats: %s", stats)

    # ---- Step 6. sidecars --------------------------------------------------
    if not args.skip_sidecars:
        logger.info("[6/6] syncing sidecars")
        cache_stats = sync_entity_cache(manifest, dry_run=args.dry_run)
        prog_stats  = sync_progress(manifest, dry_run=args.dry_run)
        logger.info("  → entity_cache: %s", cache_stats)
        logger.info("  → progress:     %s", prog_stats)
    else:
        logger.info("[6/6] sidecar sync skipped")

    elapsed = time.perf_counter() - t0
    logger.info("Completed in %.1fs", elapsed)

    if args.dry_run:
        logger.info("DRY RUN — no files have been modified on disk except:")
        logger.info("  %s  (manifest)", MANIFEST_PATH)
        logger.info("  %s  (report)",   REPORT_PATH)
    else:
        logger.info("Pruned KG: %s", PRUNED_KG_PATH)
        logger.info("Side graph: %s", SIDE_GRAPH_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
