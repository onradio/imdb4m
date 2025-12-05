#!/usr/bin/env python3
"""
Knowledge Graph Analysis Script

Loads all .ttl files from /extractor/movies subdirectories into a single RDF graph,
converts it to NetworkX for graph analysis, and computes statistics.
"""

import os
from pathlib import Path
from collections import Counter
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF
import networkx as nx
from tqdm import tqdm


def find_ttl_files(base_path: str) -> list[Path]:
    """Recursively find all .ttl files in the given directory."""
    base = Path(base_path)
    ttl_files = list(base.rglob("*.ttl"))
    return ttl_files


def load_kg(ttl_files: list[Path]) -> Graph:
    """Load all TTL files into a single RDF graph."""
    combined_graph = Graph()
    
    # Bind common prefixes
    combined_graph.bind("schema", "http://schema.org/")
    combined_graph.bind("xsd", "http://www.w3.org/2001/XMLSchema#")
    
    errors = []
    for ttl_file in tqdm(ttl_files, desc="Loading TTL files"):
        try:
            combined_graph.parse(str(ttl_file), format="turtle")
        except Exception as e:
            errors.append((ttl_file, str(e)))
    
    if errors:
        print(f"\n⚠️  Failed to load {len(errors)} files:")
        for file, error in errors[:10]:  # Show first 10 errors
            print(f"   - {file}: {error[:80]}...")
        if len(errors) > 10:
            print(f"   ... and {len(errors) - 10} more")
    
    return combined_graph


def rdf_to_networkx(rdf_graph: Graph) -> nx.DiGraph:
    """
    Convert RDF graph to NetworkX directed graph.
    Nodes are URIs/BNodes/Literals, edges are predicates.
    """
    nx_graph = nx.DiGraph()
    
    for s, p, o in tqdm(rdf_graph, desc="Converting to NetworkX", total=len(rdf_graph)):
        # Convert RDF terms to string identifiers
        s_id = str(s)
        p_id = str(p)
        o_id = str(o)
        
        # Add nodes with type information
        if not nx_graph.has_node(s_id):
            nx_graph.add_node(s_id, type=type(s).__name__)
        if not nx_graph.has_node(o_id):
            nx_graph.add_node(o_id, type=type(o).__name__)
        
        # Add edge with predicate as attribute
        # If edge already exists, we append the predicate to a list
        if nx_graph.has_edge(s_id, o_id):
            existing = nx_graph[s_id][o_id].get('predicates', [])
            existing.append(p_id)
            nx_graph[s_id][o_id]['predicates'] = existing
        else:
            nx_graph.add_edge(s_id, o_id, predicates=[p_id])
    
    return nx_graph


def rdf_to_networkx_undirected(rdf_graph: Graph) -> nx.Graph:
    """
    Convert RDF graph to NetworkX undirected graph for component analysis.
    Only includes URI nodes (no literals or blank nodes for cleaner analysis).
    """
    nx_graph = nx.Graph()
    
    for s, p, o in rdf_graph:
        # Only include URI-to-URI edges for entity graph
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            s_id = str(s)
            o_id = str(o)
            nx_graph.add_node(s_id)
            nx_graph.add_node(o_id)
            nx_graph.add_edge(s_id, o_id)
    
    return nx_graph


