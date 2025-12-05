#!/usr/bin/env python3
"""
Copy movie directories for movies listed in sampled_movies.csv
to a new sampled_movies directory.
"""

import csv
import shutil
from pathlib import Path


def read_movie_ids(csv_path: Path) -> list[str]:
    """Read movie IDs from the CSV file."""
    movie_ids = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            movie_ids.append(row['movie_id'])
    return movie_ids


def copy_movie_directory(source_dir: Path, dest_dir: Path, movie_id: str) -> bool:
    """
    Copy a movie directory from source to destination.
    
    Returns:
        True if copied successfully, False if source doesn't exist
    """
    source_movie_dir = source_dir / movie_id
    dest_movie_dir = dest_dir / movie_id
    
    if not source_movie_dir.exists():
        print(f"  ⚠ Warning: {movie_id} directory not found in {source_dir}")
        return False
    
    # Copy the entire directory tree
    shutil.copytree(source_movie_dir, dest_movie_dir)
    print(f"  ✓ Copied {movie_id}")
    return True


def main():
    # Paths
    csv_path = Path('extractor/movie_seeds/sampled_movies.csv')
    source_movies_dir = Path('extractor/movies')
    dest_dir = Path('sampled_movies')
    
    # Read movie IDs from CSV
    print(f"Reading movie IDs from {csv_path}...")
    movie_ids = read_movie_ids(csv_path)
    print(f"Found {len(movie_ids)} movie IDs\n")
    
    # Create destination directory
    if dest_dir.exists():
        print(f"Directory {dest_dir} already exists. Removing it...")
        shutil.rmtree(dest_dir)
    
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created directory: {dest_dir}\n")
    
    # Copy each movie directory
    print("Copying movie directories...")
    copied_count = 0
    missing_count = 0
    
    for movie_id in movie_ids:
        if copy_movie_directory(source_movies_dir, dest_dir, movie_id):
            copied_count += 1
        else:
            missing_count += 1
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total movies: {len(movie_ids)}")
    print(f"  Successfully copied: {copied_count}")
    print(f"  Missing: {missing_count}")
    print(f"  Destination: {dest_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()






