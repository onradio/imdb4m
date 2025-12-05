#!/usr/bin/env python3
"""
Utility script that runs parse_imdb_actor.py for a single HTML file, ensures
the generated Turtle file uses the IMDb actor ID (nm#######) as its filename,
and validates the output with rdflib while reporting useful summary statistics.

Supports parallel processing with --workers to speed up batch operations.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

from rdflib import Graph
from rdflib.namespace import RDF
from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parse_imdb_actor import SCHEMA  # type: ignore  # Reuse shared namespace definitions


def extract_nm_id(html_path: Path) -> str:
    """Extract IMDb nm ID from HTML file path or content."""
    # Try to extract from parent directory name (e.g., extractor/movies/actors/nm0000138/actor.html)
    parent = html_path.parent
    if parent.name.startswith("nm") and re.match(r"^nm\d+$", parent.name):
        return parent.name
    
    # Try to extract from HTML content
    try:
        content = html_path.read_text()
        match = re.search(r'/name/(nm\d+)/', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    
    raise ValueError(f"Could not extract IMDb nm ID from {html_path}")


def run_parser(
    parse_script: Path,
    html_path: Path,
    ttl_path: Path,
    max_actor_year: int | None = None,
    show_output: bool = False,
) -> None:
    """Invoke parse_imdb_actor.py via subprocess to generate the TTL file."""
    cmd = [sys.executable, str(parse_script), str(html_path), "-o", str(ttl_path)]
    if max_actor_year is not None:
        cmd.extend(["--max-actor-year", str(max_actor_year)])
    
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
    """Collect useful statistics about the parsed actor graph."""
    stats: Dict[str, Any] = {"triples": len(graph)}
    
    person_uri = next(graph.subjects(RDF.type, SCHEMA.Person), None)
    if person_uri:
        stats["person_uri"] = str(person_uri)
        name = graph.value(person_uri, SCHEMA.name)
        stats["person_name"] = str(name) if name else "Unknown"
        
        stats["performer_in_count"] = len(list(graph.objects(person_uri, SCHEMA.performerIn)))
        stats["award_count"] = len(list(graph.objects(person_uri, SCHEMA.award)))
        stats["image_count"] = len(list(graph.objects(person_uri, SCHEMA.image)))
        stats["video_count"] = len(list(graph.objects(person_uri, SCHEMA.video)))
        
        birth_date = graph.value(person_uri, SCHEMA.birthDate)
        stats["birth_date"] = str(birth_date) if birth_date else None
        
        job_titles = list(graph.objects(person_uri, SCHEMA.jobTitle))
        stats["job_titles"] = [str(jt) for jt in job_titles]
    
    stats["movies"] = len(list(graph.subjects(RDF.type, SCHEMA.Movie)))
    stats["image_objects"] = len(list(graph.subjects(RDF.type, SCHEMA.ImageObject)))
    stats["video_objects"] = len(list(graph.subjects(RDF.type, SCHEMA.VideoObject)))
    
    return stats


def process_actor_html(
    html_path: Path,
    parse_script: Path,
    output_dir: Path | None,
    max_actor_year: int | None,
    show_parser_output: bool,
    quiet: bool = False,
) -> Tuple[Path, Dict[str, Any]]:
    """Run parser + validation for a single actor HTML file and return stats."""
    html_path = html_path.resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    
    # Extract nm ID and determine output filename
    nm_id = extract_nm_id(html_path)
    target_dir = output_dir.resolve() if output_dir else html_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    ttl_path = target_dir / f"{nm_id}.ttl"
    
    if not quiet:
        print(f"\nRunning parser on {html_path} -> {ttl_path}")
    run_parser(parse_script, html_path, ttl_path, max_actor_year, show_output=show_parser_output)
    
    graph = load_graph(ttl_path)
    stats = gather_stats(graph)
    return ttl_path, stats


def _worker_process_actor(
    args_tuple: Tuple[Path, Path, Optional[Path], Optional[int], bool]
) -> Tuple[Path, Optional[Path], Optional[Dict[str, Any]], Optional[str]]:
    """
    Worker function for parallel processing.
    Returns (html_path, ttl_path, stats, error_message).
    If successful, error_message is None. If failed, stats is None.
    """
    html_path, parse_script, output_dir, max_actor_year, show_parser_output = args_tuple
    try:
        ttl_path, stats = process_actor_html(
            html_path, parse_script, output_dir, max_actor_year, show_parser_output, quiet=True
        )
        return (html_path, ttl_path, stats, None)
    except Exception as exc:
        return (html_path, None, None, str(exc))


def discover_actor_html_files(actors_root: Path) -> List[Path]:
    """Find all HTML files that match nm*/actor.html."""
    actors_root = actors_root.resolve()
    pattern = "nm*/actor.html"
    if actors_root.name.startswith("nm") and (actors_root / "actor.html").exists():
        html_files = [actors_root / "actor.html"]
    else:
        html_files = list(actors_root.rglob(pattern))
    return sorted(html_files)


def write_stats_excel(results: List[Tuple[Path, Dict[str, Any]]], destination: Path) -> None:
    """Persist per-actor statistics to an Excel workbook."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Actor Stats"
    headers = [
        "ttl_file",
        "actor_id",
        "actor_name",
        "person_uri",
        "triples",
        "movies",
        "performer_in_count",
        "award_count",
        "image_count",
        "image_objects",
        "video_count",
        "video_objects",
        "birth_date",
        "job_titles",
    ]
    ws.append(headers)

    for ttl_path, stats in results:
        actor_id = ttl_path.stem
        job_titles_str = ", ".join(stats.get("job_titles", []))
        row = [
            str(ttl_path),
            actor_id,
            stats.get("person_name", ""),
            stats.get("person_uri", ""),
            stats.get("triples", 0),
            stats.get("movies", 0),
            stats.get("performer_in_count", 0),
            stats.get("award_count", 0),
            stats.get("image_count", 0),
            stats.get("image_objects", 0),
            stats.get("video_count", 0),
            stats.get("video_objects", 0),
            stats.get("birth_date", ""),
            job_titles_str,
        ]
        ws.append(row)

    wb.save(destination)
    print(f"Wrote stats for {len(results)} actors to {destination}")


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
            "Run parse_imdb_actor.py for IMDb actor HTML files, emit TTL files named "
            "after each IMDb actor ID (nm#######), and validate the result with rdflib."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--actor-html",
        type=Path,
        help="Process a single IMDb actor HTML file (e.g., /path/to/actor.html).",
    )
    group.add_argument(
        "--all-actors",
        action="store_true",
        help="Process every actor HTML file found under --actors-root.",
    )
    parser.add_argument(
        "--parse-script",
        type=Path,
        default=PROJECT_ROOT / "parse_imdb_actor.py",
        help="Optional path to parse_imdb_actor.py (defaults to project root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for the TTL file (defaults to the HTML file directory).",
    )
    parser.add_argument(
        "--actors-root",
        type=Path,
        default=PROJECT_ROOT / "extractor" / "movies" / "actors",
        help="Root directory that holds actor folders (used with --all-actors).",
    )
    parser.add_argument(
        "--stats-xlsx",
        type=Path,
        default=PROJECT_ROOT / "actor_stats.xlsx",
        help="Path to the Excel file that will store per-actor statistics.",
    )
    parser.add_argument(
        "--error-log",
        type=Path,
        default=PROJECT_ROOT / "actor_errors.txt",
        help="Path to the text file that will capture failures.",
    )
    parser.add_argument(
        "--max-actor-year",
        type=int,
        default=None,
        help="Highest release year to keep in actor filmography (passed to parse_imdb_actor.py).",
    )
    parser.add_argument(
        "--show-parser-output",
        action="store_true",
        help="Print stdout from parse_imdb_actor.py for each run.",
    )
    parser.add_argument(
        "-j", "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for batch processing (default: 1, use 0 for CPU count).",
    )

    args = parser.parse_args()

    parse_script = args.parse_script.resolve()
    if not parse_script.exists():
        parser.error(f"parse_imdb_actor.py not found at {parse_script}")

    if args.all_actors:
        html_files = discover_actor_html_files(args.actors_root)
        if not html_files:
            parser.error(f"No actor HTML files found under {args.actors_root}")

        successes: List[Tuple[Path, Dict[str, Any]]] = []
        failures: List[Tuple[Path, Exception]] = []
        
        # Determine number of workers
        num_workers = args.workers
        if num_workers == 0:
            num_workers = multiprocessing.cpu_count()
        
        if num_workers > 1:
            # Parallel processing
            print(f"Processing {len(html_files)} actors with {num_workers} parallel workers...")
            
            # Prepare work items
            work_items = [
                (html_file, parse_script, args.output_dir, args.max_actor_year, args.show_parser_output)
                for html_file in html_files
            ]
            
            completed = 0
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = {
                    executor.submit(_worker_process_actor, item): item[0]
                    for item in work_items
                }
                
                for future in as_completed(futures):
                    html_path, ttl_path, stats, error_msg = future.result()
                    completed += 1
                    
                    if error_msg is None:
                        successes.append((ttl_path, stats))
                        if completed % 100 == 0 or completed == len(html_files):
                            print(f"  Progress: {completed}/{len(html_files)} ({100*completed//len(html_files)}%)")
                    else:
                        failures.append((html_path, Exception(error_msg)))
                        print(f"Failed on {html_path}: {error_msg}", file=sys.stderr)
        else:
            # Sequential processing (original behavior)
            for html_file in html_files:
                try:
                    result = process_actor_html(
                        html_file, parse_script, args.output_dir, args.max_actor_year, args.show_parser_output
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
    if not args.actor_html:
        parser.error("--actor-html is required when --all-actors is not used")

    try:
        ttl_path, stats = process_actor_html(
            args.actor_html,
            parse_script,
            args.output_dir,
            args.max_actor_year,
            args.show_parser_output,
        )
        
        print("\n" + "=" * 60)
        print("TTL FILE VALIDATION & STATISTICS")
        print("=" * 60)
        print(f"✓ TTL file is valid and can be imported by rdflib")
        print(f"\nOutput file: {ttl_path}")
        print(f"Triples: {stats['triples']}")
        print(f"Person: {stats.get('person_name', 'Unknown')}")
        print(f"Person URI: {stats.get('person_uri', 'N/A')}")
        if stats.get('birth_date'):
            print(f"Birth date: {stats['birth_date']}")
        if stats.get('job_titles'):
            print(f"Job titles: {', '.join(stats['job_titles'])}")
        print(f"Movies: {stats['movies']}")
        print(f"Performer in: {stats.get('performer_in_count', 0)} movies")
        print(f"Awards: {stats.get('award_count', 0)}")
        print(f"Images: {stats.get('image_count', 0)}")
        print(f"Image objects: {stats.get('image_objects', 0)}")
        print(f"Videos: {stats.get('video_count', 0)}")
        print(f"Video objects: {stats.get('video_objects', 0)}")
        
        # Write stats to Excel for single file too
        write_stats_excel([(ttl_path, stats)], args.stats_xlsx)
        
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        write_error_log([(args.actor_html, exc)], args.error_log)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