def compute_statistics(rdf_graph: Graph, nx_directed: nx.DiGraph, nx_undirected: nx.Graph):
    """Compute and display various KG statistics."""
    
    print("\n" + "=" * 70)
    print("📊 KNOWLEDGE GRAPH STATISTICS")
    print("=" * 70)
    
    # RDF-level statistics
    print("\n📋 RDF GRAPH METRICS")
    print("-" * 50)
    print(f"  Total Triples:              {len(rdf_graph):,}")
    
    # Count different node types
    subjects = set(rdf_graph.subjects())
    objects = set(rdf_graph.objects())
    predicates = set(rdf_graph.predicates())
    all_nodes = subjects | objects
    
    uri_nodes = sum(1 for n in all_nodes if isinstance(n, URIRef))
    bnode_nodes = sum(1 for n in all_nodes if isinstance(n, BNode))
    literal_nodes = sum(1 for n in all_nodes if isinstance(n, Literal))
    
    print(f"  Unique Subjects:            {len(subjects):,}")
    print(f"  Unique Objects:             {len(objects):,}")
    print(f"  Unique Predicates:          {len(predicates):,}")
    print(f"  Total Unique Nodes:         {len(all_nodes):,}")
    print(f"    - URIs:                   {uri_nodes:,}")
    print(f"    - Blank Nodes:            {bnode_nodes:,}")
    print(f"    - Literals:               {literal_nodes:,}")
    
    # NetworkX directed graph statistics
    print("\n📈 DIRECTED GRAPH METRICS (Full Graph)")
    print("-" * 50)
    print(f"  Nodes:                      {nx_directed.number_of_nodes():,}")
    print(f"  Edges:                      {nx_directed.number_of_edges():,}")
    
    # Degree statistics
    in_degrees = dict(nx_directed.in_degree())
    out_degrees = dict(nx_directed.out_degree())
    total_degrees = {n: in_degrees[n] + out_degrees[n] for n in nx_directed.nodes()}
    
    avg_in_degree = sum(in_degrees.values()) / len(in_degrees) if in_degrees else 0
    avg_out_degree = sum(out_degrees.values()) / len(out_degrees) if out_degrees else 0
    avg_total_degree = sum(total_degrees.values()) / len(total_degrees) if total_degrees else 0
    
    print(f"  Average In-Degree:          {avg_in_degree:.4f}")
    print(f"  Average Out-Degree:         {avg_out_degree:.4f}")
    print(f"  Average Total Degree:       {avg_total_degree:.4f}")
    
    max_in = max(in_degrees.values()) if in_degrees else 0
    max_out = max(out_degrees.values()) if out_degrees else 0
    max_total = max(total_degrees.values()) if total_degrees else 0
    
    print(f"  Max In-Degree:              {max_in:,}")
    print(f"  Max Out-Degree:             {max_out:,}")
    print(f"  Max Total Degree:           {max_total:,}")
    
    # Find nodes with max degrees
    if max_in > 0:
        max_in_nodes = [n for n, d in in_degrees.items() if d == max_in][:3]
        print(f"    Top In-Degree Node(s):    {max_in_nodes[0][:60]}...")
    if max_out > 0:
        max_out_nodes = [n for n, d in out_degrees.items() if d == max_out][:3]
        print(f"    Top Out-Degree Node(s):   {max_out_nodes[0][:60]}...")
    
    # Leaf nodes (nodes with only one connection)
    leaf_nodes_in = [n for n, d in in_degrees.items() if d == 1 and out_degrees[n] == 0]
    leaf_nodes_out = [n for n, d in out_degrees.items() if d == 1 and in_degrees[n] == 0]
    source_nodes = [n for n, d in in_degrees.items() if d == 0 and out_degrees[n] > 0]
    sink_nodes = [n for n, d in out_degrees.items() if d == 0 and in_degrees[n] > 0]
    
    print(f"\n  Source Nodes (in=0, out>0): {len(source_nodes):,}")
    print(f"  Sink Nodes (out=0, in>0):   {len(sink_nodes):,}")
    print(f"  Leaf Nodes (total deg=1):   {sum(1 for d in total_degrees.values() if d == 1):,}")
    
    # NetworkX undirected graph statistics (URI entities only)
    print("\n🔗 UNDIRECTED ENTITY GRAPH (URIs only)")
    print("-" * 50)
    print(f"  Entity Nodes:               {nx_undirected.number_of_nodes():,}")
    print(f"  Entity Edges:               {nx_undirected.number_of_edges():,}")
    
    # Connected components
    components = list(nx.connected_components(nx_undirected))
    component_sizes = sorted([len(c) for c in components], reverse=True)
    
    print(f"\n  Connected Components:       {len(components):,}")
    if component_sizes:
        print(f"    Largest Component:        {component_sizes[0]:,} nodes")
        if len(component_sizes) > 1:
            print(f"    2nd Largest Component:    {component_sizes[1]:,} nodes")
        if len(component_sizes) > 2:
            print(f"    3rd Largest Component:    {component_sizes[2]:,} nodes")
        
        # Component size distribution
        print(f"\n  Component Size Distribution:")
        size_counter = Counter(component_sizes)
        for size in sorted(size_counter.keys(), reverse=True)[:10]:
            count = size_counter[size]
            print(f"    Size {size:>6}: {count:,} component(s)")
        if len(size_counter) > 10:
            print(f"    ... and {len(size_counter) - 10} more size categories")
    
    # Leaf nodes in undirected graph
    undirected_degrees = dict(nx_undirected.degree())
    undirected_leaf_nodes = [n for n, d in undirected_degrees.items() if d == 1]
    isolated_nodes = [n for n, d in undirected_degrees.items() if d == 0]
    
    print(f"\n  Isolated Nodes (degree=0):  {len(isolated_nodes):,}")
    print(f"  Leaf Nodes (degree=1):      {len(undirected_leaf_nodes):,}")
    
    # Nodes with degree 2 connected to schema:Movie
    degree_2_nodes = [n for n, d in undirected_degrees.items() if d == 2]
    print(f"  Nodes with degree=2:        {len(degree_2_nodes):,}")
    
    # Find all Movie nodes (nodes that are of type schema:Movie)
    RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    SCHEMA_MOVIE = URIRef("http://schema.org/Movie")
    movie_nodes = set(str(s) for s, p, o in rdf_graph.triples((None, RDF_TYPE, SCHEMA_MOVIE)))
    
    # Count degree-2 nodes that are connected to a Movie or are a Movie themselves
    degree_2_with_movie = []
    for node in degree_2_nodes:
        # Check if this node is a Movie
        if node in movie_nodes:
            degree_2_with_movie.append(node)
            continue
        # Check if any neighbor is a Movie
        neighbors = set(nx_undirected.neighbors(node))
        if neighbors & movie_nodes:  # intersection
            degree_2_with_movie.append(node)
    
    print(f"  Degree=2 nodes linked to Movie: {len(degree_2_with_movie):,}")
    
    if undirected_degrees:
        avg_undirected_degree = sum(undirected_degrees.values()) / len(undirected_degrees)
        print(f"  Average Degree:             {avg_undirected_degree:.4f}")
        print(f"  Max Degree:                 {max(undirected_degrees.values()):,}")
    
    # Density
    if nx_undirected.number_of_nodes() > 1:
        density = nx.density(nx_undirected)
        print(f"  Graph Density:              {density:.6f}")
    
    # Predicate analysis
    print("\n📝 PREDICATE ANALYSIS")
    print("-" * 50)
    predicate_counts = Counter()
    for s, p, o in rdf_graph:
        predicate_counts[str(p)] += 1
    
    print(f"  Total Unique Predicates:    {len(predicate_counts):,}")
    print(f"\n  Top 15 Predicates:")
    for pred, count in predicate_counts.most_common(15):
        # Shorten predicate for display
        short_pred = pred.split("/")[-1] if "/" in pred else pred
        short_pred = short_pred.split("#")[-1] if "#" in short_pred else short_pred
        print(f"    {short_pred[:35]:35} {count:>10,}")
    
    # Node type distribution (schema:type analysis)
    print("\n🏷️  ENTITY TYPE ANALYSIS (rdf:type)")
    print("-" * 50)
    type_counts = Counter()
    RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    for s, p, o in rdf_graph.triples((None, RDF_TYPE, None)):
        type_counts[str(o)] += 1
    
    print(f"  Typed Entities:             {sum(type_counts.values()):,}")
    print(f"\n  Top 15 Entity Types:")
    for type_uri, count in type_counts.most_common(15):
        short_type = type_uri.split("/")[-1] if "/" in type_uri else type_uri
        short_type = short_type.split("#")[-1] if "#" in short_type else short_type
        print(f"    {short_type[:35]:35} {count:>10,}")
    
    # ===========================================================================
    # ORPHAN MOVIE ANALYSIS
    # Find movies where only one actor in the KG has starred in them
    # and we have no additional information beyond the actor's connection
    # ===========================================================================
    print("\n🎬 ORPHAN MOVIE ANALYSIS")
    print("-" * 50)
    
    SCHEMA = Namespace("http://schema.org/")
    PERFORMER_IN = SCHEMA.performerIn
    SCHEMA_ACTOR = SCHEMA.actor
    
    # Step 1: Find all movies (entities of type schema:Movie)
    all_movies = set(str(s) for s, p, o in rdf_graph.triples((None, RDF_TYPE, SCHEMA_MOVIE)))
    print(f"  Total Movies in KG:         {len(all_movies):,}")
    
    # Step 2: Count how many actors have schema:performerIn pointing to each movie
    # (This is the actor-centric view from actor.ttl files)
    movie_to_actors_performerIn = {}
    for s, p, o in rdf_graph.triples((None, PERFORMER_IN, None)):
        movie_uri = str(o)
        actor_uri = str(s)
        if movie_uri not in movie_to_actors_performerIn:
            movie_to_actors_performerIn[movie_uri] = set()
        movie_to_actors_performerIn[movie_uri].add(actor_uri)
    
    # Step 3: Count how many actors are linked via schema:actor on movies
    # (This is the movie-centric view, from movie.ttl files that list full cast)
    movie_to_actors_schema = {}
    for s, p, o in rdf_graph.triples((None, SCHEMA_ACTOR, None)):
        movie_uri = str(s)
        # o could be a PerformanceRole (blank node) or direct actor URI
        # We count movies that have schema:actor predicate
        if movie_uri not in movie_to_actors_schema:
            movie_to_actors_schema[movie_uri] = 0
        movie_to_actors_schema[movie_uri] += 1
    
    # Step 4: Find movies with only 1 actor via performerIn
    single_actor_movies = {
        movie: actors for movie, actors in movie_to_actors_performerIn.items()
        if len(actors) == 1
    }
    print(f"  Movies with 1 actor (performerIn): {len(single_actor_movies):,}")
    
    # Step 5: Among single-actor movies, find those with minimal info
    # "Minimal info" = the movie only has basic predicates (type, name, url, datePublished, actor)
    # and no rich metadata (no ratings, reviews, description, genre, director, etc.)
    MINIMAL_PREDICATES = {
        str(RDF_TYPE),
        str(SCHEMA.name),
        str(SCHEMA.url),
        str(SCHEMA.datePublished),
        str(SCHEMA_ACTOR),  # actor (PerformanceRole from the single actor's file)
    }
    
    orphan_movies = []
    for movie_uri in single_actor_movies:
        movie_ref = URIRef(movie_uri)
        # Get all predicates for this movie
        movie_predicates = set(str(p) for s, p, o in rdf_graph.triples((movie_ref, None, None)))
        
        # Check if movie has only minimal predicates
        extra_predicates = movie_predicates - MINIMAL_PREDICATES
        
        if not extra_predicates:
            # This movie has only minimal info from one actor file
            actor = list(single_actor_movies[movie_uri])[0]
            orphan_movies.append((movie_uri, actor))
    
    print(f"  Orphan movies (1 actor, minimal info): {len(orphan_movies):,}")
    
    # Show some examples
    if orphan_movies:
        print(f"\n  Examples of orphan movies (showing first 10):")
        for movie_uri, actor_uri in orphan_movies[:10]:
            # Get movie name
            movie_ref = URIRef(movie_uri)
            movie_name = None
            for s, p, o in rdf_graph.triples((movie_ref, SCHEMA.name, None)):
                movie_name = str(o)
                break
            # Get actor name
            actor_ref = URIRef(actor_uri)
            actor_name = None
            for s, p, o in rdf_graph.triples((actor_ref, SCHEMA.name, None)):
                actor_name = str(o)
                break
            
            movie_id = movie_uri.split("/")[-2] if movie_uri.endswith("/") else movie_uri.split("/")[-1]
            print(f"    {movie_id}: \"{movie_name or 'Unknown'}\" - only actor: {actor_name or actor_uri}")
    
    # Additional breakdown
    print(f"\n  Breakdown by actor count (via performerIn):")
    actor_count_dist = Counter(len(actors) for actors in movie_to_actors_performerIn.values())
    for count in sorted(actor_count_dist.keys())[:10]:
        num_movies = actor_count_dist[count]
        print(f"    {count} actor(s): {num_movies:,} movies")
    if len(actor_count_dist) > 10:
        print(f"    ... and more")
    
    return {
        'num_triples': len(rdf_graph),
        'num_nodes': len(all_nodes),
        'num_predicates': len(predicates),
        'num_components': len(components),
        'largest_component': component_sizes[0] if component_sizes else 0,
        'avg_degree': avg_total_degree,
        'num_leaf_nodes': len(undirected_leaf_nodes),
        'orphan_movies': [uri for uri, _ in orphan_movies],  # Return orphan movie URIs
    }


