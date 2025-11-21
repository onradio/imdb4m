#!/usr/bin/env python3
"""
Knowledge Graph Comparison Tool

This script compares two RDF knowledge graphs in Turtle syntax and reports:
- Missing triples from ground truth in the tested graph
- Extra triples in the tested graph (not in ground truth)
- Accuracy/coverage metrics
"""

import sys
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import RDF
from typing import Set, Tuple, List
from collections import defaultdict


def normalize_term(term, graph: Graph):
    """Normalize a single RDF term (subject, predicate, or object)."""
    if isinstance(term, BNode):
        # For blank nodes, we'll use a placeholder - but this means
        # blank node structures need special handling
        return BNode("_blank")
    elif isinstance(term, URIRef):
        # Ensure we get the full expanded URI, not the abbreviated form
        # Try to get the namespace and local name, then reconstruct
        try:
            # Get the full URI string
            uri_str = str(term)
            # If it looks like it might be abbreviated, try to expand it
            if ':' in uri_str and not uri_str.startswith('http'):
                # Try to expand using the graph's namespace manager
                try:
                    expanded = graph.namespace_manager.expand_curie(uri_str)
                    if expanded:
                        return URIRef(expanded)
                except:
                    pass
            return URIRef(uri_str)
        except:
            return URIRef(str(term))
    elif isinstance(term, Literal):
        # Normalize literals - compare value and datatype
        # Convert numeric literals to a canonical form
        value = str(term)
        datatype = term.datatype
        lang = term.language
        
        # Normalize numeric values (e.g., "200000000.0" vs "200000000")
        if datatype and 'decimal' in str(datatype):
            try:
                # Try to normalize decimal representation
                float_val = float(value)
                if float_val.is_integer():
                    value = str(int(float_val))
                else:
                    value = str(float_val)
            except:
                pass
        
        return Literal(value, datatype=datatype, lang=lang)
    else:
        return term


def normalize_triple(triple: Tuple, graph: Graph) -> Tuple:
    """
    Normalize a triple by expanding prefixes and handling blank nodes.
    For comparison purposes, we convert blank nodes to a canonical form.
    """
    s, p, o = triple
    
    s = normalize_term(s, graph)
    p = normalize_term(p, graph)
    o = normalize_term(o, graph)
    
    return (s, p, o)


def load_graph(file_path: str) -> Graph:
    """Load a Turtle file into an RDF graph."""
    graph = Graph()
    try:
        graph.parse(file_path, format="turtle")
        print(f"✓ Loaded {file_path}: {len(graph)} triples")
        return graph
    except Exception as e:
        print(f"✗ Error loading {file_path}: {e}")
        sys.exit(1)


def compare_graphs(ground_truth: Graph, tested: Graph) -> dict:
    """
    Compare two RDF graphs and return detailed comparison results.
    
    Returns:
        Dictionary with comparison results including:
        - missing_triples: triples in ground truth but not in tested
        - extra_triples: triples in tested but not in ground truth
        - common_triples: triples in both graphs
        - metrics: various accuracy/coverage metrics
    """
    # Get all triples from both graphs
    gt_triples = set(ground_truth)
    test_triples = set(tested)
    
    # Normalize triples for comparison
    # Note: Blank nodes require special handling - we'll compare them separately
    gt_normalized = {normalize_triple(t, ground_truth) for t in gt_triples}
    test_normalized = {normalize_triple(t, tested) for t in test_triples}
    
    # Find differences
    missing_triples = gt_normalized - test_normalized
    extra_triples = test_normalized - gt_normalized
    common_triples = gt_normalized & test_normalized
    
    # Map back to original triples for reporting
    # Create a mapping from normalized to original
    gt_normalized_to_original = {normalize_triple(t, ground_truth): t for t in gt_triples}
    test_normalized_to_original = {normalize_triple(t, tested): t for t in test_triples}
    
    missing_original = [gt_normalized_to_original.get(t) for t in missing_triples if t in gt_normalized_to_original]
    extra_original = [test_normalized_to_original.get(t) for t in extra_triples if t in test_normalized_to_original]
    
    # Calculate metrics
    total_gt = len(gt_normalized)
    total_test = len(test_normalized)
    total_common = len(common_triples)
    
    # Precision: how many of the tested triples are correct
    precision = total_common / total_test if total_test > 0 else 0.0
    
    # Recall: how many of the ground truth triples are found
    recall = total_common / total_gt if total_gt > 0 else 0.0
    
    # F1 Score: harmonic mean of precision and recall
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Coverage: same as recall
    coverage = recall
    
    # Accuracy: percentage of correct triples
    accuracy = total_common / max(total_gt, total_test) if max(total_gt, total_test) > 0 else 0.0
    
    # Jaccard similarity
    union_size = len(gt_normalized | test_normalized)
    jaccard = total_common / union_size if union_size > 0 else 0.0
    
    metrics = {
        "total_ground_truth_triples": total_gt,
        "total_tested_triples": total_test,
        "common_triples": total_common,
        "missing_triples_count": len(missing_triples),
        "extra_triples_count": len(extra_triples),
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
        "coverage": coverage,
        "accuracy": accuracy,
        "jaccard_similarity": jaccard
    }
    
    return {
        "missing_triples": missing_original,
        "extra_triples": extra_original,
        "common_triples": [gt_normalized_to_original.get(t) for t in common_triples if t in gt_normalized_to_original],
        "metrics": metrics
    }


