#!/usr/bin/env python3
"""
Knowledge Graph Statistics Script

Loads a single TTL file using rdflib and converts to NetworkX
for comprehensive graph analysis and statistics computation.
"""

import sys
from pathlib import Path
from collections import Counter
from typing import Optional
from rdflib import Graph, URIRef, Literal, BNode, Namespace
from rdflib.namespace import RDF, RDFS, XSD
import networkx as nx
from tqdm import tqdm


# Define common namespaces
SCHEMA = Namespace("http://schema.org/")


def load_single_ttl(file_path: str | Path) -> Graph:
    """Load a single TTL file into an RDF graph."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"TTL file not found: {file_path}")
    
    print(f"📂 Loading TTL file: {file_path}")
    print(f"   File size: {file_path.stat().st_size / (1024 * 1024):.2f} MB")
    
    rdf_graph = Graph()
    rdf_graph.bind("schema", SCHEMA)
    rdf_graph.bind("xsd", XSD)
    rdf_graph.bind("rdf", RDF)
    rdf_graph.bind("rdfs", RDFS)
    
    print("   Parsing Turtle format...")
    rdf_graph.parse(str(file_path), format="turtle")
    
    print(f"✅ Loaded {len(rdf_graph):,} triples")
    return rdf_graph


def rdf_to_networkx_directed(rdf_graph: Graph) -> nx.DiGraph:
    """
    Convert RDF graph to NetworkX directed graph.
    Nodes are URIs/BNodes/Literals, edges are predicates.
    """
    print("\n🔄 Converting to directed NetworkX graph...")
    nx_graph = nx.DiGraph()
    
    for s, p, o in tqdm(rdf_graph, desc="   Processing triples", total=len(rdf_graph)):
        s_id = str(s)
        p_id = str(p)
        o_id = str(o)
        
        # Add nodes with type information
        if not nx_graph.has_node(s_id):
            nx_graph.add_node(s_id, 
                              node_type=type(s).__name__,
                              is_uri=isinstance(s, URIRef),
                              is_literal=isinstance(s, Literal),
                              is_bnode=isinstance(s, BNode))
        if not nx_graph.has_node(o_id):
            nx_graph.add_node(o_id,
                              node_type=type(o).__name__,
                              is_uri=isinstance(o, URIRef),
                              is_literal=isinstance(o, Literal),
                              is_bnode=isinstance(o, BNode))
        
        # Add edge with predicate as attribute
        if nx_graph.has_edge(s_id, o_id):
            existing = nx_graph[s_id][o_id].get('predicates', [])
            existing.append(p_id)
            nx_graph[s_id][o_id]['predicates'] = existing
        else:
            nx_graph.add_edge(s_id, o_id, predicates=[p_id])
    
    print(f"✅ Directed graph: {nx_graph.number_of_nodes():,} nodes, {nx_graph.number_of_edges():,} edges")
    return nx_graph


def rdf_to_networkx_undirected(rdf_graph: Graph) -> nx.Graph:
    """
    Convert RDF graph to NetworkX undirected graph for component analysis.
    Only includes URI nodes (no literals or blank nodes for cleaner entity analysis).
    """
    print("\n🔄 Converting to undirected entity graph (URIs only)...")
    nx_graph = nx.Graph()
    
    for s, p, o in rdf_graph:
        # Only include URI-to-URI edges for entity graph
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            nx_graph.add_node(str(s))
            nx_graph.add_node(str(o))
            nx_graph.add_edge(str(s), str(o))
    
    print(f"✅ Undirected entity graph: {nx_graph.number_of_nodes():,} nodes, {nx_graph.number_of_edges():,} edges")
    return nx_graph


def compute_basic_rdf_stats(rdf_graph: Graph) -> dict:
    """Compute basic RDF-level statistics."""
    print("\n" + "=" * 80)
    print("📊 BASIC RDF STATISTICS")
    print("=" * 80)
    
    subjects = set(rdf_graph.subjects())
    predicates = set(rdf_graph.predicates())
    objects = set(rdf_graph.objects())
    all_nodes = subjects | objects
    
    # Count node types
    uri_subjects = sum(1 for n in subjects if isinstance(n, URIRef))
    bnode_subjects = sum(1 for n in subjects if isinstance(n, BNode))
    
    uri_objects = sum(1 for n in objects if isinstance(n, URIRef))
    bnode_objects = sum(1 for n in objects if isinstance(n, BNode))
    literal_objects = sum(1 for n in objects if isinstance(n, Literal))
    
    uri_nodes = sum(1 for n in all_nodes if isinstance(n, URIRef))
    bnode_nodes = sum(1 for n in all_nodes if isinstance(n, BNode))
    literal_nodes = sum(1 for n in all_nodes if isinstance(n, Literal))
    
    print(f"\n  📋 Triple Statistics:")
    print(f"     Total Triples:                    {len(rdf_graph):,}")
    
    print(f"\n  📌 Subject Statistics:")
    print(f"     Unique Subjects:                  {len(subjects):,}")
    print(f"       - URI Subjects:                 {uri_subjects:,}")
    print(f"       - Blank Node Subjects:          {bnode_subjects:,}")
    
    print(f"\n  🔗 Predicate Statistics:")
    print(f"     Unique Predicates:                {len(predicates):,}")
    
    print(f"\n  🎯 Object Statistics:")
    print(f"     Unique Objects:                   {len(objects):,}")
    print(f"       - URI Objects:                  {uri_objects:,}")
    print(f"       - Blank Node Objects:           {bnode_objects:,}")
    print(f"       - Literal Objects:              {literal_objects:,}")
    
    print(f"\n  🔵 Total Node Statistics:")
    print(f"     Total Unique Nodes:               {len(all_nodes):,}")
    print(f"       - URIs:                         {uri_nodes:,}")
    print(f"       - Blank Nodes:                  {bnode_nodes:,}")
    print(f"       - Literals:                     {literal_nodes:,}")
    
    return {
        'num_triples': len(rdf_graph),
        'num_subjects': len(subjects),
        'num_predicates': len(predicates),
        'num_objects': len(objects),
        'num_nodes': len(all_nodes),
        'num_uri_nodes': uri_nodes,
        'num_bnode_nodes': bnode_nodes,
        'num_literal_nodes': literal_nodes,
    }


def compute_degree_statistics(nx_graph: nx.DiGraph) -> dict:
    """Compute degree statistics for the directed graph."""
    print("\n" + "=" * 80)
    print("📈 DEGREE STATISTICS (Directed Graph)")
    print("=" * 80)
    
    in_degrees = dict(nx_graph.in_degree())
    out_degrees = dict(nx_graph.out_degree())
    total_degrees = {n: in_degrees[n] + out_degrees[n] for n in nx_graph.nodes()}
    
    # Basic degree stats
    avg_in = sum(in_degrees.values()) / len(in_degrees) if in_degrees else 0
    avg_out = sum(out_degrees.values()) / len(out_degrees) if out_degrees else 0
    avg_total = sum(total_degrees.values()) / len(total_degrees) if total_degrees else 0
    
    max_in = max(in_degrees.values()) if in_degrees else 0
    max_out = max(out_degrees.values()) if out_degrees else 0
    max_total = max(total_degrees.values()) if total_degrees else 0
    
    min_in = min(in_degrees.values()) if in_degrees else 0
    min_out = min(out_degrees.values()) if out_degrees else 0
    min_total = min(total_degrees.values()) if total_degrees else 0
    
    # Median degrees
    sorted_in = sorted(in_degrees.values())
    sorted_out = sorted(out_degrees.values())
    sorted_total = sorted(total_degrees.values())
    
    median_in = sorted_in[len(sorted_in) // 2] if sorted_in else 0
    median_out = sorted_out[len(sorted_out) // 2] if sorted_out else 0
    median_total = sorted_total[len(sorted_total) // 2] if sorted_total else 0
    
    print(f"\n  📊 In-Degree (incoming edges):")
    print(f"     Minimum:        {min_in:,}")
    print(f"     Maximum:        {max_in:,}")
    print(f"     Average:        {avg_in:.4f}")
    print(f"     Median:         {median_in}")
    
    print(f"\n  📊 Out-Degree (outgoing edges):")
    print(f"     Minimum:        {min_out:,}")
    print(f"     Maximum:        {max_out:,}")
    print(f"     Average:        {avg_out:.4f}")
    print(f"     Median:         {median_out}")
    
    print(f"\n  📊 Total Degree:")
    print(f"     Minimum:        {min_total:,}")
    print(f"     Maximum:        {max_total:,}")
    print(f"     Average:        {avg_total:.4f}")
    print(f"     Median:         {median_total}")
    
    # Find hub nodes (nodes with very high degree)
    print(f"\n  🌟 Top 10 Nodes by In-Degree:")
    top_in = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (node, degree) in enumerate(top_in, 1):
        node_short = node[:70] + "..." if len(node) > 70 else node
        print(f"     {i:2}. [{degree:>6,}] {node_short}")
    
    print(f"\n  🌟 Top 10 Nodes by Out-Degree:")
    top_out = sorted(out_degrees.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (node, degree) in enumerate(top_out, 1):
        node_short = node[:70] + "..." if len(node) > 70 else node
        print(f"     {i:2}. [{degree:>6,}] {node_short}")
    
    return {
        'avg_in_degree': avg_in,
        'avg_out_degree': avg_out,
        'avg_total_degree': avg_total,
        'max_in_degree': max_in,
        'max_out_degree': max_out,
        'max_total_degree': max_total,
        'median_in_degree': median_in,
        'median_out_degree': median_out,
        'median_total_degree': median_total,
        'in_degrees': in_degrees,
        'out_degrees': out_degrees,
        'total_degrees': total_degrees,
    }


def compute_structural_statistics(nx_directed: nx.DiGraph, degree_stats: dict) -> dict:
    """Compute structural statistics (leaf nodes, sources, sinks, etc.)."""
    print("\n" + "=" * 80)
    print("🏗️  STRUCTURAL STATISTICS")
    print("=" * 80)
    
    in_degrees = degree_stats['in_degrees']
    out_degrees = degree_stats['out_degrees']
    total_degrees = degree_stats['total_degrees']
    
    # Leaf nodes (degree = 1)
    leaf_nodes = [n for n, d in total_degrees.items() if d == 1]
    
    # Source nodes (in-degree = 0, out-degree > 0) - no incoming edges
    source_nodes = [n for n in nx_directed.nodes() if in_degrees[n] == 0 and out_degrees[n] > 0]
    
    # Sink nodes (out-degree = 0, in-degree > 0) - no outgoing edges  
    sink_nodes = [n for n in nx_directed.nodes() if out_degrees[n] == 0 and in_degrees[n] > 0]
    
    # Isolated nodes (degree = 0)
    isolated_nodes = [n for n, d in total_degrees.items() if d == 0]
    
    # Bridge nodes (degree = 2) - potential bottlenecks
    bridge_candidates = [n for n, d in total_degrees.items() if d == 2]
    
    # Hub nodes (top 1% by degree)
    threshold_degree = sorted(total_degrees.values(), reverse=True)[len(total_degrees) // 100] if len(total_degrees) > 100 else max(total_degrees.values())
    hub_nodes = [n for n, d in total_degrees.items() if d >= threshold_degree]
    
    # Node type distribution by structural role
    uri_nodes = [n for n, data in nx_directed.nodes(data=True) if data.get('is_uri', False)]
    literal_nodes = [n for n, data in nx_directed.nodes(data=True) if data.get('is_literal', False)]
    bnode_nodes = [n for n, data in nx_directed.nodes(data=True) if data.get('is_bnode', False)]
    
    print(f"\n  🍃 Leaf Nodes (total degree = 1):")
    print(f"     Count:                            {len(leaf_nodes):,}")
    print(f"     Percentage of all nodes:          {100 * len(leaf_nodes) / len(total_degrees):.2f}%")
    
    print(f"\n  ➡️  Source Nodes (in=0, out>0):")
    print(f"     Count:                            {len(source_nodes):,}")
    print(f"     Percentage of all nodes:          {100 * len(source_nodes) / len(total_degrees):.2f}%")
    
    print(f"\n  ⬇️  Sink Nodes (out=0, in>0):")
    print(f"     Count:                            {len(sink_nodes):,}")
    print(f"     Percentage of all nodes:          {100 * len(sink_nodes) / len(total_degrees):.2f}%")
    
    print(f"\n  ⚫ Isolated Nodes (degree = 0):")
    print(f"     Count:                            {len(isolated_nodes):,}")
    
    print(f"\n  🌉 Bridge Candidates (degree = 2):")
    print(f"     Count:                            {len(bridge_candidates):,}")
    
    print(f"\n  🌟 Hub Nodes (top 1% by degree, >= {threshold_degree}):")
    print(f"     Count:                            {len(hub_nodes):,}")
    
    print(f"\n  📊 Node Type Distribution:")
    print(f"     URI Nodes:                        {len(uri_nodes):,}")
    print(f"     Literal Nodes:                    {len(literal_nodes):,}")
    print(f"     Blank Nodes:                      {len(bnode_nodes):,}")
    
    # Degree distribution histogram
    print(f"\n  📊 Degree Distribution (directed graph):")
    degree_counter = Counter(total_degrees.values())
    sorted_degrees = sorted(degree_counter.items())
    
    # Show first 15 buckets
    print(f"     {'Degree':<10} {'Count':>12} {'Percentage':>12}")
    print(f"     {'-'*35}")
    for deg, count in sorted_degrees[:15]:
        pct = 100 * count / len(total_degrees)
        print(f"     {deg:<10} {count:>12,} {pct:>11.2f}%")
    if len(sorted_degrees) > 15:
        remaining = sum(c for d, c in sorted_degrees[15:])
        print(f"     {'...':<10} {remaining:>12,} (remaining)")
    
    return {
        'num_leaf_nodes': len(leaf_nodes),
        'num_source_nodes': len(source_nodes),
        'num_sink_nodes': len(sink_nodes),
        'num_isolated_nodes': len(isolated_nodes),
        'num_bridge_candidates': len(bridge_candidates),
        'num_hub_nodes': len(hub_nodes),
        'leaf_nodes': leaf_nodes[:100],  # Store sample
        'source_nodes': source_nodes[:100],
        'sink_nodes': sink_nodes[:100],
        'hub_nodes': hub_nodes[:100],
    }


def compute_connected_components(nx_undirected: nx.Graph, rdf_graph: Graph) -> dict:
    """Analyze connected components in the undirected entity graph."""
    print("\n" + "=" * 80)
    print("🔗 CONNECTED COMPONENTS ANALYSIS (Undirected Entity Graph)")
    print("=" * 80)
    
    components = list(nx.connected_components(nx_undirected))
    component_sizes = sorted([len(c) for c in components], reverse=True)
    
    print(f"\n  📊 Component Overview:")
    print(f"     Total Components:                 {len(components):,}")
    
    if component_sizes:
        print(f"     Largest Component:                {component_sizes[0]:,} nodes")
        if len(component_sizes) > 1:
            print(f"     2nd Largest:                      {component_sizes[1]:,} nodes")
        if len(component_sizes) > 2:
            print(f"     3rd Largest:                      {component_sizes[2]:,} nodes")
        
        # Component size statistics
        avg_size = sum(component_sizes) / len(component_sizes)
        median_size = component_sizes[len(component_sizes) // 2]
        
        print(f"\n  📊 Component Size Statistics:")
        print(f"     Minimum Size:                     {min(component_sizes):,}")
        print(f"     Maximum Size:                     {max(component_sizes):,}")
        print(f"     Average Size:                     {avg_size:.2f}")
        print(f"     Median Size:                      {median_size:,}")
        
        # Component size distribution
        print(f"\n  📊 Component Size Distribution:")
        size_counter = Counter(component_sizes)
        sorted_sizes = sorted(size_counter.items(), key=lambda x: x[0], reverse=True)
        
        print(f"     {'Size':<12} {'Count':>10} {'Total Nodes':>15}")
        print(f"     {'-'*40}")
        for size, count in sorted_sizes[:15]:
            total = size * count
            print(f"     {size:<12,} {count:>10,} {total:>15,}")
        if len(sorted_sizes) > 15:
            print(f"     ... and {len(sorted_sizes) - 15} more size categories")
        
        # Singleton analysis
        singletons = [c for c in components if len(c) == 1]
        print(f"\n  ⚠️  Singleton Components (size=1):")
        print(f"     Count:                            {len(singletons):,}")
        print(f"     Percentage of components:         {100 * len(singletons) / len(components):.2f}%")
        
        # Small components (size <= 5)
        small_components = [c for c in components if len(c) <= 5]
        print(f"\n  📦 Small Components (size <= 5):")
        print(f"     Count:                            {len(small_components):,}")
        print(f"     Percentage of components:         {100 * len(small_components) / len(components):.2f}%")
    
    # Analyze largest component contents
    if components:
        largest = max(components, key=len)
        print(f"\n  🔍 Largest Component Analysis:")
        print(f"     Nodes:                            {len(largest):,}")
        
        # Count entity types in largest component
        type_counts = Counter()
        for node in largest:
            node_ref = URIRef(node)
            for s, p, o in rdf_graph.triples((node_ref, RDF.type, None)):
                type_counts[str(o)] += 1
        
        print(f"     Entity Types in Largest Component:")
        for type_uri, count in type_counts.most_common(10):
            short_type = type_uri.split("/")[-1] if "/" in type_uri else type_uri
            short_type = short_type.split("#")[-1] if "#" in short_type else short_type
            print(f"       {short_type[:40]:40} {count:>8,}")
    
    return {
        'num_components': len(components),
        'component_sizes': component_sizes,
        'largest_component_size': component_sizes[0] if component_sizes else 0,
        'num_singletons': len([c for c in components if len(c) == 1]),
        'num_small_components': len([c for c in components if len(c) <= 5]),
    }


def compute_predicate_analysis(rdf_graph: Graph) -> dict:
    """Analyze predicate usage patterns."""
    print("\n" + "=" * 80)
    print("📝 PREDICATE ANALYSIS")
    print("=" * 80)
    
    predicate_counts = Counter()
    predicate_subject_types = {}  # predicate -> set of subject types
    predicate_object_types = {}   # predicate -> set of object types
    
    for s, p, o in rdf_graph:
        p_str = str(p)
        predicate_counts[p_str] += 1
        
        # Track what types of nodes use this predicate
        if p_str not in predicate_subject_types:
            predicate_subject_types[p_str] = Counter()
            predicate_object_types[p_str] = Counter()
        
        predicate_subject_types[p_str][type(s).__name__] += 1
        predicate_object_types[p_str][type(o).__name__] += 1
    
    print(f"\n  📊 Predicate Overview:")
    print(f"     Total Unique Predicates:          {len(predicate_counts):,}")
    print(f"     Total Predicate Usages:           {sum(predicate_counts.values()):,}")
    
    avg_usage = sum(predicate_counts.values()) / len(predicate_counts) if predicate_counts else 0
    print(f"     Average Usage per Predicate:      {avg_usage:.2f}")
    
    print(f"\n  🏆 Complete Predicate Frequency Distribution:")
    print(f"     {'#':<4} {'Predicate':<40} {'Count':>12} {'%':>8} {'Cumulative %':>14}")
    print(f"     {'-'*82}")
    total_triples = len(rdf_graph)
    cumulative = 0
    for i, (pred, count) in enumerate(predicate_counts.most_common(), 1):
        short_pred = pred.split("/")[-1] if "/" in pred else pred
        short_pred = short_pred.split("#")[-1] if "#" in short_pred else short_pred
        pct = 100 * count / total_triples
        cumulative += pct
        print(f"     {i:<4} {short_pred[:40]:40} {count:>12,} {pct:>7.2f}% {cumulative:>13.2f}%")
    
    # Rare predicates (used only once)
    rare_predicates = [p for p, c in predicate_counts.items() if c == 1]
    print(f"\n  ⚠️  Rare Predicates (used only once):")
    print(f"     Count:                            {len(rare_predicates):,}")
    if rare_predicates:
        print(f"     Examples (first 5):")
        for pred in rare_predicates[:5]:
            short_pred = pred.split("/")[-1] if "/" in pred else pred
            short_pred = short_pred.split("#")[-1] if "#" in short_pred else short_pred
            print(f"       - {short_pred[:60]}")
    
    # Predicate domains (subject types)
    print(f"\n  📊 Predicate Subject Type Distribution (Top 10 predicates):")
    for pred, count in predicate_counts.most_common(10):
        short_pred = pred.split("/")[-1] if "/" in pred else pred
        short_pred = short_pred.split("#")[-1] if "#" in short_pred else short_pred
        subj_types = predicate_subject_types[pred]
        type_str = ", ".join([f"{t}:{c}" for t, c in subj_types.most_common(3)])
        print(f"     {short_pred[:35]:35} -> {type_str}")
    
    return {
        'num_predicates': len(predicate_counts),
        'predicate_counts': dict(predicate_counts),
        'num_rare_predicates': len(rare_predicates),
        'top_predicates': predicate_counts.most_common(20),
    }


def compute_entity_type_analysis(rdf_graph: Graph) -> dict:
    """Analyze entity types (rdf:type statements)."""
    print("\n" + "=" * 80)
    print("🏷️  ENTITY TYPE ANALYSIS")
    print("=" * 80)
    
    type_counts = Counter()
    entity_type_map = {}  # entity -> list of types
    
    for s, p, o in rdf_graph.triples((None, RDF.type, None)):
        s_str = str(s)
        o_str = str(o)
        type_counts[o_str] += 1
        
        if s_str not in entity_type_map:
            entity_type_map[s_str] = []
        entity_type_map[s_str].append(o_str)
    
    print(f"\n  📊 Entity Type Overview:")
    print(f"     Unique Entity Types:              {len(type_counts):,}")
    print(f"     Typed Entities:                   {len(entity_type_map):,}")
    print(f"     Total Type Assertions:            {sum(type_counts.values()):,}")
    
    # Multi-typed entities
    multi_typed = [e for e, types in entity_type_map.items() if len(types) > 1]
    print(f"\n  🔄 Multi-Typed Entities:")
    print(f"     Count:                            {len(multi_typed):,}")
    if multi_typed:
        print(f"     Examples (first 5):")
        for entity in multi_typed[:5]:
            types = entity_type_map[entity]
            short_entity = entity.split("/")[-1] if "/" in entity else entity
            short_types = [t.split("/")[-1].split("#")[-1] for t in types]
            print(f"       {short_entity[:50]} -> {', '.join(short_types)}")
    
    print(f"\n  🏆 Top 15 Entity Types:")
    print(f"     {'Type':<45} {'Count':>12}")
    print(f"     {'-'*60}")
    for type_uri, count in type_counts.most_common(15):
        short_type = type_uri.split("/")[-1] if "/" in type_uri else type_uri
        short_type = short_type.split("#")[-1] if "#" in short_type else short_type
        print(f"     {short_type[:45]:45} {count:>12,}")
    
    return {
        'num_entity_types': len(type_counts),
        'num_typed_entities': len(entity_type_map),
        'num_multi_typed': len(multi_typed),
        'type_counts': dict(type_counts),
        'top_types': type_counts.most_common(15),
    }


def compute_graph_density_metrics(nx_directed: nx.DiGraph, nx_undirected: nx.Graph) -> dict:
    """Compute graph density and clustering metrics."""
    print("\n" + "=" * 80)
    print("📐 GRAPH DENSITY & CLUSTERING METRICS")
    print("=" * 80)
    
    print(f"\n  📊 Directed Graph Metrics:")
    directed_nodes = nx_directed.number_of_nodes()
    directed_edges = nx_directed.number_of_edges()
    
    # Density for directed graph
    if directed_nodes > 1:
        directed_density = directed_edges / (directed_nodes * (directed_nodes - 1))
    else:
        directed_density = 0
    
    print(f"     Nodes:                            {directed_nodes:,}")
    print(f"     Edges:                            {directed_edges:,}")
    print(f"     Density:                          {directed_density:.10f}")
    print(f"     Max Possible Edges:               {directed_nodes * (directed_nodes - 1):,}")
    
    print(f"\n  📊 Undirected Entity Graph Metrics:")
    undirected_nodes = nx_undirected.number_of_nodes()
    undirected_edges = nx_undirected.number_of_edges()
    
    if undirected_nodes > 1:
        undirected_density = nx.density(nx_undirected)
    else:
        undirected_density = 0
    
    print(f"     Nodes:                            {undirected_nodes:,}")
    print(f"     Edges:                            {undirected_edges:,}")
    print(f"     Density:                          {undirected_density:.10f}")
    
    # Calculate average clustering coefficient for undirected graph
    # This can be expensive for large graphs, so we sample if needed
    if undirected_nodes < 50000:
        print("\n  🔶 Computing Clustering Coefficient (may take a moment)...")
        try:
            avg_clustering = nx.average_clustering(nx_undirected)
            print(f"     Average Clustering Coefficient:   {avg_clustering:.6f}")
        except Exception as e:
            print(f"     Could not compute clustering: {e}")
            avg_clustering = None
    else:
        print(f"\n  ⚠️  Graph too large for clustering coefficient ({undirected_nodes:,} nodes)")
        print("      Sampling 10,000 nodes for approximate clustering...")
        import random
        sample_nodes = random.sample(list(nx_undirected.nodes()), min(10000, undirected_nodes))
        subgraph = nx_undirected.subgraph(sample_nodes)
        avg_clustering = nx.average_clustering(subgraph)
        print(f"     Approximate Avg Clustering:       {avg_clustering:.6f}")
    
    return {
        'directed_density': directed_density,
        'undirected_density': undirected_density,
        'avg_clustering': avg_clustering,
        'directed_nodes': directed_nodes,
        'directed_edges': directed_edges,
        'undirected_nodes': undirected_nodes,
        'undirected_edges': undirected_edges,
    }


def detect_corner_cases(rdf_graph: Graph, nx_directed: nx.DiGraph, degree_stats: dict) -> dict:
    """Detect corner cases and anomalies in the KG."""
    print("\n" + "=" * 80)
    print("⚠️  CORNER CASES & ANOMALIES DETECTION")
    print("=" * 80)
    
    corner_cases = {}
    in_degrees = degree_stats['in_degrees']
    out_degrees = degree_stats['out_degrees']
    
    # 1. Self-loops (subject = object)
    print("\n  🔄 Self-Loops (subject = object):")
    self_loops = [(s, p, o) for s, p, o in rdf_graph if str(s) == str(o)]
    corner_cases['self_loops'] = len(self_loops)
    print(f"     Count:                            {len(self_loops):,}")
    if self_loops:
        print(f"     Examples (first 3):")
        for s, p, o in self_loops[:3]:
            short_s = str(s).split("/")[-1][:40]
            short_p = str(p).split("/")[-1].split("#")[-1]
            print(f"       {short_s} --{short_p}--> SELF")
    
    # 2. Duplicate triples (exact same s, p, o)
    print("\n  📋 Duplicate Triples Check:")
    triple_set = set()
    duplicates = []
    for s, p, o in rdf_graph:
        triple_key = (str(s), str(p), str(o))
        if triple_key in triple_set:
            duplicates.append(triple_key)
        triple_set.add(triple_key)
    corner_cases['duplicates'] = len(duplicates)
    print(f"     Duplicate Triples:                {len(duplicates):,}")
    
    # 3. Blank nodes with no outgoing edges (orphan blank nodes)
    print("\n  🔲 Orphan Blank Nodes (BNodes with no outgoing edges):")
    bnode_nodes = [n for n, data in nx_directed.nodes(data=True) if data.get('is_bnode', False)]
    orphan_bnodes = [n for n in bnode_nodes if out_degrees.get(n, 0) == 0]
    corner_cases['orphan_bnodes'] = len(orphan_bnodes)
    print(f"     Count:                            {len(orphan_bnodes):,}")
    
    # 4. Literals as subjects (invalid in RDF but checking anyway)
    print("\n  📝 Literals as Subjects (should be 0 in valid RDF):")
    literal_subjects = sum(1 for s in rdf_graph.subjects() if isinstance(s, Literal))
    corner_cases['literal_subjects'] = literal_subjects
    print(f"     Count:                            {literal_subjects:,}")
    
    # 5. Very long literals (potential data quality issues)
    print("\n  📏 Very Long Literals (> 1000 characters):")
    long_literals = []
    for s, p, o in rdf_graph:
        if isinstance(o, Literal) and len(str(o)) > 1000:
            long_literals.append((str(s), str(p), len(str(o))))
    corner_cases['long_literals'] = len(long_literals)
    print(f"     Count:                            {len(long_literals):,}")
    if long_literals:
        print(f"     Examples (first 3):")
        for subj, pred, length in long_literals[:3]:
            short_s = subj.split("/")[-1][:30]
            short_p = pred.split("/")[-1].split("#")[-1][:20]
            print(f"       {short_s} --{short_p}--> [{length:,} chars]")
    
    # 6. Nodes with extremely high degree (potential hubs or errors)
    print("\n  🌟 Extreme Degree Nodes (>1000 total degree):")
    total_degrees = degree_stats['total_degrees']
    extreme_nodes = [(n, d) for n, d in total_degrees.items() if d > 1000]
    extreme_nodes.sort(key=lambda x: x[1], reverse=True)
    corner_cases['extreme_degree_nodes'] = len(extreme_nodes)
    print(f"     Count:                            {len(extreme_nodes):,}")
    if extreme_nodes:
        print(f"     Top 5:")
        for node, deg in extreme_nodes[:5]:
            short_node = node.split("/")[-1][:50] if "/" in node else node[:50]
            print(f"       [{deg:>6,}] {short_node}")
    
    # 7. Empty strings as literals
    print("\n  📭 Empty String Literals:")
    empty_literals = sum(1 for s, p, o in rdf_graph if isinstance(o, Literal) and str(o).strip() == "")
    corner_cases['empty_literals'] = empty_literals
    print(f"     Count:                            {empty_literals:,}")
    
    # 8. Untyped entities (no rdf:type)
    print("\n  ❓ Untyped URI Entities:")
    typed_entities = set(str(s) for s, p, o in rdf_graph.triples((None, RDF.type, None)))
    all_uri_subjects = set(str(s) for s in rdf_graph.subjects() if isinstance(s, URIRef))
    untyped_entities = all_uri_subjects - typed_entities
    corner_cases['untyped_entities'] = len(untyped_entities)
    print(f"     Count:                            {len(untyped_entities):,}")
    print(f"     Percentage:                       {100 * len(untyped_entities) / len(all_uri_subjects) if all_uri_subjects else 0:.2f}%")
    
    return corner_cases


def generate_summary_report(all_stats: dict):
    """Generate a final summary report."""
    print("\n" + "=" * 80)
    print("📋 SUMMARY REPORT")
    print("=" * 80)
    
    print(f"""
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                     KNOWLEDGE GRAPH STATISTICS                          │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ RDF Metrics                                                             │
  │   • Triples:              {all_stats['basic']['num_triples']:>12,}                              │
  │   • Unique Nodes:         {all_stats['basic']['num_nodes']:>12,}                              │
  │   • Unique Predicates:    {all_stats['basic']['num_predicates']:>12,}                              │
  │   • URI Nodes:            {all_stats['basic']['num_uri_nodes']:>12,}                              │
  │   • Literal Nodes:        {all_stats['basic']['num_literal_nodes']:>12,}                              │
  │   • Blank Nodes:          {all_stats['basic']['num_bnode_nodes']:>12,}                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Graph Structure                                                         │
  │   • Connected Components: {all_stats['components']['num_components']:>12,}                              │
  │   • Largest Component:    {all_stats['components']['largest_component_size']:>12,} nodes                        │
  │   • Graph Density:        {all_stats['density']['undirected_density']:>12.10f}                          │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Degree Statistics                                                       │
  │   • Average In-Degree:    {all_stats['degrees']['avg_in_degree']:>12.4f}                              │
  │   • Average Out-Degree:   {all_stats['degrees']['avg_out_degree']:>12.4f}                              │
  │   • Max In-Degree:        {all_stats['degrees']['max_in_degree']:>12,}                              │
  │   • Max Out-Degree:       {all_stats['degrees']['max_out_degree']:>12,}                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Structural Properties                                                   │
  │   • Leaf Nodes:           {all_stats['structural']['num_leaf_nodes']:>12,}                              │
  │   • Source Nodes:         {all_stats['structural']['num_source_nodes']:>12,}                              │
  │   • Sink Nodes:           {all_stats['structural']['num_sink_nodes']:>12,}                              │
  │   • Hub Nodes (top 1%):   {all_stats['structural']['num_hub_nodes']:>12,}                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Entity Types                                                            │
  │   • Unique Types:         {all_stats['entity_types']['num_entity_types']:>12,}                              │
  │   • Typed Entities:       {all_stats['entity_types']['num_typed_entities']:>12,}                              │
  │   • Multi-Typed:          {all_stats['entity_types']['num_multi_typed']:>12,}                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Corner Cases                                                            │
  │   • Self-Loops:           {all_stats['corner_cases']['self_loops']:>12,}                              │
  │   • Empty Literals:       {all_stats['corner_cases']['empty_literals']:>12,}                              │
  │   • Untyped Entities:     {all_stats['corner_cases']['untyped_entities']:>12,}                              │
  │   • Extreme Degree Nodes: {all_stats['corner_cases']['extreme_degree_nodes']:>12,}                              │
  └─────────────────────────────────────────────────────────────────────────┘
