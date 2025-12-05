#!/usr/bin/env python3
"""
Count the number of text, image, and video properties in the IMDB Knowledge Graph.

Text properties: name, abstract, description, reviewBody, caption, keywords, 
                 genre, inLanguage, contentRating, alternateName, characterName, 
                 jobTitle, currency, unitCode

Image properties: ImageObject (type), thumbnail

Video properties: VideoObject (type)
"""

import re
from pathlib import Path
from collections import defaultdict


def count_kg_properties(ttl_file: str) -> dict:
    """
    Count occurrences of text, image, and video properties in a TTL file.
    
    Args:
        ttl_file: Path to the TTL file
        
    Returns:
        Dictionary with counts for each property and category totals
    """
    
    # Define property categories
    text_properties = [
        'name', 'abstract', 'description', 'reviewBody', 'caption', 
        'keywords', 'genre', 'inLanguage', 'contentRating', 'alternateName',
        'characterName', 'jobTitle', 'currency', 'unitCode'
    ]
    
    # ImageObject is a type (used with "a schema:ImageObject"), thumbnail is a property
    image_properties = ['ImageObject', 'thumbnail']
    
    # VideoObject is a type (used with "a schema:VideoObject")
    video_properties = ['VideoObject']
    
    # Initialize counters
    counts = defaultdict(int)
    
    # Build regex pattern for schema properties and types
    # Handles both schema: and schema1: prefixes
    property_pattern = re.compile(r'schema1?:(\w+)')
    
    print(f"Reading file: {ttl_file}")
    print("-" * 60)
    
    # Read and process the file
    file_path = Path(ttl_file)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {ttl_file}")
    
    line_count = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_count += 1
            if line_count % 500000 == 0:
                print(f"  Processed {line_count:,} lines...")
            
            # Find all schema properties/types in the line
            matches = property_pattern.findall(line)
            for prop in matches:
                counts[prop] += 1
    
    print(f"  Total lines processed: {line_count:,}")
    print("-" * 60)
    
    # Calculate category totals
    text_total = sum(counts[prop] for prop in text_properties)
    image_total = sum(counts[prop] for prop in image_properties)
    video_total = sum(counts[prop] for prop in video_properties)
    
    # Prepare results
    results = {
        'text': {
            'properties': {prop: counts[prop] for prop in text_properties},
            'total': text_total
        },
        'images': {
            'properties': {prop: counts[prop] for prop in image_properties},
            'total': image_total
        },
        'videos': {
            'properties': {prop: counts[prop] for prop in video_properties},
            'total': video_total
        },
        'all_properties': dict(counts)
    }
    
    return results


def print_results(results: dict):
    """Pretty print the results."""
    
    print("\n" + "=" * 60)
    print("IMDB KNOWLEDGE GRAPH PROPERTY COUNTS")
    print("=" * 60)
    
    # Text properties
    print("\n📝 TEXT PROPERTIES")
    print("-" * 40)
    for prop, count in sorted(results['text']['properties'].items(), 
                               key=lambda x: -x[1]):
        if count > 0:
            print(f"  schema:{prop:<20} {count:>10,}")
    print("-" * 40)
    print(f"  {'TOTAL TEXT:':<20} {results['text']['total']:>10,}")
    
    # Image properties
    print("\n🖼️  IMAGE PROPERTIES")
    print("-" * 40)
    for prop, count in sorted(results['images']['properties'].items(), 
                               key=lambda x: -x[1]):
        if count > 0:
            print(f"  schema:{prop:<20} {count:>10,}")
    print("-" * 40)
    print(f"  {'TOTAL IMAGES:':<20} {results['images']['total']:>10,}")
    
    # Video properties
    print("\n🎬 VIDEO PROPERTIES")
    print("-" * 40)
    for prop, count in sorted(results['videos']['properties'].items(), 
                               key=lambda x: -x[1]):
        if count > 0:
            print(f"  schema:{prop:<20} {count:>10,}")
    print("-" * 40)
    print(f"  {'TOTAL VIDEOS:':<20} {results['videos']['total']:>10,}")
    
    # Grand total
    grand_total = (results['text']['total'] + 
                   results['images']['total'] + 
                   results['videos']['total'])
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Text properties:    {results['text']['total']:>10,}")
    print(f"  Image properties:   {results['images']['total']:>10,}")
    print(f"  Video properties:   {results['videos']['total']:>10,}")
    print("-" * 40)
    print(f"  GRAND TOTAL:        {grand_total:>10,}")
    print("=" * 60)


def main():
    # Path to the KG file
    kg_file = Path(__file__).parent / "data" / "kg" / "imdb_kg_cleaned.ttl"
    
    # Count properties
    results = count_kg_properties(str(kg_file))
    
    # Print results
    print_results(results)
    
    # Also print all unique properties found (for reference)
    print("\n📊 ALL UNIQUE PROPERTIES FOUND (top 30 by count):")
    print("-" * 40)
    sorted_props = sorted(results['all_properties'].items(), 
                          key=lambda x: -x[1])[:30]
    for prop, count in sorted_props:
        print(f"  schema:{prop:<20} {count:>10,}")


if __name__ == "__main__":
    main()
