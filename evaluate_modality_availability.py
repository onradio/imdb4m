#!/usr/bin/env python3
"""
Script to evaluate modality availability for each movie in the dataset.

Modalities:
- Video: Trailer (schema:VideoObject linked via schema:trailer)
- Images: Image objects (schema:ImageObject linked via schema:image)
- Audio: Audio clips from soundtrack_links.json (entries with valid YouTube links)
- Text: Abstract/description and reviews (schema:abstract, schema:review)
- Literals: Budget, scores, dates (schema:productionBudget, schema:aggregateRating, schema:datePublished)

Output: Excel file with per-movie modality counts and overall statistics.
"""

import os
import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

import pandas as pd
from rdflib import Graph, Namespace, URIRef


# Define namespaces
SCHEMA = Namespace("http://schema.org/")


def parse_ttl_file(ttl_path: str) -> Dict[str, Any]:
    """
    Parse a TTL file and extract modality information.
    
    Returns:
        Dictionary with counts for each modality category.
    """
    result = {
        'has_video': False,
        'video_count': 0,
        'has_images': False,
        'image_count': 0,
        'has_abstract': False,
        'has_reviews': False,
        'review_count': 0,
        'has_budget': False,
        'has_scores': False,
        'score_count': 0,
        'has_dates': False,
        'date_count': 0,
    }
    
    if not os.path.exists(ttl_path):
        return result
    
    try:
        g = Graph()
        g.parse(ttl_path, format='turtle')
    except Exception as e:
        print(f"Error parsing {ttl_path}: {e}")
        return result
    
    # Find the main movie entity
    movie_uri = None
    for s in g.subjects(predicate=URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), 
                         object=SCHEMA.Movie):
        movie_uri = s
        break
    
    if not movie_uri:
        return result
    
    # Count images (schema:image pointing to ImageObjects)
    images = list(g.objects(subject=movie_uri, predicate=SCHEMA.image))
    result['image_count'] = len(images)
    result['has_images'] = len(images) > 0
    
    # Count videos/trailers (schema:trailer)
    trailers = list(g.objects(subject=movie_uri, predicate=SCHEMA.trailer))
    result['video_count'] = len(trailers)
    result['has_video'] = len(trailers) > 0
    
    # Check for abstract
    abstracts = list(g.objects(subject=movie_uri, predicate=SCHEMA.abstract))
    result['has_abstract'] = len(abstracts) > 0
    
    # Count reviews
    reviews = list(g.objects(subject=movie_uri, predicate=SCHEMA.review))
    result['review_count'] = len(reviews)
    result['has_reviews'] = len(reviews) > 0
    
    # Check for budget (productionBudget)
    budgets = list(g.objects(subject=movie_uri, predicate=SCHEMA.productionBudget))
    result['has_budget'] = len(budgets) > 0
    
    # Count aggregate ratings (scores)
    # Direct aggregateRating property
    ratings = list(g.objects(subject=movie_uri, predicate=SCHEMA.aggregateRating))
    result['score_count'] = len(ratings)
    result['has_scores'] = len(ratings) > 0
    
    # Check for date published
    dates = list(g.objects(subject=movie_uri, predicate=SCHEMA.datePublished))
    result['date_count'] = len(dates)
    result['has_dates'] = len(dates) > 0
    
    return result


def parse_soundtrack_json(json_path: str) -> Tuple[int, int]:
    """
    Parse soundtrack_links.json and count audio clips with valid YouTube links.
    
    Returns:
        Tuple of (total_soundtracks, soundtracks_with_clips)
    """
    if not os.path.exists(json_path):
        return 0, 0
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return 0, 0
    
    if not isinstance(data, list):
        return 0, 0
    
    total = len(data)
    with_clips = 0
    
    for entry in data:
        # Check if there's a best_match with a valid URL (YouTube link)
        if isinstance(entry, dict) and 'best_match' in entry:
            best_match = entry.get('best_match')
            if isinstance(best_match, dict) and best_match.get('url'):
                with_clips += 1
    
    return total, with_clips


