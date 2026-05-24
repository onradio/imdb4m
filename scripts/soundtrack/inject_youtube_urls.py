#!/usr/bin/env python3
"""
Inject YouTube URLs into soundtrack TTL files.

This script reads the soundtrack_links.json file containing YouTube matches
and injects the URLs into the corresponding TTL file at the MusicRecording level.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse


def load_soundtrack_links(json_path: Path) -> Dict[str, str]:
    """
    Load soundtrack links from JSON file.
    
    Args:
        json_path: Path to soundtrack_links.json
        
    Returns:
        Dictionary mapping track titles to YouTube URLs
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Build a mapping from soundtrack title to YouTube URL
    title_to_url = {}
    
    for item in data:
        soundtrack = item.get('soundtrack', {})
        title = soundtrack.get('title', '').strip()
        
        best_match = item.get('best_match')
        if best_match and title:
            url = best_match.get('url', '')
            if url:
                title_to_url[title] = url
    
    return title_to_url


def normalize_title(title: str) -> str:
    """Normalize title for comparison (lowercase, strip whitespace)."""
    return title.lower().strip()


def find_recording_blocks(ttl_content: str) -> List[Tuple[int, int, str]]:
    """
    Find all MusicRecording blocks in the TTL content.
    
    Returns:
        List of tuples (start_pos, end_pos, title) for each recording block
    """
    blocks = []
    
    # Pattern to match a MusicRecording block
    # Matches from "    [" to "    ]," or "    ] ."
    pattern = r'(    \[\s*\n\s*a schema:MusicRecording\s*;.*?(?:    \],|    \] \.))'
    
    matches = re.finditer(pattern, ttl_content, re.DOTALL)
    
    for match in matches:
        block_text = match.group(1)
        start_pos = match.start()
        end_pos = match.end()
        
        # Extract the title from this block
        title_match = re.search(r'schema:name\s+"([^"]+)"', block_text)
        if title_match:
            title = title_match.group(1)
            # Unescape the title
            title = title.replace('\\"', '"').replace('\\\\', '\\')
            blocks.append((start_pos, end_pos, title))
    
    return blocks


def inject_url_into_block(block_text: str, url: str) -> str:
    """
    Inject a schema:url triple into a MusicRecording block.
    
    Args:
        block_text: The text of the MusicRecording block
        url: The YouTube URL to inject
        
    Returns:
        Modified block text with URL injected
    """
    # Check if URL already exists
    if 'schema:url' in block_text:
        # URL already exists, don't modify
        return block_text
    
    # Find the position to inject the URL
    # We want to add it after the last property but before the closing bracket
    
    # Find if there's a recordingOf block
    recordingof_pattern = r'(schema:recordingOf\s*\[.*?\]\s*)(;|\s*(?=\],|\] \.))'
    recordingof_match = re.search(recordingof_pattern, block_text, re.DOTALL)
    
    if recordingof_match:
        # If there's a recordingOf, add URL after it
        # Need to add semicolon after recordingOf if not present
        before = block_text[:recordingof_match.end()]
        after = block_text[recordingof_match.end():]
        
        # Check if we need to add a semicolon after recordingOf
        if not before.rstrip().endswith(';'):
            before = before.rstrip() + ' ;'
        
        # Add the URL line
        url_line = f'\n        schema:url "{url}"'
        
        return before + url_line + after
    
    else:
        # No recordingOf block, add URL as last property before closing bracket
        # Find the last property (ends with ; or nothing before the closing bracket)
        
        # Find the position right before the closing bracket
        closing_pattern = r'(\s*)(    \],|    \] \.)'
        closing_match = re.search(closing_pattern, block_text)
        
        if closing_match:
            before = block_text[:closing_match.start()]
            closing = block_text[closing_match.start():]
            
            # Remove trailing whitespace and check for semicolon
            before = before.rstrip()
            if not before.endswith(';'):
                before += ' ;'
            
            # Add the URL line
            url_line = f'\n        schema:url "{url}"'
            
            return before + url_line + '\n' + closing.lstrip()
    
    return block_text


