#!/usr/bin/env python3
"""
Modality Count for Movies

This script loops over the movies directory and evaluates the modality availability
for each movie, reporting results in an Excel file.

Modalities tracked:
- Text: name, abstract, description, reviewBody, caption, keywords, genre, 
        inLanguage, contentRating, alternateName, characterName, jobTitle, 
        currency, unitCode
- Images: ImageObject (type), thumbnail
- Videos: VideoObject (type)
- Audio: Soundtracks with YouTube links (from soundtrack_links.json)

Output:
- Excel file with per-movie modality counts
- Overall statistics (percentage of movies with each modality, average counts)
"""

import json
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
        Dictionary with counts for each property category
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


def count_audio_clips(json_file: Path) -> tuple[int, int]:
    """
    Count audio clips (soundtracks) with available YouTube links.
    
    Args:
        json_file: Path to the soundtrack_links.json file
        
    Returns:
        Tuple of (clips_with_links, total_soundtracks)
    """
    if not json_file.exists():
        return 0, 0
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            soundtracks = json.load(f)
    except Exception as e:
        print(f"  Warning: Error reading {json_file}: {e}")
        return 0, 0
    
    if not isinstance(soundtracks, list):
        return 0, 0
    
    total = len(soundtracks)
    with_links = 0
    
    for soundtrack in soundtracks:
        # Check if there's a best_match with a valid URL
        if isinstance(soundtrack, dict):
            best_match = soundtrack.get('best_match')
            if best_match and isinstance(best_match, dict):
                if best_match.get('url') or best_match.get('video_id'):
                    with_links += 1
    
    return with_links, total


def analyze_movie(movie_dir: Path) -> Optional[dict]:
    """
    Analyze a single movie directory for modality availability.
    
    Args:
        movie_dir: Path to the movie directory (e.g., data/movies/tt0120338)
        
    Returns:
        Dictionary with modality counts, or None if invalid
    """
    movie_id = movie_dir.name
    
    # Find the TTL file in movie_html directory
    ttl_file = movie_dir / "movie_html" / f"{movie_id}.ttl"
    
    # Find the soundtrack JSON file
    soundtrack_json = movie_dir / "movie_soundtrack" / "soundtrack_links.json"
    
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
    
    # Count audio clips
    audio_with_links, audio_total = count_audio_clips(soundtrack_json)
    
    return {
        'movie_id': movie_id,
        # Text
        'text_total': text_total,
        **{f'text_{prop}': text_counts[prop] for prop in TEXT_PROPERTIES},
        # Images
        'image_total': image_total,
        **{f'image_{prop}': image_counts[prop] for prop in IMAGE_PROPERTIES},
        # Videos
        'video_total': video_total,
        **{f'video_{prop}': video_counts[prop] for prop in VIDEO_PROPERTIES},
        # Audio
        'audio_clips_with_links': audio_with_links,
        'audio_soundtracks_total': audio_total,
        # Boolean flags for modality presence
        'has_text': text_total > 0,
        'has_images': image_total > 0,
        'has_videos': video_total > 0,
        'has_audio': audio_with_links > 0,
    }