def evaluate_movies(movies_dir: str) -> pd.DataFrame:
    """
    Evaluate modality availability for all movies in the directory.
    
    Returns:
        DataFrame with per-movie modality information.
    """
    movies_path = Path(movies_dir)
    records = []
    
    # Get all movie directories (those starting with 'tt')
    movie_dirs = sorted([d for d in movies_path.iterdir() 
                        if d.is_dir() and d.name.startswith('tt')])
    
    print(f"Found {len(movie_dirs)} movie directories")
    
    for i, movie_dir in enumerate(movie_dirs):
        movie_id = movie_dir.name
        
        if (i + 1) % 50 == 0:
            print(f"Processing movie {i + 1}/{len(movie_dirs)}: {movie_id}")
        
        # Path to TTL file
        ttl_path = movie_dir / 'movie_html' / f'{movie_id}.ttl'
        
        # Path to soundtrack JSON
        soundtrack_json_path = movie_dir / 'movie_soundtrack' / 'soundtrack_links.json'
        
        # Parse TTL file
        ttl_data = parse_ttl_file(str(ttl_path))
        
        # Parse soundtrack JSON
        total_soundtracks, soundtracks_with_clips = parse_soundtrack_json(str(soundtrack_json_path))
        
        # Calculate text count (abstract + reviews)
        text_count = (1 if ttl_data['has_abstract'] else 0) + ttl_data['review_count']
        has_text = ttl_data['has_abstract'] or ttl_data['has_reviews']
        
        # Calculate literal count (budget + scores + dates)
        literal_count = (1 if ttl_data['has_budget'] else 0) + ttl_data['score_count'] + ttl_data['date_count']
        has_literals = ttl_data['has_budget'] or ttl_data['has_scores'] or ttl_data['has_dates']
        
        record = {
            'movie_id': movie_id,
            # Video modality
            'has_video': ttl_data['has_video'],
            'video_count': ttl_data['video_count'],
            # Image modality
            'has_images': ttl_data['has_images'],
            'image_count': ttl_data['image_count'],
            # Audio modality
            'has_audio': soundtracks_with_clips > 0,
            'audio_count': soundtracks_with_clips,
            'total_soundtracks': total_soundtracks,
            # Text modality
            'has_text': has_text,
            'text_count': text_count,
            'has_abstract': ttl_data['has_abstract'],
            'review_count': ttl_data['review_count'],
            # Literal modality
            'has_literals': has_literals,
            'literal_count': literal_count,
            'has_budget': ttl_data['has_budget'],
            'has_scores': ttl_data['has_scores'],
            'score_count': ttl_data['score_count'],
            'has_dates': ttl_data['has_dates'],
        }
        
        records.append(record)
    
    return pd.DataFrame(records)


