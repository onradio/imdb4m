#!/usr/bin/env python3
"""
Script to create owl:sameAs mappings between IMDB URIs and Wikidata URIs.

Reads actor_stats.xlsx and movie_stats.xlsx and generates a Turtle file
containing triples of the form:
    <MovieURI> owl:sameAs <WikidataURI>
    <ActorURI> owl:sameAs <WikidataURI>
"""

import pandas as pd
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL
from pathlib import Path


def create_wikidata_uri(wikidata_id: str) -> str:
    """Convert a Wikidata ID (e.g., Q12345) to a full Wikidata URI."""
    return f"http://www.wikidata.org/entity/{wikidata_id}"


def normalize_imdb_uri(uri: str) -> str:
    """Normalize IMDB URI to ensure consistent format (with trailing slash for actors)."""
    if pd.isna(uri):
        return None
    uri = str(uri).strip()
    # Ensure trailing slash for actor URIs
    if "/name/" in uri and not uri.endswith("/"):
        uri = uri + "/"
    return uri


def process_movies(df: pd.DataFrame, graph: Graph) -> tuple[int, int]:
    """
    Process movie DataFrame and add owl:sameAs triples to the graph.
    
    Returns:
        Tuple of (processed_count, skipped_count)
    """
    processed = 0
    skipped = 0
    
    for _, row in df.iterrows():
        movie_uri = row.get('movie_uri')
        wikidata_id = row.get('wikidata_id')
        
        # Skip if either value is missing
        if pd.isna(movie_uri) or pd.isna(wikidata_id):
            skipped += 1
            continue
        
        movie_uri = str(movie_uri).strip()
        wikidata_id = str(wikidata_id).strip()
        
        # Skip empty strings
        if not movie_uri or not wikidata_id:
            skipped += 1
            continue
        
        wikidata_uri = create_wikidata_uri(wikidata_id)
        
        # Add the owl:sameAs triple
        graph.add((URIRef(movie_uri), OWL.sameAs, URIRef(wikidata_uri)))
        processed += 1
    
    return processed, skipped


def process_actors(df: pd.DataFrame, graph: Graph) -> tuple[int, int]:
    """
    Process actor DataFrame and add owl:sameAs triples to the graph.
    
    Returns:
        Tuple of (processed_count, skipped_count)
    """
    processed = 0
    skipped = 0
    
    for _, row in df.iterrows():
        actor_uri = row.get('person_uri')
        wikidata_id = row.get('wikidata_id')
        
        # Skip if either value is missing
        if pd.isna(actor_uri) or pd.isna(wikidata_id):
            skipped += 1
            continue
        
        actor_uri = normalize_imdb_uri(actor_uri)
        wikidata_id = str(wikidata_id).strip()
        
        # Skip empty strings
        if not actor_uri or not wikidata_id:
            skipped += 1
            continue
        
        wikidata_uri = create_wikidata_uri(wikidata_id)
        
        # Add the owl:sameAs triple
        graph.add((URIRef(actor_uri), OWL.sameAs, URIRef(wikidata_uri)))
        processed += 1
    
    return processed, skipped


def main():
    # Define file paths
    base_path = Path(__file__).parent
    movie_stats_file = base_path / "movie_stats.xlsx"
    actor_stats_file = base_path / "actor_stats.xlsx"
    output_file = base_path / "KG" / "sameas_mappings.ttl"
    
    # Create KG directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize RDF graph
    graph = Graph()
    
    # Bind common prefixes
    graph.bind("owl", OWL)
    graph.bind("wd", Namespace("http://www.wikidata.org/entity/"))
    graph.bind("imdb", Namespace("https://www.imdb.com/"))
    
    print("=" * 60)
    print("Creating owl:sameAs mappings from IMDB to Wikidata")
    print("=" * 60)
    
    # Process movies
    print(f"\nReading movie stats from: {movie_stats_file}")
    movie_df = pd.read_excel(movie_stats_file)
    print(f"  Total movies in file: {len(movie_df)}")
    
    movies_processed, movies_skipped = process_movies(movie_df, graph)
    print(f"  Movies processed: {movies_processed}")
    print(f"  Movies skipped (missing data): {movies_skipped}")
    
    # Process actors
    print(f"\nReading actor stats from: {actor_stats_file}")
    actor_df = pd.read_excel(actor_stats_file)
    print(f"  Total actors in file: {len(actor_df)}")
    
    actors_processed, actors_skipped = process_actors(actor_df, graph)
    print(f"  Actors processed: {actors_processed}")
    print(f"  Actors skipped (missing data): {actors_skipped}")
    
    # Summary
    total_triples = len(graph)
    print(f"\n{'=' * 60}")
    print(f"Total owl:sameAs triples created: {total_triples}")
    print(f"{'=' * 60}")
    
    # Serialize to Turtle
    print(f"\nWriting Turtle file to: {output_file}")
    graph.serialize(destination=str(output_file), format="turtle")
    print(f"  File size: {output_file.stat().st_size:,} bytes")
    
    # Validate by reloading
    print(f"\n{'=' * 60}")
    print("Validating Turtle syntax by reloading with rdflib...")
    print("=" * 60)
    
    validation_graph = Graph()
    try:
        validation_graph.parse(str(output_file), format="turtle")
        print(f"  ✓ Validation successful!")
        print(f"  ✓ Loaded {len(validation_graph)} triples")
        
        # Show a sample of triples
        print(f"\nSample triples (first 5):")
        for i, (s, p, o) in enumerate(validation_graph):
            if i >= 5:
                break
            print(f"  {s}")
            print(f"    owl:sameAs {o}")
            print()
            
    except Exception as e:
        print(f"  ✗ Validation failed!")
        print(f"  Error: {e}")
        return 1
    
    print("Done!")
    return 0


if __name__ == "__main__":
    exit(main())

