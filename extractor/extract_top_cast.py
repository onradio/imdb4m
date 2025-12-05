#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import List, Dict, Iterable

from bs4 import BeautifulSoup


def find_movie_html_files(movies_dir: Path) -> Iterable[tuple[str, Path]]:
    for movie_dir in sorted(p for p in movies_dir.iterdir() if p.is_dir()):
        movie_id = movie_dir.name
        html_dir = movie_dir / "movie_html"
        if not html_dir.exists():
            continue
        html_files = list(html_dir.glob("*.html"))
        if not html_files:
            continue
        # Prefer file named after movie_id if present
        target = html_dir / f"{movie_id}.html"
        if target.exists():
            yield movie_id, target
        else:
            yield movie_id, html_files[0]


def extract_top_cast(html_path: Path) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    script = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if not script or not script.string:
        return []
    data = json.loads(script.string)
    main_data = data.get("props", {}).get("pageProps", {}).get("mainColumnData", {})
    cast_groups = main_data.get("castV2") or []
    rows: List[Dict[str, str]] = []
    for group in cast_groups:
        grouping = group.get("grouping") or {}
        if grouping.get("text", "").lower() != "top cast":
            continue
        for credit in group.get("credits", []):
            name = credit.get("name") or {}
            actor_id = name.get("id")
            if not actor_id or not actor_id.startswith("nm"):
                continue
            actor_name = (name.get("nameText") or {}).get("text", "")
            actor_url = f"https://www.imdb.com/name/{actor_id}/"
            rows.append(
                {
                    "actor_id": actor_id,
                    "actor_name": actor_name,
                    "actor_url": actor_url,
                }
            )
    return rows


def write_output(rows: List[Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=["movie_id", "actor_id", "actor_name", "actor_url"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Top Cast actor URLs from downloaded IMDb movie HTML files."
    )
    default_movies_dir = Path(__file__).resolve().parent / "movies"
    parser.add_argument(
        "--movies-dir",
        type=Path,
        default=default_movies_dir,
        help=f"Directory containing movie subdirectories (default: {default_movies_dir})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "top_cast.csv",
        help="CSV file to write results to.",
    )
    args = parser.parse_args()

    movies_dir: Path = args.movies_dir
    if not movies_dir.exists():
        parser.error(f"Movies directory not found: {movies_dir}")

    collected: List[Dict[str, str]] = []
    missing = []
    for movie_id, html_path in find_movie_html_files(movies_dir):
        cast = extract_top_cast(html_path)
        if not cast:
            missing.append(movie_id)
            continue
        for entry in cast:
            collected.append({"movie_id": movie_id, **entry})

    if not collected:
        parser.error("No cast entries extracted.")

    write_output(collected, args.output)
    print(f"Wrote {len(collected)} rows to {args.output}")
    if missing:
        print(f"Movies without Top Cast data: {len(missing)} (e.g., {', '.join(missing[:5])})")


if __name__ == "__main__":
    main()

