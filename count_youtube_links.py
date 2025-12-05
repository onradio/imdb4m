#!/usr/bin/env python3
"""
Script to count total YouTube links across all movie soundtrack_links.json files.
"""

import os
import json
import re
from pathlib import Path


def count_youtube_links(movies_dir: str) -> dict:
    """
    Walk through all movie directories and count YouTube links in soundtrack_links.json files.
    
    Args:
        movies_dir: Path to the movies directory
        
    Returns:
        Dictionary with statistics about found YouTube links
    """
    youtube_pattern = re.compile(r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+')
    
    total_youtube_links = 0
    movies_with_soundtracks = 0
    movies_processed = 0
    all_links = []
    errors = []
    
    movies_path = Path(movies_dir)
    
    # Iterate through all movie directories
    for movie_dir in sorted(movies_path.iterdir()):
        # Skip non-directories and non-movie folders (like 'actors')
        if not movie_dir.is_dir() or not movie_dir.name.startswith('tt'):
            continue
            
        movies_processed += 1
        soundtrack_json = movie_dir / 'movie_soundtrack' / 'soundtrack_links.json'
        
        if not soundtrack_json.exists():
            continue
            
        movies_with_soundtracks += 1
        
        try:
            with open(soundtrack_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Count YouTube links in this file
            for entry in data:
                # Check if best_match exists and has a url
                if 'best_match' in entry and entry['best_match'] is not None:
                    url = entry['best_match'].get('url', '')
                    if youtube_pattern.match(url):
                        total_youtube_links += 1
                        all_links.append({
                            'movie_id': movie_dir.name,
                            'url': url,
                            'title': entry.get('soundtrack', {}).get('title', 'Unknown')
                        })
                        
        except json.JSONDecodeError as e:
            errors.append(f"{soundtrack_json}: JSON decode error - {e}")
        except Exception as e:
            errors.append(f"{soundtrack_json}: {e}")
    
    return {
        'total_youtube_links': total_youtube_links,
        'movies_processed': movies_processed,
        'movies_with_soundtracks': movies_with_soundtracks,
        'unique_videos': len(set(link['url'] for link in all_links)),
        'errors': errors,
        'all_links': all_links
    }


def main():
    # Path to the movies directory
    movies_dir = Path(__file__).parent / 'data' / 'movies'
    
    print(f"Scanning movies directory: {movies_dir}")
    print("-" * 60)
    
    results = count_youtube_links(str(movies_dir))
    
    print(f"Total movies processed:        {results['movies_processed']}")
    print(f"Movies with soundtrack files:  {results['movies_with_soundtracks']}")
    print(f"Total YouTube links found:     {results['total_youtube_links']}")
    print(f"Unique YouTube videos:         {results['unique_videos']}")
    
    if results['errors']:
        print(f"\nErrors encountered: {len(results['errors'])}")
        for error in results['errors']:
            print(f"  - {error}")
    
    print("-" * 60)
    print(f"\n✓ Total YouTube links: {results['total_youtube_links']}")


if __name__ == '__main__':
    main()