""")


def main(ttl_file: Optional[str] = None):
    """Main function to run KG analysis."""
    
    # Default file path
    if ttl_file is None:
        ttl_file = Path(__file__).parent / "data" / "kg" / "imdb_kg_cleaned.ttl"
    else:
        ttl_file = Path(ttl_file)
    
    print("=" * 80)
    print("🎬 KNOWLEDGE GRAPH STATISTICS ANALYZER")
    print("=" * 80)
    
    # Load the TTL file
    rdf_graph = load_single_ttl(ttl_file)
    
    # Convert to NetworkX graphs
    nx_directed = rdf_to_networkx_directed(rdf_graph)
    nx_undirected = rdf_to_networkx_undirected(rdf_graph)
    
    # Collect all statistics
    all_stats = {}
    
    # Basic RDF stats
    all_stats['basic'] = compute_basic_rdf_stats(rdf_graph)
    
    # Degree statistics
    all_stats['degrees'] = compute_degree_statistics(nx_directed)
    
    # Structural statistics
    all_stats['structural'] = compute_structural_statistics(nx_directed, all_stats['degrees'])
    
    # Connected components
    all_stats['components'] = compute_connected_components(nx_undirected, rdf_graph)
    
    # Predicate analysis
    all_stats['predicates'] = compute_predicate_analysis(rdf_graph)
    
    # Entity type analysis
    all_stats['entity_types'] = compute_entity_type_analysis(rdf_graph)
    
    # Density metrics
    all_stats['density'] = compute_graph_density_metrics(nx_directed, nx_undirected)
    
    # Corner cases
    all_stats['corner_cases'] = detect_corner_cases(rdf_graph, nx_directed, all_stats['degrees'])
    
    # Generate summary report
    generate_summary_report(all_stats)
    
    print("\n" + "=" * 80)
    print("✅ Analysis Complete!")
    print("=" * 80)
    
    return rdf_graph, nx_directed, nx_undirected, all_stats


if __name__ == "__main__":
    # Allow custom file path from command line
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()

