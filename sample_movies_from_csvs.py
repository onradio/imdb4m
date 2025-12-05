#!/usr/bin/env python3
"""
Sample 5 movies from each CSV file in the movie_seeds folder.
Ensures Titanic and Gladiator are included in the selection.
"""

import csv
import random
from pathlib import Path
from typing import List, Dict


def read_csv_file(csv_path: Path) -> List[Dict[str, str]]:
    """Read a CSV file and return list of dictionaries."""
    movies = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            movies.append(row)
    return movies


def find_movie(movies: List[Dict[str, str]], movie_id: str) -> Dict[str, str] | None:
    """Find a movie by its ID."""
    for movie in movies:
        if movie['movie_id'] == movie_id:
            return movie
    return None


def sample_movies(movies: List[Dict[str, str]], required_movies: List[Dict[str, str]], 
                  excluded_ids: set, n: int) -> List[Dict[str, str]]:
    """Sample n movies from the list, ensuring required movies are included and excluding duplicates."""
    # Filter out movies that are already selected (by movie_id)
    available_movies = [m for m in movies if m['movie_id'] not in excluded_ids]
    
    # Filter required movies to only include those not already selected
    new_required = [m for m in required_movies if m['movie_id'] not in excluded_ids]
    
    # Remove required movies from the pool to avoid duplicates
    pool = [m for m in available_movies if m not in new_required]
    
    # Calculate how many more we need
    needed = n - len(new_required)
    
    if needed <= 0:
        return new_required[:n]
    
    # Sample the remaining movies
    if len(pool) < needed:
        sampled = pool
    else:
        sampled = random.sample(pool, needed)
    
    # Combine required and sampled movies
    result = new_required + sampled
    
    # Shuffle to randomize order
    random.shuffle(result)
    
    return result


def main():
    # Set random seed for reproducibility (optional)
    random.seed(42)
    
    # Define CSV files
    csv_dir = Path('extractor/movie_seeds')
    csv_files = [
        csv_dir / 'Movie, Release date between 1980-01-01 and 1990-12-31, IMDb ratings between 7 and 10, Number of votes at least 100000 (Sorted by User rating Descending).csv',
        csv_dir / 'Movie, Release date between 1990-01-01 and 2000-12-31, IMDb ratings between 7 and 10, Number of votes at least 100000 (Sorted by User rating Descending).csv',
        csv_dir / 'Movie, Release date between 2000-01-01 and 2010-12-31, IMDb ratings between 7 and 10, Number of votes at least 100000 (Sorted by User rating Descending).csv',
        csv_dir / 'Movie, Release date between 2010-01-01 and 2020-12-31, IMDb ratings between 7 and 10, Number of votes at least 100000 (Sorted by User rating Descending).csv',
    ]
    
    # Movie IDs we need to include
    titanic_id = 'tt0120338'
    gladiator_id = 'tt0172495'
    
    all_sampled = []
    selected_ids = set()  # Track selected movie IDs to avoid duplicates
    
    print("Sampling movies from CSV files:\n")
    
    for csv_file in csv_files:
        print(f"Processing: {csv_file.name}")
        movies = read_csv_file(csv_file)
        
        # Find required movies in this file (only if not already selected)
        required = []
        titanic = find_movie(movies, titanic_id)
        gladiator = find_movie(movies, gladiator_id)
        
        if titanic and titanic_id not in selected_ids:
            required.append(titanic)
            print(f"  ✓ Found Titanic: {titanic['title']}")
        
        if gladiator and gladiator_id not in selected_ids:
            required.append(gladiator)
            print(f"  ✓ Found Gladiator: {gladiator['title']}")
        
        # Sample 5 movies (excluding already selected ones)
        sampled = sample_movies(movies, required, selected_ids, 5)
        
        # Update selected IDs
        for movie in sampled:
            selected_ids.add(movie['movie_id'])
        
        all_sampled.extend(sampled)
        
        print(f"  Selected {len(sampled)} movies:")
        for movie in sampled:
            marker = " [REQUIRED]" if movie in required else ""
            print(f"    - {movie['title']} ({movie['movie_id']}){marker}")
        print()
    
    # Verify required movies are included
    selected_movie_ids = {movie['movie_id'] for movie in all_sampled}
    titanic_included = titanic_id in selected_movie_ids
    gladiator_included = gladiator_id in selected_movie_ids
    
    print(f"\nTotal unique movies selected: {len(all_sampled)}")
    print(f"✓ Titanic included: {titanic_included}")
    print(f"✓ Gladiator included: {gladiator_included}")
    print("\n" + "="*80)
    print("COMPLETE LIST OF SELECTED MOVIES:")
    print("="*80)
    
    for i, movie in enumerate(all_sampled, 1):
        marker = ""
        if movie['movie_id'] == titanic_id:
            marker = " [TITANIC]"
        elif movie['movie_id'] == gladiator_id:
            marker = " [GLADIATOR]"
        print(f"{i:2d}. {movie['title']:50s} | {movie['movie_id']:12s} | Rating: {movie['rating']:4s}{marker}")
    
    # Save to a new CSV file
    output_file = csv_dir / 'sampled_movies.csv'
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        if all_sampled:
            writer = csv.DictWriter(f, fieldnames=all_sampled[0].keys())
            writer.writeheader()
            writer.writerows(all_sampled)
    
    print(f"\n✓ Results saved to: {output_file}")


if __name__ == '__main__':
    main()

