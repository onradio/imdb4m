"""KG cleanup package for IMDB4M.

Reconciles the ``data/kg/imdb_kg_cleaned.ttl`` Turtle graph with the actual
media files living in ``output/`` after the manual rescue rounds documented
in ``failed/``.

Outputs:
    data/kg/imdb_kg_cleaned.pruned.ttl        -- main graph minus failed media
    data/kg/imdb_kg_failed_media.ttl          -- side graph with the removed triples
    output/kg_cleanup/manifest.json           -- full decision manifest
    output/kg_cleanup/report.xlsx             -- human-readable audit spreadsheet
"""

__all__ = [
    "config",
    "disk_scan",
    "kg_index",
    "rescue_map",
    "reconcile",
    "apply",
    "sync_sidecars",
    "run",
]
