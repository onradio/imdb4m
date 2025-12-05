#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://www.imdb.com"
RESULT_SELECTOR = "div.dli-parent"
COLUMN_NAMES = ["movie_id", "title", "rating", "number_of_ratings", "movie_link"]


def normalize_href(href: str) -> str:
    """Turn an IMDb title link into an absolute URL without query params."""
    cleaned = href.strip()
    absolute = cleaned if cleaned.startswith("http") else urljoin(BASE_URL, cleaned)
    return absolute.split("?", 1)[0]


def extract_movie_id(url: str) -> str:
    match = re.search(r"/title/(tt\d+)", url)
    return match.group(1) if match else ""


def clean_title(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^\d+\.\s*(.+)$", stripped)
    return match.group(1).strip() if match else stripped


def parse_vote_count(text: str) -> str:
    cleaned = re.sub(r"[()\s]", "", text)
    if not cleaned:
        return ""
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)([KMB]?)", cleaned, flags=re.IGNORECASE)
    if not match:
        digits_only = re.sub(r"[^0-9]", "", cleaned)
        return digits_only
    number, suffix = match.groups()
    multiplier_lookup = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    multiplier = multiplier_lookup.get(suffix.upper(), 1)
    value = int(round(float(number) * multiplier))
    return str(value)


def extract_entry(block) -> Optional[dict]:
    title_link = block.select_one("a.ipc-title-link-wrapper[href]")
    if not title_link:
        return None

    movie_link = normalize_href(title_link["href"])
    movie_id = extract_movie_id(movie_link)
    title = clean_title(title_link.get_text(strip=True))

    rating_value = ""
    vote_count = ""
    rating_group = block.select_one('[data-testid="ratingGroup--imdb-rating"]')
    if rating_group:
        rating_span = rating_group.select_one(".ipc-rating-star--rating")
        if rating_span:
            rating_value = rating_span.get_text(strip=True)
        votes_span = rating_group.select_one(".ipc-rating-star--voteCount")
        if votes_span:
            vote_count = parse_vote_count(votes_span.get_text())

    return {
        "movie_id": movie_id,
        "title": title,
        "rating": rating_value,
        "number_of_ratings": vote_count,
        "movie_link": movie_link,
    }


def process_file(html_path: Path, output_dir: Path) -> tuple[Path, int]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select(RESULT_SELECTOR):
        entry = extract_entry(block)
        if entry:
            rows.append(entry)

    if not rows:
        raise ValueError(f"No movie rows extracted from {html_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{html_path.stem}.csv"
    with output_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=COLUMN_NAMES)
        writer.writeheader()
        writer.writerows(rows)

    return output_path, len(rows)


def iter_html_files(input_dir: Path) -> Iterable[Path]:
    yield from sorted(p for p in input_dir.glob("*.html") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract IMDb movie listings from saved HTML searches into CSV files."
    )
    default_input = Path(__file__).resolve().parent / "movie_seeds"
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_input,
        help=f"Directory containing IMDb HTML search exports (default: {default_input})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write CSV files (defaults to the input directory).",
    )
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir or input_dir

    if not input_dir.exists():
        parser.error(f"Input directory not found: {input_dir}")

    html_files = list(iter_html_files(input_dir))
    if not html_files:
        parser.error(f"No HTML files found in {input_dir}")

    for html_file in html_files:
        output_path, row_count = process_file(html_file, output_dir)
        print(f"Wrote {row_count} rows to {output_path}")


if __name__ == "__main__":
    main()

