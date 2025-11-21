#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Iterable, Set

try:
    from scraper.download_imdb_actor import download_imdb_actor, extract_actor_id
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from scraper.download_imdb_actor import download_imdb_actor, extract_actor_id


def read_actor_urls(csv_path: Path) -> Iterable[str]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "actor_url" not in (reader.fieldnames or []):
            raise ValueError(f"{csv_path} missing 'actor_url' column")
        for row in reader:
            url = (row.get("actor_url") or "").strip()
            if url:
                yield url


def load_existing_actor_ids(output_dir: Path) -> Set[str]:
    existing: Set[str] = set()
    actors_dir = output_dir / "actors"
    if not actors_dir.exists():
        return existing
    for actor_dir in actors_dir.iterdir():
        if not actor_dir.is_dir():
            continue
        actor_html = actor_dir / "actor.html"
        if actor_html.exists():
            existing.add(actor_dir.name)
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download IMDb actor pages from actor CSV data."
    )
    default_csv = Path(__file__).resolve().parent / "top_cast_sample.csv"
    default_movies = Path(__file__).resolve().parent / "movies"
    parser.add_argument(
        "--actors-csv",
        type=Path,
        default=default_csv,
        help=f"CSV containing actor_url column (default: {default_csv})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_movies,
        help=f"Directory to store actor downloads (default: {default_movies})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Delay in seconds between downloads.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (passed to downloader).",
    )
    args = parser.parse_args()

    csv_path: Path = args.actors_csv
    output_dir: Path = args.output_dir
    delay: float = args.delay
    headless: bool = args.headless

    if not csv_path.exists():
        parser.error(f"CSV file not found: {csv_path}")

    existing = load_existing_actor_ids(output_dir)
    print(f"Found {len(existing)} actors already downloaded; they will be skipped.")

    seen_ids: Set[str] = set(existing)
    total_attempted = 0
    total_downloaded = 0

    for url in read_actor_urls(csv_path):
        try:
            actor_id = extract_actor_id(url)
        except ValueError as exc:
            print(f"Skipping invalid URL {url}: {exc}")
            continue

        if actor_id in seen_ids:
            continue

        total_attempted += 1
        try:
            download_imdb_actor(url, output_dir=output_dir, headless=headless)
            seen_ids.add(actor_id)
            total_downloaded += 1
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to download {actor_id}: {exc}")
        if delay > 0:
            time.sleep(delay)

    print(
        f"Attempted {total_attempted} downloads, successfully downloaded {total_downloaded} actors."
    )


if __name__ == "__main__":
    main()