def remove_orphan_movies(rdf_graph: Graph, orphan_movie_uris: list[str]) -> Graph:
    """
    Remove all triples where orphan movies appear as subject or object.
    Also removes associated blank nodes (PerformanceRole) linked to these movies.
    """
    print(f"\n🧹 REMOVING ORPHAN MOVIE TRIPLES")
    print("-" * 50)
    
    orphan_set = set(orphan_movie_uris)
    print(f"  Orphan movies to remove: {len(orphan_set):,}")
    
    initial_count = len(rdf_graph)
    
    # Collect triples to remove
    triples_to_remove = []
    blank_nodes_to_remove = set()
    
    # Step 1: Find all triples where orphan movie is subject
    for movie_uri in tqdm(orphan_set, desc="Finding subject triples"):
        movie_ref = URIRef(movie_uri)
        for s, p, o in rdf_graph.triples((movie_ref, None, None)):
            triples_to_remove.append((s, p, o))
            # If object is a blank node, mark it for removal
            if isinstance(o, BNode):
                blank_nodes_to_remove.add(o)
    
    # Step 2: Find all triples where orphan movie is object
    for movie_uri in tqdm(orphan_set, desc="Finding object triples"):
        movie_ref = URIRef(movie_uri)
        for s, p, o in rdf_graph.triples((None, None, movie_ref)):
            triples_to_remove.append((s, p, o))
    
    # Step 3: Find all triples from blank nodes associated with orphan movies
    # (e.g., PerformanceRole nodes)
    for bnode in tqdm(blank_nodes_to_remove, desc="Finding blank node triples"):
        for s, p, o in rdf_graph.triples((bnode, None, None)):
            triples_to_remove.append((s, p, o))
    
    print(f"  Triples to remove: {len(triples_to_remove):,}")
    
    # Remove triples
    for triple in tqdm(triples_to_remove, desc="Removing triples"):
        try:
            rdf_graph.remove(triple)
        except:
            pass  # Triple may have already been removed
    
    final_count = len(rdf_graph)
    removed_count = initial_count - final_count
    
    print(f"  Initial triples: {initial_count:,}")
    print(f"  Final triples: {final_count:,}")
    print(f"  Triples removed: {removed_count:,}")
    
    return rdf_graph


