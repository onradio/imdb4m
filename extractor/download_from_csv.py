#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Iterable, Set

try:
    from extractor.download_imdb_movie import (
        download_imdb_movie,
        download_imdb_soundtrack,
        extract_movie_id,
    )
except ModuleNotFoundError:  # pragma: no cover
    # Allow running as `python extractor/download_from_csv.py`
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parent.parent))
    from extractor.download_imdb_movie import (
        download_imdb_movie,
        download_imdb_soundtrack,
        extract_movie_id,
    )

CSV_COLUMNS = {"movie_link", "movie_id"}


def find_csv_files(directory: Path) -> Iterable[Path]:
    yield from sorted(p for p in directory.glob("*.csv") if p.is_file())


def read_movie_urls(csv_path: Path) -> Iterable[tuple[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_cols = CSV_COLUMNS - set(reader.fieldnames or [])
        if missing_cols:
            raise ValueError(f"{csv_path} missing columns: {', '.join(sorted(missing_cols))}")
        for row in reader:
            url = (row.get("movie_link") or "").strip()
            movie_id = (row.get("movie_id") or "").strip()
            if not url or not movie_id:
                continue
            yield movie_id, url


def load_existing_movie_ids(output_dir: Path) -> Set[str]:
    existing = set()
    if not output_dir.exists():
        return existing
    for movie_dir in output_dir.iterdir():
        if not movie_dir.is_dir():
            continue
        movie_id = movie_dir.name
        movie_file = movie_dir / "movie_html" / f"{movie_id}.html"
        soundtrack_file = movie_dir / "movie_soundtrack" / f"{movie_id}_sound.html"
        if movie_file.exists() or soundtrack_file.exists():
            existing.add(movie_id)
    return existing


def process_csv(csv_path: Path, output_dir: Path, seen_ids: Set[str], delay: float) -> None:
    print(f"\nProcessing CSV: {csv_path}")
    for movie_id, url in read_movie_urls(csv_path):
        if movie_id in seen_ids:
            print(f"Skipping {movie_id}; already downloaded.")
            continue
        try:
            inferred_id = extract_movie_id(url)
        except ValueError:
            inferred_id = movie_id

        print(f"\n==> Fetching {inferred_id} from {url}")
        try:
            download_imdb_movie(url, output_dir=output_dir)
            download_imdb_soundtrack(url, output_dir=output_dir)
            seen_ids.add(movie_id)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to download {movie_id}: {exc}")
        if delay > 0:
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download IMDb movie and soundtrack HTML pages from CSV exports."
    )
    default_input = Path(__file__).resolve().parent / "movie_seeds"
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=default_input,
        help=f"Directory containing CSV files (default: {default_input})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "movies",
        help="Directory where movie HTML should be stored.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between movie downloads (default: 1.0).",
    )
    args = parser.parse_args()

    csv_dir: Path = args.csv_dir
    output_dir: Path = args.output_dir
    delay: float = args.delay

    if not csv_dir.exists():
        parser.error(f"CSV directory not found: {csv_dir}")

    csv_files = list(find_csv_files(csv_dir))
    if not csv_files:
        parser.error(f"No CSV files found in {csv_dir}")

    seen_ids: Set[str] = load_existing_movie_ids(output_dir)
    if seen_ids:
        print(f"Found {len(seen_ids)} movies already downloaded. They will be skipped.")
    for csv_file in csv_files:
        process_csv(csv_file, output_dir=output_dir, seen_ids=seen_ids, delay=delay)

    print("\nDownloads complete.")


if __name__ == "__main__":
    main()