def main():
    # Path to movies directory
    movies_dir = Path(__file__).parent / "data" / "movies"
    
    if not movies_dir.exists():
        print(f"Error: Movies directory not found: {movies_dir}")
        return
    
    print("=" * 70)
    print("MODALITY COUNT FOR MOVIES")
    print("=" * 70)
    
    # Find all movie directories (tt######### pattern)
    movie_dirs = sorted([
        d for d in movies_dir.iterdir()
        if d.is_dir() and d.name.startswith('tt') and d.name[2:].isdigit()
    ])
    
    print(f"\nFound {len(movie_dirs)} movie directories")
    print("-" * 70)
    
    # Analyze each movie
    results = []
    for i, movie_dir in enumerate(movie_dirs, 1):
        if i % 50 == 0 or i == len(movie_dirs):
            print(f"  Processing movie {i}/{len(movie_dirs)}: {movie_dir.name}")
        
        result = analyze_movie(movie_dir)
        if result:
            results.append(result)
    
    print(f"\nSuccessfully analyzed {len(results)} movies")
    print("-" * 70)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Calculate overall statistics
    total_movies = len(df)
    
    # Percentage of movies with each modality
    pct_with_text = (df['has_text'].sum() / total_movies) * 100
    pct_with_images = (df['has_images'].sum() / total_movies) * 100
    pct_with_videos = (df['has_videos'].sum() / total_movies) * 100
    pct_with_audio = (df['has_audio'].sum() / total_movies) * 100
    
    # Average counts per modality
    avg_text = df['text_total'].mean()
    avg_images = df['image_total'].mean()
    avg_videos = df['video_total'].mean()
    avg_audio = df['audio_clips_with_links'].mean()
    
    # Print overall statistics
    print("\n" + "=" * 70)
    print("OVERALL STATISTICS")
    print("=" * 70)
    
    print("\n📊 MODALITY COVERAGE (% of movies with modality)")
    print("-" * 50)
    print(f"  Text:   {pct_with_text:6.2f}% ({df['has_text'].sum():>4}/{total_movies} movies)")
    print(f"  Images: {pct_with_images:6.2f}% ({df['has_images'].sum():>4}/{total_movies} movies)")
    print(f"  Videos: {pct_with_videos:6.2f}% ({df['has_videos'].sum():>4}/{total_movies} movies)")
    print(f"  Audio:  {pct_with_audio:6.2f}% ({df['has_audio'].sum():>4}/{total_movies} movies)")
    
    print("\n📈 AVERAGE COUNT PER MOVIE")
    print("-" * 50)
    print(f"  Text elements:    {avg_text:8.2f}")
    print(f"  Image elements:   {avg_images:8.2f}")
    print(f"  Video elements:   {avg_videos:8.2f}")
    print(f"  Audio clips:      {avg_audio:8.2f}")
    
    # Detailed text property breakdown
    print("\n📝 TEXT PROPERTY BREAKDOWN (average per movie)")
    print("-" * 50)
    for prop in TEXT_PROPERTIES:
        col = f'text_{prop}'
        avg = df[col].mean()
        if avg > 0:
            print(f"  {prop:<20}: {avg:8.2f}")
    
    # Create summary DataFrame for overall stats
    summary_data = {
        'Metric': [
            'Total Movies Analyzed',
            '% with Text',
            '% with Images',
            '% with Videos',
            '% with Audio',
            'Avg Text Elements',
            'Avg Image Elements',
            'Avg Video Elements',
            'Avg Audio Clips',
        ],
        'Value': [
            total_movies,
            f"{pct_with_text:.2f}%",
            f"{pct_with_images:.2f}%",
            f"{pct_with_videos:.2f}%",
            f"{pct_with_audio:.2f}%",
            f"{avg_text:.2f}",
            f"{avg_images:.2f}",
            f"{avg_videos:.2f}",
            f"{avg_audio:.2f}",
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Prepare columns for Excel output
    # Reorder columns for better readability
    column_order = [
        'movie_id',
        'has_text', 'text_total',
        'has_images', 'image_total',
        'has_videos', 'video_total',
        'has_audio', 'audio_clips_with_links', 'audio_soundtracks_total',
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
    output_file = Path(__file__).parent / "modality_counts_movies.xlsx"
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Write summary sheet
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Write detailed per-movie data
        df_output.to_excel(writer, sheet_name='Per Movie Details', index=False)
        
        # Write property breakdown
        property_breakdown = []
        for prop in TEXT_PROPERTIES:
            col = f'text_{prop}'
            property_breakdown.append({
                'Category': 'Text',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Movie': df[col].mean(),
                'Movies with Property': (df[col] > 0).sum(),
                '% Movies with Property': ((df[col] > 0).sum() / total_movies) * 100
            })
        
        for prop in IMAGE_PROPERTIES:
            col = f'image_{prop}'
            property_breakdown.append({
                'Category': 'Image',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Movie': df[col].mean(),
                'Movies with Property': (df[col] > 0).sum(),
                '% Movies with Property': ((df[col] > 0).sum() / total_movies) * 100
            })
        
        for prop in VIDEO_PROPERTIES:
            col = f'video_{prop}'
            property_breakdown.append({
                'Category': 'Video',
                'Property': prop,
                'Total Count': df[col].sum(),
                'Average per Movie': df[col].mean(),
                'Movies with Property': (df[col] > 0).sum(),
                '% Movies with Property': ((df[col] > 0).sum() / total_movies) * 100
            })
        
        # Add audio breakdown
        property_breakdown.append({
            'Category': 'Audio',
            'Property': 'clips_with_links',
            'Total Count': df['audio_clips_with_links'].sum(),
            'Average per Movie': df['audio_clips_with_links'].mean(),
            'Movies with Property': (df['audio_clips_with_links'] > 0).sum(),
            '% Movies with Property': ((df['audio_clips_with_links'] > 0).sum() / total_movies) * 100
        })
        property_breakdown.append({
            'Category': 'Audio',
            'Property': 'soundtracks_total',
            'Total Count': df['audio_soundtracks_total'].sum(),
            'Average per Movie': df['audio_soundtracks_total'].mean(),
            'Movies with Property': (df['audio_soundtracks_total'] > 0).sum(),
            '% Movies with Property': ((df['audio_soundtracks_total'] > 0).sum() / total_movies) * 100
        })
        
        breakdown_df = pd.DataFrame(property_breakdown)
        breakdown_df.to_excel(writer, sheet_name='Property Breakdown', index=False)
    
    print(f"\n✅ Results saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()


