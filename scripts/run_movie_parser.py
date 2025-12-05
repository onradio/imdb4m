#!/usr/bin/env python3
"""
Utility script that runs parse_imdb_movie.py for a single HTML file, ensures
the generated Turtle file uses the IMDb ID as its filename, and validates the
output with rdflib while reporting useful summary statistics.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

from rdflib import Graph
from rdflib.namespace import RDF
from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parse_imdb_movie import SCHEMA  # type: ignore  # Reuse shared namespace definitions


def run_parser(
    parse_script: Path,
    html_path: Path,
    ttl_path: Path,
    show_output: bool = False,
) -> None:
    """Invoke parse_imdb_movie.py via subprocess to generate the TTL file."""
    cmd = [sys.executable, str(parse_script), str(html_path), "-o", str(ttl_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Parser failed with exit code {result.returncode}:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    if show_output and result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)


def load_graph(ttl_path: Path) -> Graph:
    """Load the generated TTL file into rdflib to verify syntax."""
    graph = Graph()
    graph.parse(ttl_path, format="turtle")
    return graph


def gather_stats(graph: Graph) -> Dict[str, Any]:
    """Collect a handful of useful statistics about the parsed movie graph."""
    stats: Dict[str, Any] = {"triples": len(graph)}
    movie_uri = next(graph.subjects(RDF.type, SCHEMA.Movie), None)
    if movie_uri:
        stats["movie_uri"] = str(movie_uri)
        name = graph.value(movie_uri, SCHEMA.name)
        stats["movie_name"] = str(name) if name else "Unknown"
        stats["actor_count"] = len(list(graph.objects(movie_uri, SCHEMA.actor)))
        stats["director_count"] = len(list(graph.objects(movie_uri, SCHEMA.director)))
        stats["genre_count"] = len(list(graph.objects(movie_uri, SCHEMA.genre)))
        stats["language_count"] = len(list(graph.objects(movie_uri, SCHEMA.inLanguage)))
        stats["review_count"] = len(list(graph.objects(movie_uri, SCHEMA.review)))
        stats["image_count"] = len(list(graph.objects(movie_uri, SCHEMA.image)))
    return stats


def process_html_file(
    html_path: Path,
    parse_script: Path,
    output_dir: Path | None,
    show_parser_output: bool,
) -> Tuple[Path, Dict[str, Any]]:
    """Run parser + validation for a single HTML file and return stats."""
    html_path = html_path.resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    target_dir = output_dir.resolve() if output_dir else html_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = target_dir / f"{html_path.stem}.ttl"

    print(f"\nRunning parser on {html_path} -> {ttl_path}")
    run_parser(parse_script, html_path, ttl_path, show_output=show_parser_output)

    graph = load_graph(ttl_path)
    stats = gather_stats(graph)
    return ttl_path, stats


def discover_movie_html_files(movies_root: Path) -> List[Path]:
    """Find all HTML files that match /tt#######/movie_html/tt#######.html."""
    movies_root = movies_root.resolve()
    pattern = "tt*/movie_html/tt*.html"
    if movies_root.name.startswith("tt") and (movies_root / "movie_html").exists():
        html_files = list((movies_root / "movie_html").glob("tt*.html"))
    else:
        html_files = list(movies_root.rglob(pattern))
    return sorted(html_files)


def write_stats_excel(results: List[Tuple[Path, Dict[str, Any]]], destination: Path) -> None:
    """Persist per-movie statistics to an Excel workbook."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Movie Stats"
    headers = [
        "ttl_file",
        "movie_id",
        "movie_name",
        "movie_uri",
        "triples",
        "actor_count",
        "director_count",
        "genre_count",
        "language_count",
        "review_count",
        "image_count",
    ]
    ws.append(headers)

    for ttl_path, stats in results:
        movie_id = ttl_path.stem
        row = [
            str(ttl_path),
            movie_id,
            stats.get("movie_name", ""),
            stats.get("movie_uri", ""),
            stats.get("triples", 0),
            stats.get("actor_count", 0),
            stats.get("director_count", 0),
            stats.get("genre_count", 0),
            stats.get("language_count", 0),
            stats.get("review_count", 0),
            stats.get("image_count", 0),
        ]
        ws.append(row)

    wb.save(destination)
    print(f"Wrote stats for {len(results)} movies to {destination}")


def write_error_log(failures: List[Tuple[Path, Exception]], destination: Path) -> None:
    """Write failure details to a plain-text log."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as fh:
        for html_file, exc in failures:
            fh.write(f"{html_file}: {exc}\n")
    print(f"Logged {len(failures)} failures to {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run parse_imdb_movie.py for IMDb HTML files, emit TTL files named "
            "after each IMDb title ID, and validate the result with rdflib."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--html-file",
        type=Path,
        help="Process a single IMDb HTML file (e.g. /path/to/tt1234567.html).",
    )
    group.add_argument(
        "--all-movies",
        action="store_true",
        help="Process every movie HTML file found under --movies-root.",
    )
    parser.add_argument(
        "--parse-script",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "parse_imdb_movie.py",
        help="Optional path to parse_imdb_movie.py (defaults to project root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for the TTL file (defaults to the HTML file directory).",
    )
    parser.add_argument(
        "--movies-root",
        type=Path,
        default=PROJECT_ROOT / "extractor" / "movies",
        help="Root directory that holds movie folders (used with --all-movies).",
    )
    parser.add_argument(
        "--stats-xlsx",
        type=Path,
        default=PROJECT_ROOT / "movie_stats.xlsx",
        help="Path to the Excel file that will store per-movie statistics.",
    )
    parser.add_argument(
        "--error-log",
        type=Path,
        default=PROJECT_ROOT / "error.txt",
        help="Path to the text file that will capture failures.",
    )
    parser.add_argument(
        "--show-parser-output",
        action="store_true",
        help="Print stdout from parse_imdb_movie.py for each run.",
    )

    args = parser.parse_args()

    parse_script = args.parse_script.resolve()
    if not parse_script.exists():
        parser.error(f"parse_imdb_movie.py not found at {parse_script}")

    if args.all_movies:
        html_files = discover_movie_html_files(args.movies_root)
        if not html_files:
            parser.error(f"No movie HTML files found under {args.movies_root}")

        successes: List[Tuple[Path, Dict[str, Any]]] = []
        failures: List[Tuple[Path, Exception]] = []
        for html_file in html_files:
            try:
                result = process_html_file(
                    html_file, parse_script, args.output_dir, args.show_parser_output
                )
                successes.append(result)
            except Exception as exc:
                failures.append((html_file, exc))
                print(f"Failed on {html_file}: {exc}", file=sys.stderr)

        print(f"\nBatch complete: {len(successes)} succeeded, {len(failures)} failed.")
        if successes:
            write_stats_excel(successes, args.stats_xlsx)
            total_triples = sum(stats.get("triples", 0) for _, stats in successes)
            print(f"Total triples across successes: {total_triples}")
            largest = max(successes, key=lambda item: item[1].get("triples", 0))
            print(
                f"Largest graph: {largest[0].name} with {largest[1].get('triples', 0)} triples"
            )

        if failures:
            write_error_log(failures, args.error_log)

        return 1 if failures else 0

    # Single file mode
    if not args.html_file:
        parser.error("--html-file is required when --all-movies is not used")

    success = [
        process_html_file(
            args.html_file, parse_script, args.output_dir, args.show_parser_output
        )
    ]
    write_stats_excel(success, args.stats_xlsx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

