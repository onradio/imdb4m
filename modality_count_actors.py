#!/usr/bin/env python3
"""
Modality Count for Actors

This script loops over the actors directory and evaluates the modality availability
for each actor, reporting results in an Excel file.

Modalities tracked:
- Text: name, abstract, description, reviewBody, caption, keywords, genre, 
        inLanguage, contentRating, alternateName, characterName, jobTitle, 
        currency, unitCode
- Images: ImageObject (type), thumbnail
- Videos: VideoObject (type)

Note: Audio modality is excluded as we don't have audio clip information for actors.

Output:
- Excel file with per-actor modality counts
- Overall statistics (percentage of actors with each modality, average counts)
"""

import re
from pathlib import Path
from collections import defaultdict
from typing import Optional

try:
    import pandas as pd
except ImportError:
    print("Please install pandas: pip install pandas")
    exit(1)

try:
    import openpyxl
except ImportError:
    print("Please install openpyxl: pip install openpyxl")
    exit(1)


# Define property categories
TEXT_PROPERTIES = [
    'name', 'abstract', 'description', 'reviewBody', 'caption',
    'keywords', 'genre', 'inLanguage', 'contentRating', 'alternateName',
    'characterName', 'jobTitle', 'currency', 'unitCode'
]

IMAGE_PROPERTIES = ['ImageObject', 'thumbnail']

VIDEO_PROPERTIES = ['VideoObject']


def count_ttl_properties(ttl_file: Path) -> dict:
    """
    Count text, image, and video properties in a TTL file.
    
    Args:
        ttl_file: Path to the TTL file
        
    Returns:
        Dictionary with counts for each property
    """
    counts = defaultdict(int)
    
    if not ttl_file.exists():
        return counts
    
    # Pattern to match schema properties/types (handles both schema: and schema1:)
    property_pattern = re.compile(r'schema1?:(\w+)')
    
    try:
        with open(ttl_file, 'r', encoding='utf-8') as f:
            for line in f:
                matches = property_pattern.findall(line)
                for prop in matches:
                    counts[prop] += 1
    except Exception as e:
        print(f"  Warning: Error reading {ttl_file}: {e}")
    
    return counts


def analyze_actor(actor_dir: Path) -> Optional[dict]:
    """
    Analyze a single actor directory for modality availability.
    
    Args:
        actor_dir: Path to the actor directory (e.g., data/movies/actors/nm0000138)
        
    Returns:
        Dictionary with modality counts, or None if invalid
    """
    actor_id = actor_dir.name
    
    # Find the TTL file
    ttl_file = actor_dir / f"{actor_id}.ttl"
    
    if not ttl_file.exists():
        return None
    
    # Count TTL properties
    ttl_counts = count_ttl_properties(ttl_file)
    
    # Calculate text counts
    text_counts = {prop: ttl_counts.get(prop, 0) for prop in TEXT_PROPERTIES}
    text_total = sum(text_counts.values())
    
    # Calculate image counts
    image_counts = {prop: ttl_counts.get(prop, 0) for prop in IMAGE_PROPERTIES}
    image_total = sum(image_counts.values())
    
    # Calculate video counts
    video_counts = {prop: ttl_counts.get(prop, 0) for prop in VIDEO_PROPERTIES}
    video_total = sum(video_counts.values())
    
    return {
        'actor_id': actor_id,
        # Text
        'text_total': text_total,
        **{f'text_{prop}': text_counts[prop] for prop in TEXT_PROPERTIES},
        # Images
        'image_total': image_total,
        **{f'image_{prop}': image_counts[prop] for prop in IMAGE_PROPERTIES},
        # Videos
        'video_total': video_total,
        **{f'video_{prop}': video_counts[prop] for prop in VIDEO_PROPERTIES},
        # Boolean flags for modality presence
        'has_text': text_total > 0,
        'has_images': image_total > 0,
        'has_videos': video_total > 0,
    }