def sanitize_graph(rdf_graph: Graph) -> Graph:
    """Remove triples with invalid URIs that would break serialization."""
    import re
    
    print("\n🔧 SANITIZING GRAPH (removing invalid URIs)")
    print("-" * 50)
    
    # Pattern to detect invalid URIs (containing spaces or other bad chars)
    def is_valid_uri(uri_str: str) -> bool:
        # URIs shouldn't contain unencoded spaces
        if ' ' in uri_str:
            return False
        return True
    
    invalid_triples = []
    for s, p, o in rdf_graph:
        if isinstance(s, URIRef) and not is_valid_uri(str(s)):
            invalid_triples.append((s, p, o))
        elif isinstance(o, URIRef) and not is_valid_uri(str(o)):
            invalid_triples.append((s, p, o))
    
    print(f"  Invalid triples found: {len(invalid_triples):,}")
    
    for triple in invalid_triples:
        rdf_graph.remove(triple)
    
    print(f"  Triples after sanitization: {len(rdf_graph):,}")
    
    return rdf_graph


def save_kg(rdf_graph: Graph, output_dir: Path, filename: str = "imdb_kg_cleaned.ttl"):
    """Save the RDF graph to a Turtle file."""
    print(f"\n💾 SAVING KNOWLEDGE GRAPH")
    print("-" * 50)
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    
    print(f"  Output directory: {output_dir}")
    print(f"  Output file: {output_path}")
    print(f"  Triples to save: {len(rdf_graph):,}")
    
    # Sanitize graph first
    rdf_graph = sanitize_graph(rdf_graph)
    
    # Serialize to Turtle format
    print("  Serializing to Turtle format...")
    rdf_graph.serialize(destination=str(output_path), format="turtle")
    
    # Get file size
    file_size = output_path.stat().st_size
    if file_size > 1024 * 1024 * 1024:
        size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
    elif file_size > 1024 * 1024:
        size_str = f"{file_size / (1024 * 1024):.2f} MB"
    elif file_size > 1024:
        size_str = f"{file_size / 1024:.2f} KB"
    else:
        size_str = f"{file_size} bytes"
    
    print(f"  ✅ Saved! File size: {size_str}")
    
    return output_path


