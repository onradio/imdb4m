"""Shared paths and constants for the kg_cleanup package."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Inputs ---------------------------------------------------------------

KG_PATH = PROJECT_ROOT / "data" / "kg" / "imdb_kg_cleaned.ttl"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_MOVIES = PROJECT_ROOT / "data" / "movies"
FAILED_DIR = PROJECT_ROOT / "failed"
ENTITY_CACHE_PATH = OUTPUT_DIR / "entity_cache.json"
PROGRESS_PATH = OUTPUT_DIR / "download_progress.json"
INTEGRITY_AUDIT_PATH = OUTPUT_DIR / "integrity_audit.json"

# --- Outputs --------------------------------------------------------------

CLEANUP_DIR = OUTPUT_DIR / "kg_cleanup"
PRUNED_KG_PATH = PROJECT_ROOT / "data" / "kg" / "imdb_kg_cleaned.pruned.ttl"
SIDE_GRAPH_PATH = PROJECT_ROOT / "data" / "kg" / "imdb_kg_failed_media.ttl"
MANIFEST_PATH = CLEANUP_DIR / "manifest.json"
DISK_SCAN_PATH = CLEANUP_DIR / "disk_scan.json"
REPORT_PATH = CLEANUP_DIR / "report.xlsx"
GRAPH_CACHE_PATH = CLEANUP_DIR / "kg_graph.pickle"

# --- File type registries -------------------------------------------------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv"}
AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".webm", ".ogg", ".wav", ".aac", ".flac", ".wma"}

MIN_VALID_BYTES = 1024  # files smaller than this are treated as absent

# --- Namespaces -----------------------------------------------------------

SCHEMA_NS = "http://schema.org/"