def main():
    # Path to actors directory
    actors_dir = Path(__file__).parent / "data" / "movies" / "actors"
    
    if not actors_dir.exists():
        print(f"Error: Actors directory not found: {actors_dir}")
        return
    
    print("=" * 70)
    print("MODALITY COUNT FOR ACTORS")
    print("=" * 70)
    
    # Find all actor directories (nm######### pattern)
    actor_dirs = sorted([
        d for d in actors_dir.iterdir()
        if d.is_dir() and d.name.startswith('nm') and d.name[2:].isdigit()
    ])
    
    print(f"\nFound {len(actor_dirs)} actor directories")
    print("-" * 70)
    
    # Analyze each actor
    results = []
    for i, actor_dir in enumerate(actor_dirs, 1):
        if i % 100 == 0 or i == len(actor_dirs):
            print(f"  Processing actor {i}/{len(actor_dirs)}: {actor_dir.name}")
        
        result = analyze_actor(actor_dir)
        if result:
            results.append(result)
    
    print(f"\nSuccessfully analyzed {len(results)} actors")
    print("-" * 70)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Calculate overall statistics
    total_actors = len(df)
    
    # Percentage of actors with each modality
    pct_with_text = (df['has_text'].sum() / total_actors) * 100
    pct_with_images = (df['has_images'].sum() / total_actors) * 100
    pct_with_videos = (df['has_videos'].sum() / total_actors) * 100
    
    # Average counts per modality
    avg_text = df['text_total'].mean()
    avg_images = df['image_total'].mean()
    avg_videos = df['video_total'].mean()
    
    # Print overall statistics
    print("\n" + "=" * 70)
    print("OVERALL STATISTICS")
    print("=" * 70)
    
    print("\n📊 MODALITY COVERAGE (% of actors with modality)")
    print("-" * 50)
    print(f"  Text:   {pct_with_text:6.2f}% ({df['has_text'].sum():>4}/{total_actors} actors)")
    print(f"  Images: {pct_with_images:6.2f}% ({df['has_images'].sum():>4}/{total_actors} actors)")
    print(f"  Videos: {pct_with_videos:6.2f}% ({df['has_videos'].sum():>4}/{total_actors} actors)")
    
    print("\n📈 AVERAGE COUNT PER ACTOR")
    print("-" * 50)
    print(f"  Text elements:    {avg_text:8.2f}")
    print(f"  Image elements:   {avg_images:8.2f}")
    print(f"  Video elements:   {avg_videos:8.2f}")
    
    # Detailed text property breakdown
    print("\n📝 TEXT PROPERTY BREAKDOWN (average per actor)")
    print("-" * 50)
    for prop in TEXT_PROPERTIES:
        col = f'text_{prop}'
        avg = df[col].mean()
        if avg > 0:
            print(f"  {prop:<20}: {avg:8.2f}")
    
    # Create summary DataFrame for overall stats
    summary_data = {
        'Metric': [
            'Total Actors Analyzed',
            '% with Text',
            '% with Images',
            '% with Videos',
            'Avg Text Elements',
            'Avg Image Elements',
            'Avg Video Elements',
        ],
        'Value': [
            total_actors,
            f"{pct_with_text:.2f}%",
            f"{pct_with_images:.2f}%",
            f"{pct_with_videos:.2f}%",
            f"{avg_text:.2f}",
            f"{avg_images:.2f}",
            f"{avg_videos:.2f}",
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Prepare columns for Excel output
    # Reorder columns for better readability
    column_order = [
        'actor_id',
        'has_text', 'text_total',
        'has_images', 'image_total',
        'has_videos', 'video_total',
    ]
    
    # Add detailed text property columns
    for prop in TEXT_PROPERTIES:
        column_order.append(f'text_{prop}')
    
    # Add detailed image property columns
    for prop in IMAGE_PROPERTIES:
        column_order.append(f'image_{prop}')
    
    # Add detailed video property columns
    for prop in VIDEO_PROPERTIES:
        column_order.append(f'video_{prop}')
    
    df_output = df[column_order]
    
    # Save to Excel
    output_file = Path(__file__).parent / "modality_counts_actors.xlsx"
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Write summary sheet
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Write detailed per-actor data
        df_output.to_excel(writer, sheet_name='Per Actor Details', index=False)
        
        # Write property breakdown
        property_breakdown = []
        for prop in TEXT_PROPERTIES:
            col = f'text_{prop}'
            property_breakdown.append({
                'Category': 'Text',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Actor': df[col].mean(),
                'Actors with Property': (df[col] > 0).sum(),
                '% Actors with Property': ((df[col] > 0).sum() / total_actors) * 100
            })
        
        for prop in IMAGE_PROPERTIES:
            col = f'image_{prop}'
            property_breakdown.append({
                'Category': 'Image',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Actor': df[col].mean(),
                'Actors with Property': (df[col] > 0).sum(),
                '% Actors with Property': ((df[col] > 0).sum() / total_actors) * 100
            })
        
        for prop in VIDEO_PROPERTIES:
            col = f'video_{prop}'
            property_breakdown.append({
                'Category': 'Video',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Actor': df[col].mean(),
                'Actors with Property': (df[col] > 0).sum(),
                '% Actors with Property': ((df[col] > 0).sum() / total_actors) * 100
            })
        
        breakdown_df = pd.DataFrame(property_breakdown)
        breakdown_df.to_excel(writer, sheet_name='Property Breakdown', index=False)
    
    print(f"\n✅ Results saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()


