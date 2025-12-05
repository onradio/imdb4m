#!/usr/bin/env python3
"""
Run SPARQL queries from sparql_queries.txt on all movie TTL files
and calculate what percentage return informative results.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from rdflib import Graph


def parse_sparql_queries(filepath: str) -> dict[str, str]:
    """Parse SPARQL queries from the file, extracting query name and query text."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract PREFIX declarations (at the top of the file)
    prefix_pattern = r'(PREFIX\s+\w+:\s*<[^>]+>\s*)+'
    prefix_match = re.search(prefix_pattern, content)
    prefixes = prefix_match.group(0) if prefix_match else ""
    
    # Pattern to match query comments and the query that follows
    # Matches: # Q1: Question text\nSELECT ... }
    query_pattern = r'#\s*(Q\d+:\s*[^\n]+)\s*\n(SELECT[\s\S]*?}\s*)(?=\n\s*#|\Z)'
    
    queries = {}
    for match in re.finditer(query_pattern, content):
        query_name = match.group(1).strip()
        query_body = match.group(2).strip()
        # Combine prefixes with query body
        full_query = prefixes + "\n" + query_body
        queries[query_name] = full_query
    
    return queries


def find_all_movie_ttl_files(base_dir: str) -> list[Path]:
    """Find all TTL files in movie_html directories."""
    ttl_files = []
    base_path = Path(base_dir)
    
    for movie_dir in base_path.iterdir():
        if movie_dir.is_dir() and movie_dir.name.startswith('tt'):
            movie_html_dir = movie_dir / 'movie_html'
            if movie_html_dir.exists():
                for ttl_file in movie_html_dir.glob('*.ttl'):
                    ttl_files.append(ttl_file)
    
    return sorted(ttl_files)


def main():
    # Paths
    sparql_file = '/home/ioannis/PycharmProjects/imdb4m/QA/sparql_queries.txt'
    movies_dir = '/home/ioannis/PycharmProjects/imdb4m/data/movies'
    
    # Parse queries
    print("Parsing SPARQL queries...")
    queries = parse_sparql_queries(sparql_file)
    print(f"Found {len(queries)} queries:\n")
    for name in sorted(queries.keys(), key=lambda x: int(re.search(r'Q(\d+)', x).group(1))):
        print(f"  - {name}")
    print()
    
    # Find all TTL files
    print("Finding movie TTL files...")
    ttl_files = find_all_movie_ttl_files(movies_dir)
    print(f"Found {len(ttl_files)} TTL files\n")
    
    # Statistics tracking
    query_stats = defaultdict(lambda: {'success': 0, 'empty': 0, 'error': 0})
    
    # Process each TTL file
    print("Running queries on all TTL files...")
    for i, ttl_file in enumerate(ttl_files, 1):
        if i % 50 == 0 or i == len(ttl_files):
            print(f"  Processing file {i}/{len(ttl_files)}: {ttl_file.name}")
        
        # Load graph
        try:
            g = Graph()
            g.parse(ttl_file, format='turtle')
        except Exception as e:
            print(f"  Error loading {ttl_file}: {e}")
            for query_name in queries:
                query_stats[query_name]['error'] += 1
            continue
        
        # Run each query
        for query_name, query_str in queries.items():
            try:
                results = list(g.query(query_str))
                if results:
                    query_stats[query_name]['success'] += 1
                else:
                    query_stats[query_name]['empty'] += 1
            except Exception as e:
                query_stats[query_name]['error'] += 1
    
    # Print results
    print("\n" + "=" * 100)
    print("SPARQL Query Coverage Report")
    print("=" * 100)
    print(f"\nTotal TTL files analyzed: {len(ttl_files)}")
    print("\nResults by Query:\n")
    
    print(f"{'Query':<55} {'Success':>10} {'Empty':>10} {'Error':>10} {'Coverage':>12}")
    print("-" * 97)
    
    overall_success = 0
    overall_total = 0
    
    for query_name in sorted(queries.keys(), key=lambda x: int(re.search(r'Q(\d+)', x).group(1))):
        stats = query_stats[query_name]
        total = stats['success'] + stats['empty'] + stats['error']
        coverage = (stats['success'] / total * 100) if total > 0 else 0
        
        overall_success += stats['success']
        overall_total += total
        
        # Truncate query name if too long
        display_name = query_name[:52] + "..." if len(query_name) > 55 else query_name
        
        print(f"{display_name:<55} {stats['success']:>10} {stats['empty']:>10} {stats['error']:>10} {coverage:>11.1f}%")
    
    print("-" * 97)
    overall_coverage = (overall_success / overall_total * 100) if overall_total > 0 else 0
    print(f"{'OVERALL':<55} {overall_success:>10} {'':<10} {'':<10} {overall_coverage:>11.1f}%")
    
    print("\n" + "=" * 100)
    print("Summary")
    print("=" * 100)
    
    # Create a summary sorted by coverage
    print("\nQueries sorted by coverage (highest to lowest):\n")
    
    coverage_list = []
    for query_name, stats in query_stats.items():
        total = stats['success'] + stats['empty'] + stats['error']
        coverage = (stats['success'] / total * 100) if total > 0 else 0
        coverage_list.append((query_name, coverage, stats['success'], total))
    
    coverage_list.sort(key=lambda x: x[1], reverse=True)
    
    for query_name, coverage, success, total in coverage_list:
        print(f"  {coverage:5.1f}% - {query_name} ({success}/{total})")
    
    print(f"\n\nOverall: {overall_coverage:.1f}% of queries return informative results across all movies")


if __name__ == '__main__':
    main()