def inject_youtube_urls(
    ttl_path: Path,
    json_path: Path,
    output_path: Optional[Path] = None,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Inject YouTube URLs from JSON into TTL file.
    
    Args:
        ttl_path: Path to the soundtrack TTL file
        json_path: Path to the soundtrack_links.json file
        output_path: Optional output path (defaults to overwriting ttl_path)
        dry_run: If True, don't write the file
        
    Returns:
        Tuple of (total_tracks, injected_count)
    """
    # Load the URL mappings
    title_to_url = load_soundtrack_links(json_path)
    
    if not title_to_url:
        print(f"No YouTube URLs found in {json_path}")
        return (0, 0)
    
    print(f"Loaded {len(title_to_url)} YouTube URLs from JSON")
    
    # Read the TTL file
    with open(ttl_path, 'r', encoding='utf-8') as f:
        ttl_content = f.read()
    
    # Find all MusicRecording blocks
    blocks = find_recording_blocks(ttl_content)
    print(f"Found {len(blocks)} MusicRecording blocks in TTL")
    
    if not blocks:
        print("No MusicRecording blocks found in TTL file")
        return (0, 0)
    
    # Create a normalized title lookup
    normalized_lookup = {normalize_title(title): url for title, url in title_to_url.items()}
    
    # Track which URLs from JSON were successfully matched
    urls_to_inject = set(normalized_lookup.keys())
    urls_injected = set()
    urls_already_present = set()
    
    # Process blocks in reverse order to maintain positions
    modified_content = ttl_content
    injected_count = 0
    
    for start_pos, end_pos, title in reversed(blocks):
        normalized = normalize_title(title)
        
        if normalized in normalized_lookup:
            url = normalized_lookup[normalized]
            
            # Extract the block text
            block_text = modified_content[start_pos:end_pos]
            
            # Check if URL already exists
            if 'schema:url' in block_text:
                print(f"  ⏭️  Skipping '{title}': URL already exists")
                urls_already_present.add(normalized)
                continue
            
            # Inject the URL
            new_block = inject_url_into_block(block_text, url)
            
            # Replace in content
            modified_content = modified_content[:start_pos] + new_block + modified_content[end_pos:]
            
            print(f"  ✓ Injected URL for '{title}'")
            injected_count += 1
            urls_injected.add(normalized)
        else:
            print(f"  ⚠️  No URL found for '{title}'")
    
    # Validate that all URLs from JSON were either injected or already present
    urls_processed = urls_injected | urls_already_present
    unmatched_urls = urls_to_inject - urls_processed
    
    if unmatched_urls:
        # Find the original titles for the unmatched URLs
        unmatched_titles = [
            title for title, url in title_to_url.items() 
            if normalize_title(title) in unmatched_urls
        ]
        
        error_msg = (
            f"\n✗ ERROR: Failed to inject all URLs from JSON!\n"
            f"  URLs in JSON: {len(title_to_url)}\n"
            f"  URLs injected: {len(urls_injected)}\n"
            f"  URLs already present: {len(urls_already_present)}\n"
            f"  URLs unmatched: {len(unmatched_urls)}\n"
            f"\n  Unmatched tracks from JSON:\n"
        )
        for title in unmatched_titles:
            error_msg += f"    - '{title}'\n"
        
        error_msg += (
            f"\n  This indicates a mismatch between the JSON and TTL files.\n"
            f"  Each URL in the JSON must correspond to a distinct MusicRecording in the TTL.\n"
        )
        
        raise ValueError(error_msg)
    
    # Write the modified content
    if not dry_run:
        output = output_path if output_path else ttl_path
        with open(output, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print(f"\n✓ Updated TTL saved to: {output}")
        print(f"✓ All {len(title_to_url)} URLs from JSON successfully processed")
    else:
        print("\n[DRY RUN] No files were modified")
        print("\n--- Preview of modified content ---")
        print(modified_content[:2000])
        if len(modified_content) > 2000:
            print(f"\n... ({len(modified_content)} total characters)")
    
    return (len(blocks), injected_count)


def process_movie_folder(
    movie_folder: Path,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Process a single movie folder.
    
    Args:
        movie_folder: Path to movie folder (e.g., data/subset/tt0120338)
        dry_run: If True, don't write files
        
    Returns:
        Tuple of (total_tracks, injected_count)
    """
    soundtrack_folder = movie_folder / 'movie_soundtrack'
    
    # Find the TTL file
    ttl_files = list(soundtrack_folder.glob('*_soundtrack.ttl'))
    if not ttl_files:
        print(f"⚠️  No soundtrack TTL file found in {soundtrack_folder}")
        return (0, 0)
    
    ttl_path = ttl_files[0]
    
    # Find the JSON file
    json_path = soundtrack_folder / 'soundtrack_links.json'
    if not json_path.exists():
        print(f"⚠️  No soundtrack_links.json found in {soundtrack_folder}")
        return (0, 0)
    
    print(f"\n{'='*70}")
    print(f"Processing: {movie_folder.name}")
    print('='*70)
    print(f"TTL file: {ttl_path.name}")
    print(f"JSON file: {json_path.name}")
    
    return inject_youtube_urls(ttl_path, json_path, dry_run=dry_run)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Inject YouTube URLs into soundtrack TTL files',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--movie-folder',
        type=Path,
        help='Process a single movie folder (e.g., data/subset/tt0120338)'
    )
    group.add_argument(
        '--dataset-root',
        type=Path,
        help='Process all movies in the dataset root (e.g., data/subset)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without modifying files'
    )
    
    args = parser.parse_args()
    
    if args.movie_folder:
        # Process single movie
        movie_folder = args.movie_folder.resolve()
        if not movie_folder.exists():
            print(f"Error: Movie folder not found: {movie_folder}")
            return 1
        
        total, injected = process_movie_folder(movie_folder, dry_run=args.dry_run)
        
        print(f"\n{'='*70}")
        print("SUMMARY")
        print('='*70)
        print(f"Total tracks: {total}")
        print(f"URLs injected: {injected}")
        print('='*70)
        
        return 0
    
    elif args.dataset_root:
        # Process all movies
        dataset_root = args.dataset_root.resolve()
        if not dataset_root.exists():
            print(f"Error: Dataset root not found: {dataset_root}")
            return 1
        
        # Find all movie folders
        movie_folders = sorted([d for d in dataset_root.iterdir() if d.is_dir() and d.name.startswith('tt')])
        
        if not movie_folders:
            print(f"No movie folders found in {dataset_root}")
            return 1
        
        print(f"Found {len(movie_folders)} movie folders")
        
        total_tracks = 0
        total_injected = 0
        processed_movies = 0
        
        for movie_folder in movie_folders:
            try:
                tracks, injected = process_movie_folder(movie_folder, dry_run=args.dry_run)
                if tracks > 0:
                    total_tracks += tracks
                    total_injected += injected
                    processed_movies += 1
            except Exception as e:
                print(f"✗ Error processing {movie_folder.name}: {e}")
        
        print(f"\n{'='*70}")
        print("FINAL SUMMARY")
        print('='*70)
        print(f"Movies processed: {processed_movies}/{len(movie_folders)}")
        print(f"Total tracks: {total_tracks}")
        print(f"Total URLs injected: {total_injected}")
        if total_tracks > 0:
            print(f"Success rate: {total_injected/total_tracks*100:.1f}%")
        print('='*70)
        
        return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