def format_triple(triple: Tuple, graph: Graph) -> str:
    """Format a triple for display."""
    s, p, o = triple
    
    def format_term(term):
        if isinstance(term, URIRef):
            # Try to use qname if possible
            try:
                return graph.qname(term)
            except:
                return str(term)
        elif isinstance(term, Literal):
            if term.language:
                return f'"{term}"@{term.language}'
            elif term.datatype:
                return f'"{term}"^^<{term.datatype}>'
            else:
                return f'"{term}"'
        elif isinstance(term, BNode):
            return f"_:{term}"
        else:
            return str(term)
    
    return f"{format_term(s)} {format_term(p)} {format_term(o)} ."


def group_triples_by_subject(triples: List[Tuple]) -> dict:
    """Group triples by subject for better readability."""
    grouped = defaultdict(list)
    for triple in triples:
        if triple:
            grouped[triple[0]].append(triple)
    return grouped


def print_report(ground_truth_path: str, tested_path: str, results: dict):
    """Print a detailed comparison report."""
    print("\n" + "=" * 80)
    print("KNOWLEDGE GRAPH COMPARISON REPORT")
    print("=" * 80)
    print(f"\nGround Truth: {ground_truth_path}")
    print(f"Tested Graph: {tested_path}")
    
    metrics = results["metrics"]
    print("\n" + "-" * 80)
    print("METRICS SUMMARY")
    print("-" * 80)
    print(f"Total Ground Truth Triples:     {metrics['total_ground_truth_triples']}")
    print(f"Total Tested Triples:           {metrics['total_tested_triples']}")
    print(f"Common Triples (Correct):       {metrics['common_triples']}")
    print(f"Missing Triples (False Neg):    {metrics['missing_triples_count']}")
    print(f"Extra Triples (False Pos):      {metrics['extra_triples_count']}")
    print()
    print(f"Precision:                      {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)")
    print(f"Recall:                         {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)")
    print(f"F1 Score:                       {metrics['f1_score']:.4f}")
    print(f"Coverage:                       {metrics['coverage']:.4f} ({metrics['coverage']*100:.2f}%)")
    print(f"Accuracy:                       {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
    print(f"Jaccard Similarity:             {metrics['jaccard_similarity']:.4f}")
    
    # Load graphs for formatting
    gt_graph = load_graph(ground_truth_path)
    test_graph = load_graph(tested_path)
    
    # Missing triples
    if results["missing_triples"]:
        print("\n" + "-" * 80)
        print(f"MISSING TRIPLES ({len(results['missing_triples'])} triples from ground truth not found in tested graph)")
        print("-" * 80)
        grouped = group_triples_by_subject(results["missing_triples"])
        for subject, triples in sorted(grouped.items(), key=lambda x: str(x[0])):
            print(f"\nSubject: {format_triple((subject, None, None), gt_graph).split()[0]}")
            for triple in triples:
                if triple:
                    print(f"  {format_triple(triple, gt_graph)}")
    
    # Extra triples
    if results["extra_triples"]:
        print("\n" + "-" * 80)
        print(f"EXTRA TRIPLES ({len(results['extra_triples'])} triples in tested graph not in ground truth)")
        print("-" * 80)
        grouped = group_triples_by_subject(results["extra_triples"])
        for subject, triples in sorted(grouped.items(), key=lambda x: str(x[0])):
            print(f"\nSubject: {format_triple((subject, None, None), test_graph).split()[0]}")
            for triple in triples:
                if triple:
                    print(f"  {format_triple(triple, test_graph)}")
    
    print("\n" + "=" * 80)


def main():
    """Main function to run the comparison."""
    if len(sys.argv) == 3:
        ground_truth_path = sys.argv[1]
        tested_path = sys.argv[2]
    else:
        # Default to the example files
        ground_truth_path = "data/example_titanic_clean.ttl"
        tested_path = "data/example_titanic_generated.ttl"
        print("Using default files:")
        print(f"  Ground Truth: {ground_truth_path}")
        print(f"  Tested: {tested_path}")
        print()
    
    # Load graphs
    print("Loading knowledge graphs...")
    ground_truth = load_graph(ground_truth_path)
    tested = load_graph(tested_path)
    
    # Compare graphs
    print("\nComparing graphs...")
    results = compare_graphs(ground_truth, tested)
    
    # Print report
    print_report(ground_truth_path, tested_path, results)


if __name__ == "__main__":
    main()

