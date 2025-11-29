#!/usr/bin/env python3
"""
Validate soundtrack TTL files and generate statistics in an Excel file.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd
from rdflib import Graph, Namespace, URIRef, RDF
from rdflib.exceptions import ParserError

# Define namespaces
SCHEMA = Namespace("http://schema.org/")


@dataclass
class SoundtrackStats:
    """Statistics for a single movie soundtrack."""
    movie_id: str
    movie_uri: str
    ttl_file: str
    is_valid: bool = True
    error_message: str = ""
    
    # Triple counts
    total_triples: int = 0
    
    # Track counts
    num_tracks: int = 0
    
    # Person counts
    num_performers: int = 0
    num_producers: int = 0
    num_composers: int = 0
    num_lyricists: int = 0
    num_authors: int = 0
    num_unique_persons: int = 0
    
    # File stats
    file_size_bytes: int = 0
    file_lines: int = 0
    
    # Lists for detailed info
    track_names: List[str] = field(default_factory=list)
    performer_names: List[str] = field(default_factory=list)
    composer_names: List[str] = field(default_factory=list)


def validate_and_analyze_ttl(ttl_path: Path) -> SoundtrackStats:
    """
    Validate a TTL file and extract statistics.
    
    Args:
        ttl_path: Path to the TTL file
        
    Returns:
        SoundtrackStats object with validation results and statistics
    """
    movie_id = ttl_path.stem.replace('_soundtrack', '')
    
    stats = SoundtrackStats(
        movie_id=movie_id,
        movie_uri=f"https://www.imdb.com/title/{movie_id}/",
        ttl_file=str(ttl_path)
    )
    
    # File stats
    stats.file_size_bytes = ttl_path.stat().st_size
    with open(ttl_path, 'r', encoding='utf-8') as f:
        stats.file_lines = sum(1 for _ in f)
    
    # Try to parse with rdflib
    g = Graph()
    try:
        g.parse(ttl_path, format='turtle')
        stats.is_valid = True
    except ParserError as e:
        stats.is_valid = False
        stats.error_message = str(e)[:200]
        return stats
    except Exception as e:
        stats.is_valid = False
        stats.error_message = f"Unexpected error: {str(e)[:200]}"
        return stats
    
    # Count total triples
    stats.total_triples = len(g)
    
    # Count MusicRecordings (tracks)
    music_recordings = list(g.subjects(RDF.type, SCHEMA.MusicRecording))
    stats.num_tracks = len(music_recordings)
    
    # Get track names
    for recording in music_recordings:
        names = list(g.objects(recording, SCHEMA.name))
        for name in names:
            stats.track_names.append(str(name))
    
    # Count performers (byArtist)
    performers = set()
    for recording in music_recordings:
        for artist in g.objects(recording, SCHEMA.byArtist):
            performers.add(artist)
    stats.num_performers = len(performers)
    
    # Get performer names
    for performer in performers:
        names = list(g.objects(performer, SCHEMA.name))
        for name in names:
            stats.performer_names.append(str(name))
    
    # Count producers
    producers = set()
    for recording in music_recordings:
        for producer in g.objects(recording, SCHEMA.producer):
            producers.add(producer)
    stats.num_producers = len(producers)
    
    # Get MusicCompositions
    music_compositions = list(g.subjects(RDF.type, SCHEMA.MusicComposition))
    
    # Count composers
    composers = set()
    for composition in music_compositions:
        for composer in g.objects(composition, SCHEMA.composer):
            composers.add(composer)
    stats.num_composers = len(composers)
    
    # Get composer names
    for composer in composers:
        names = list(g.objects(composer, SCHEMA.name))
        for name in names:
            stats.composer_names.append(str(name))
    
    # Count lyricists
    lyricists = set()
    for composition in music_compositions:
        for lyricist in g.objects(composition, SCHEMA.lyricist):
            lyricists.add(lyricist)
    stats.num_lyricists = len(lyricists)
    
    # Count authors
    authors = set()
    for composition in music_compositions:
        for author in g.objects(composition, SCHEMA.author):
            authors.add(author)
    stats.num_authors = len(authors)
    
    # Count unique persons
    persons = list(g.subjects(RDF.type, SCHEMA.Person))
    stats.num_unique_persons = len(persons)
    
    return stats


def process_all_ttl_files(base_dir: Path) -> List[SoundtrackStats]:
    """
    Process all TTL files and collect statistics.
    
    Args:
        base_dir: Base directory containing movie folders
        
    Returns:
        List of SoundtrackStats objects
    """
    ttl_files = list(base_dir.glob('**/movie_soundtrack/*_soundtrack.ttl'))
    
    print(f"Found {len(ttl_files)} TTL files to validate")
    print()
    
    all_stats = []
    valid_count = 0
    invalid_count = 0
    
    for i, ttl_path in enumerate(ttl_files):
        stats = validate_and_analyze_ttl(ttl_path)
        all_stats.append(stats)
        
        if stats.is_valid:
            valid_count += 1
        else:
            invalid_count += 1
            print(f"INVALID: {ttl_path.name}: {stats.error_message}")
        
        if (i + 1) % 50 == 0:
            print(f"Progress: {i + 1}/{len(ttl_files)} files processed...")
    
    print()
    print(f"Validation complete: {valid_count} valid, {invalid_count} invalid")
    
    return all_stats


def generate_excel_report(stats_list: List[SoundtrackStats], output_path: Path):
    """
    Generate an Excel file with statistics.
    
    Args:
        stats_list: List of SoundtrackStats objects
        output_path: Path for the output Excel file
    """
    # Create main dataframe
    data = []
    for stats in stats_list:
        row = {
            'Movie ID': stats.movie_id,
            'Movie URI': stats.movie_uri,
            'TTL File': Path(stats.ttl_file).name,
            'Valid': stats.is_valid,
            'Error': stats.error_message if not stats.is_valid else '',
            'Total Triples': stats.total_triples,
            'Num Tracks': stats.num_tracks,
            'Num Performers': stats.num_performers,
            'Num Producers': stats.num_producers,
            'Num Composers': stats.num_composers,
            'Num Lyricists': stats.num_lyricists,
            'Num Authors': stats.num_authors,
            'Num Unique Persons': stats.num_unique_persons,
            'File Size (bytes)': stats.file_size_bytes,
            'File Lines': stats.file_lines,
            'Track Names': '; '.join(stats.track_names[:10]) + ('...' if len(stats.track_names) > 10 else ''),
            'Performer Names': '; '.join(stats.performer_names[:10]) + ('...' if len(stats.performer_names) > 10 else ''),
            'Composer Names': '; '.join(stats.composer_names[:10]) + ('...' if len(stats.composer_names) > 10 else ''),
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Sort by Movie ID
    df = df.sort_values('Movie ID')
    
    # Create summary statistics
    summary_data = {
        'Metric': [
            'Total Files',
            'Valid Files',
            'Invalid Files',
            'Total Triples',
            'Total Tracks',
            'Total Performers',
            'Total Producers',
            'Total Composers',
            'Total Lyricists',
            'Total Authors',
            'Total Unique Persons',
            'Average Triples per File',
            'Average Tracks per File',
            'Average Performers per File',
            'Average Composers per File',
            'Max Tracks in Single File',
            'Max Performers in Single File',
            'Max Composers in Single File',
            'Total File Size (KB)',
            'Average File Size (bytes)',
        ],
        'Value': [
            len(stats_list),
            df['Valid'].sum(),
            len(stats_list) - df['Valid'].sum(),
            df['Total Triples'].sum(),
            df['Num Tracks'].sum(),
            df['Num Performers'].sum(),
            df['Num Producers'].sum(),
            df['Num Composers'].sum(),
            df['Num Lyricists'].sum(),
            df['Num Authors'].sum(),
            df['Num Unique Persons'].sum(),
            round(df['Total Triples'].mean(), 2),
            round(df['Num Tracks'].mean(), 2),
            round(df['Num Performers'].mean(), 2),
            round(df['Num Composers'].mean(), 2),
            df['Num Tracks'].max(),
            df['Num Performers'].max(),
            df['Num Composers'].max(),
            round(df['File Size (bytes)'].sum() / 1024, 2),
            round(df['File Size (bytes)'].mean(), 2),
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Write to Excel with multiple sheets
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Summary sheet first
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Detailed data sheet
        df.to_excel(writer, sheet_name='Movie Details', index=False)
        
        # Invalid files sheet (if any)
        invalid_df = df[~df['Valid']]
        if len(invalid_df) > 0:
            invalid_df.to_excel(writer, sheet_name='Invalid Files', index=False)
        
        # Top movies by track count
        top_tracks_df = df.nlargest(20, 'Num Tracks')[['Movie ID', 'Num Tracks', 'Track Names']]
        top_tracks_df.to_excel(writer, sheet_name='Top 20 by Tracks', index=False)
        
        # Top movies by performer count
        top_performers_df = df.nlargest(20, 'Num Performers')[['Movie ID', 'Num Performers', 'Performer Names']]
        top_performers_df.to_excel(writer, sheet_name='Top 20 by Performers', index=False)
    
    print(f"\nExcel report saved to: {output_path}")


def print_summary(stats_list: List[SoundtrackStats]):
    """Print a summary of statistics to console."""
    valid_stats = [s for s in stats_list if s.is_valid]
    
    total_triples = sum(s.total_triples for s in valid_stats)
    total_tracks = sum(s.num_tracks for s in valid_stats)
    total_performers = sum(s.num_performers for s in valid_stats)
    total_producers = sum(s.num_producers for s in valid_stats)
    total_composers = sum(s.num_composers for s in valid_stats)
    total_lyricists = sum(s.num_lyricists for s in valid_stats)
    total_authors = sum(s.num_authors for s in valid_stats)
    total_persons = sum(s.num_unique_persons for s in valid_stats)
    total_size = sum(s.file_size_bytes for s in valid_stats)
    
    print()
    print("=" * 60)
    print("STATISTICS SUMMARY")
    print("=" * 60)
    print()
    print(f"{'Files processed:':<30} {len(stats_list)}")
    print(f"{'Valid files:':<30} {len(valid_stats)}")
    print(f"{'Invalid files:':<30} {len(stats_list) - len(valid_stats)}")
    print()
    print("TRIPLE COUNTS:")
    print("-" * 40)
    print(f"{'Total triples:':<30} {total_triples:,}")
    print(f"{'Average triples per file:':<30} {total_triples / len(valid_stats):,.1f}")
    print()
    print("ENTITY COUNTS:")
    print("-" * 40)
    print(f"{'Total tracks:':<30} {total_tracks:,}")
    print(f"{'Total performers:':<30} {total_performers:,}")
    print(f"{'Total producers:':<30} {total_producers:,}")
    print(f"{'Total composers:':<30} {total_composers:,}")
    print(f"{'Total lyricists:':<30} {total_lyricists:,}")
    print(f"{'Total authors:':<30} {total_authors:,}")
    print(f"{'Total unique persons:':<30} {total_persons:,}")
    print()
    print("AVERAGES PER FILE:")
    print("-" * 40)
    print(f"{'Avg tracks:':<30} {total_tracks / len(valid_stats):.1f}")
    print(f"{'Avg performers:':<30} {total_performers / len(valid_stats):.1f}")
    print(f"{'Avg composers:':<30} {total_composers / len(valid_stats):.1f}")
    print()
    print("FILE STATS:")
    print("-" * 40)
    print(f"{'Total file size:':<30} {total_size / 1024:.1f} KB")
    print(f"{'Average file size:':<30} {total_size / len(valid_stats):.0f} bytes")
    print()
    
    # Find extremes
    if valid_stats:
        max_tracks = max(valid_stats, key=lambda s: s.num_tracks)
        max_performers = max(valid_stats, key=lambda s: s.num_performers)
        max_triples = max(valid_stats, key=lambda s: s.total_triples)
        
        print("NOTABLE FILES:")
        print("-" * 40)
        print(f"Most tracks:     {max_tracks.movie_id} ({max_tracks.num_tracks} tracks)")
        print(f"Most performers: {max_performers.movie_id} ({max_performers.num_performers} performers)")
        print(f"Most triples:    {max_triples.movie_id} ({max_triples.total_triples} triples)")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Validate soundtrack TTL files and generate statistics'
    )
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path('/home/ioannis/PycharmProjects/imdb4m/scraper/movies'),
        help='Base directory containing movie folders'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('/home/ioannis/PycharmProjects/imdb4m/soundtrack_stats.xlsx'),
        help='Output Excel file path'
    )
    
    args = parser.parse_args()
    
    # Process all files
    all_stats = process_all_ttl_files(args.input_dir)
    
    # Print summary to console
    print_summary(all_stats)
    
    # Generate Excel report
    generate_excel_report(all_stats, args.output)


if __name__ == '__main__':
    main()