def main():
    # Configuration
    BASE_PATH = Path(__file__).parent / "extractor" / "movies"
    OUTPUT_DIR = Path(__file__).parent / "KG"
    
    print("=" * 70)
    print("🎬 IMDB KNOWLEDGE GRAPH ANALYZER")
    print("=" * 70)
    print(f"\n📂 Scanning directory: {BASE_PATH}")
    
    # Find all TTL files
    ttl_files = find_ttl_files(BASE_PATH)
    print(f"✅ Found {len(ttl_files):,} TTL files")
    
    if not ttl_files:
        print("❌ No TTL files found. Exiting.")
        return
    
    # Load into RDF graph
    print("\n📥 Loading TTL files into RDF graph...")
    rdf_graph = load_kg(ttl_files)
    print(f"✅ Loaded {len(rdf_graph):,} triples")
    
    # Convert to NetworkX
    print("\n🔄 Converting to NetworkX graphs...")
    nx_directed = rdf_to_networkx(rdf_graph)
    nx_undirected = rdf_to_networkx_undirected(rdf_graph)
    print(f"✅ Created directed graph: {nx_directed.number_of_nodes():,} nodes, {nx_directed.number_of_edges():,} edges")
    print(f"✅ Created undirected entity graph: {nx_undirected.number_of_nodes():,} nodes, {nx_undirected.number_of_edges():,} edges")
    
    # Compute statistics (original graph)
    print("\n" + "=" * 70)
    print("📊 ORIGINAL KNOWLEDGE GRAPH STATISTICS")
    print("=" * 70)
    stats = compute_statistics(rdf_graph, nx_directed, nx_undirected)
    
    # Get orphan movies from stats
    orphan_movies = stats.get('orphan_movies', [])
    
    if orphan_movies:
        # Remove orphan movie triples
        rdf_graph = remove_orphan_movies(rdf_graph, orphan_movies)
        
        # Rebuild NetworkX graphs from cleaned RDF
        print("\n🔄 Rebuilding NetworkX graphs from cleaned KG...")
        nx_directed_clean = rdf_to_networkx(rdf_graph)
        nx_undirected_clean = rdf_to_networkx_undirected(rdf_graph)
        print(f"✅ Created directed graph: {nx_directed_clean.number_of_nodes():,} nodes, {nx_directed_clean.number_of_edges():,} edges")
        print(f"✅ Created undirected entity graph: {nx_undirected_clean.number_of_nodes():,} nodes, {nx_undirected_clean.number_of_edges():,} edges")
        
        # Compute statistics (cleaned graph)
        print("\n" + "=" * 70)
        print("📊 CLEANED KNOWLEDGE GRAPH STATISTICS")
        print("=" * 70)
        stats_clean = compute_statistics(rdf_graph, nx_directed_clean, nx_undirected_clean)
        
        # Save cleaned KG
        output_path = save_kg(rdf_graph, OUTPUT_DIR)
        
        # Summary comparison
        print("\n" + "=" * 70)
        print("📈 SUMMARY COMPARISON")
        print("=" * 70)
        print(f"  {'Metric':<30} {'Original':>15} {'Cleaned':>15} {'Removed':>15}")
        print("-" * 75)
        print(f"  {'Triples':<30} {stats['num_triples']:>15,} {stats_clean['num_triples']:>15,} {stats['num_triples'] - stats_clean['num_triples']:>15,}")
        print(f"  {'Nodes':<30} {stats['num_nodes']:>15,} {stats_clean['num_nodes']:>15,} {stats['num_nodes'] - stats_clean['num_nodes']:>15,}")
        print(f"  {'Connected Components':<30} {stats['num_components']:>15,} {stats_clean['num_components']:>15,} {stats_clean['num_components'] - stats['num_components']:>15,}")
        print(f"  {'Leaf Nodes':<30} {stats['num_leaf_nodes']:>15,} {stats_clean['num_leaf_nodes']:>15,} {stats['num_leaf_nodes'] - stats_clean['num_leaf_nodes']:>15,}")
    else:
        # No orphan movies found, just save original
        output_path = save_kg(rdf_graph, OUTPUT_DIR, "imdb_kg_full.ttl")
        stats_clean = stats
        nx_directed_clean = nx_directed
        nx_undirected_clean = nx_undirected
    
    print("\n" + "=" * 70)
    print("✅ Analysis Complete!")
    print("=" * 70)
    
    return rdf_graph, nx_directed_clean, nx_undirected_clean, stats_clean


if __name__ == "__main__":
    main()