def calculate_overall_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate overall modality coverage statistics.
    
    Returns:
        DataFrame with overall statistics.
    """
    total_movies = len(df)
    
    stats = []
    
    # Video modality
    movies_with_video = df['has_video'].sum()
    stats.append({
        'Modality': 'Video (Trailer)',
        'Movies with Modality': movies_with_video,
        'Coverage (%)': round(movies_with_video / total_movies * 100, 2),
        'Total Elements': df['video_count'].sum(),
        'Avg Elements per Movie': round(df['video_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_video'], 'video_count'].mean(), 2) if movies_with_video > 0 else 0,
    })
    
    # Image modality
    movies_with_images = df['has_images'].sum()
    stats.append({
        'Modality': 'Images',
        'Movies with Modality': movies_with_images,
        'Coverage (%)': round(movies_with_images / total_movies * 100, 2),
        'Total Elements': df['image_count'].sum(),
        'Avg Elements per Movie': round(df['image_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_images'], 'image_count'].mean(), 2) if movies_with_images > 0 else 0,
    })
    
    # Audio modality
    movies_with_audio = df['has_audio'].sum()
    stats.append({
        'Modality': 'Audio Clips',
        'Movies with Modality': movies_with_audio,
        'Coverage (%)': round(movies_with_audio / total_movies * 100, 2),
        'Total Elements': df['audio_count'].sum(),
        'Avg Elements per Movie': round(df['audio_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_audio'], 'audio_count'].mean(), 2) if movies_with_audio > 0 else 0,
    })
    
    # Text modality
    movies_with_text = df['has_text'].sum()
    stats.append({
        'Modality': 'Text (Abstract + Reviews)',
        'Movies with Modality': movies_with_text,
        'Coverage (%)': round(movies_with_text / total_movies * 100, 2),
        'Total Elements': df['text_count'].sum(),
        'Avg Elements per Movie': round(df['text_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_text'], 'text_count'].mean(), 2) if movies_with_text > 0 else 0,
    })
    
    # Sub-category: Abstract
    movies_with_abstract = df['has_abstract'].sum()
    stats.append({
        'Modality': '  - Abstract/Description',
        'Movies with Modality': movies_with_abstract,
        'Coverage (%)': round(movies_with_abstract / total_movies * 100, 2),
        'Total Elements': movies_with_abstract,  # Abstract is always 1 per movie
        'Avg Elements per Movie': round(movies_with_abstract / total_movies, 2),
        'Avg Elements (when present)': 1.0,
    })
    
    # Sub-category: Reviews
    movies_with_reviews = (df['review_count'] > 0).sum()
    stats.append({
        'Modality': '  - Reviews',
        'Movies with Modality': movies_with_reviews,
        'Coverage (%)': round(movies_with_reviews / total_movies * 100, 2),
        'Total Elements': df['review_count'].sum(),
        'Avg Elements per Movie': round(df['review_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['review_count'] > 0, 'review_count'].mean(), 2) if movies_with_reviews > 0 else 0,
    })
    
    # Literal modality
    movies_with_literals = df['has_literals'].sum()
    stats.append({
        'Modality': 'Literals (Budget + Scores + Dates)',
        'Movies with Modality': movies_with_literals,
        'Coverage (%)': round(movies_with_literals / total_movies * 100, 2),
        'Total Elements': df['literal_count'].sum(),
        'Avg Elements per Movie': round(df['literal_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_literals'], 'literal_count'].mean(), 2) if movies_with_literals > 0 else 0,
    })
    
    # Sub-category: Budget
    movies_with_budget = df['has_budget'].sum()
    stats.append({
        'Modality': '  - Budget',
        'Movies with Modality': movies_with_budget,
        'Coverage (%)': round(movies_with_budget / total_movies * 100, 2),
        'Total Elements': movies_with_budget,
        'Avg Elements per Movie': round(movies_with_budget / total_movies, 2),
        'Avg Elements (when present)': 1.0,
    })
    
    # Sub-category: Scores
    movies_with_scores = df['has_scores'].sum()
    stats.append({
        'Modality': '  - Scores/Ratings',
        'Movies with Modality': movies_with_scores,
        'Coverage (%)': round(movies_with_scores / total_movies * 100, 2),
        'Total Elements': df['score_count'].sum(),
        'Avg Elements per Movie': round(df['score_count'].mean(), 2),
        'Avg Elements (when present)': round(df.loc[df['has_scores'], 'score_count'].mean(), 2) if movies_with_scores > 0 else 0,
    })
    
    # Sub-category: Dates
    movies_with_dates = df['has_dates'].sum()
    stats.append({
        'Modality': '  - Dates',
        'Movies with Modality': movies_with_dates,
        'Coverage (%)': round(movies_with_dates / total_movies * 100, 2),
        'Total Elements': df['has_dates'].sum(),
        'Avg Elements per Movie': round(df['has_dates'].sum() / total_movies, 2),
        'Avg Elements (when present)': 1.0,
    })
    
    return pd.DataFrame(stats)


def generate_report(movies_dir: str, output_file: str):
    """
    Generate the complete modality availability report.
    
    Args:
        movies_dir: Path to the movies directory
        output_file: Path to the output Excel file
    """
    print("Evaluating modality availability...")
    
    # Evaluate all movies
    df = evaluate_movies(movies_dir)
    
    print(f"\nProcessed {len(df)} movies")
    
    # Calculate overall statistics
    stats_df = calculate_overall_statistics(df)
    
    # Prepare detailed per-movie sheet
    movie_details = df[[
        'movie_id',
        'has_video', 'video_count',
        'has_images', 'image_count',
        'has_audio', 'audio_count', 'total_soundtracks',
        'has_text', 'text_count', 'has_abstract', 'review_count',
        'has_literals', 'literal_count', 'has_budget', 'has_scores', 'score_count', 'has_dates',
    ]].copy()
    
    # Add total modality count column
    movie_details['total_modalities'] = (
        movie_details['has_video'].astype(int) +
        movie_details['has_images'].astype(int) +
        movie_details['has_audio'].astype(int) +
        movie_details['has_text'].astype(int) +
        movie_details['has_literals'].astype(int)
    )
    
    # Rename columns for better readability
    movie_details.columns = [
        'Movie ID',
        'Has Video', 'Video Count',
        'Has Images', 'Image Count',
        'Has Audio', 'Audio Clips', 'Total Soundtracks',
        'Has Text', 'Text Count', 'Has Abstract', 'Review Count',
        'Has Literals', 'Literal Count', 'Has Budget', 'Has Scores', 'Score Count', 'Has Dates',
        'Total Modalities (out of 5)'
    ]
    
    # Create summary by modality count
    modality_distribution = df[['has_video', 'has_images', 'has_audio', 'has_text', 'has_literals']].astype(int).sum(axis=1)
    modality_dist_df = pd.DataFrame({
        'Total Modalities': range(6),
        'Number of Movies': [
            (modality_distribution == i).sum() for i in range(6)
        ],
        'Percentage (%)': [
            round((modality_distribution == i).sum() / len(df) * 100, 2) for i in range(6)
        ]
    })
    
    # Write to Excel
    print(f"\nWriting report to {output_file}...")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: Overall Statistics
        stats_df.to_excel(writer, sheet_name='Overall Statistics', index=False)
        
        # Sheet 2: Modality Distribution
        modality_dist_df.to_excel(writer, sheet_name='Modality Distribution', index=False)
        
        # Sheet 3: Per-Movie Details
        movie_details.to_excel(writer, sheet_name='Per-Movie Details', index=False)
        
        # Auto-adjust column widths
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print("\n" + "=" * 60)
    print("MODALITY AVAILABILITY REPORT SUMMARY")
    print("=" * 60)
    print(f"\nTotal movies analyzed: {len(df)}")
    print("\nOverall Coverage:")
    print(stats_df[['Modality', 'Coverage (%)', 'Avg Elements per Movie']].to_string(index=False))
    print("\nModality Distribution:")
    print(modality_dist_df.to_string(index=False))
    print(f"\nDetailed report saved to: {output_file}")


if __name__ == "__main__":
    # Path configuration
    MOVIES_DIR = "/home/ioannis/PycharmProjects/imdb4m/data/movies"
    OUTPUT_FILE = "/home/ioannis/PycharmProjects/imdb4m/modality_availability_report.xlsx"
    
    generate_report(MOVIES_DIR, OUTPUT_FILE)

