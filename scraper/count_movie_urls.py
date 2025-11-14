import re
from pathlib import Path

def count_movie_urls(file_path):
    """Count movie URLs in an HTML file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return set(), []
    
    # Find all IMDb movie URLs - try multiple patterns
    patterns = [
        r'https?://(?:www\.)?imdb\.com/title/(tt\d{7,8})',
        r'/title/(tt\d{7,8})',
        r'href="[^"]*title/(tt\d{7,8})',
        r'href=\'[^\']*title/(tt\d{7,8})',
    ]
    
    all_matches = []
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        all_matches.extend(matches)
    
    # Get unique movie IDs
    unique_movie_ids = set(all_matches)
    
    return unique_movie_ids, all_matches

# Compare both files
file1 = Path("Leonardo DiCaprio - IMDb.html")
file2 = Path("movies/actors/nm0000138/actor.html")

print("=" * 60)
print("COMPARING MOVIE URL COUNTS")
print("=" * 60)

# Count in first file
print(f"\n1. Analyzing: {file1}")
unique1, all1 = count_movie_urls(file1)
print(f"   Total movie URL occurrences: {len(all1)}")
print(f"   Unique movie IDs: {len(unique1)}")

# Count in second file
print(f"\n2. Analyzing: {file2}")
unique2, all2 = count_movie_urls(file2)
print(f"   Total movie URL occurrences: {len(all2)}")
print(f"   Unique movie IDs: {len(unique2)}")

# Compare
print("\n" + "=" * 60)
print("COMPARISON RESULTS")
print("=" * 60)

print(f"\nDifference in total occurrences: {len(all1) - len(all2)}")
print(f"Difference in unique movie IDs: {len(unique1) - len(unique2)}")

if len(unique1) > len(unique2):
    print(f"\n✓ '{file1.name}' has {len(unique1) - len(unique2)} MORE unique movie IDs")
    only_in_file1 = unique1 - unique2
    print(f"  Movie IDs only in '{file1.name}': {len(only_in_file1)}")
elif len(unique2) > len(unique1):
    print(f"\n✓ '{file2.name}' has {len(unique2) - len(unique1)} MORE unique movie IDs")
    only_in_file2 = unique2 - unique1
    print(f"  Movie IDs only in '{file2.name}': {len(only_in_file2)}")
else:
    print(f"\n✓ Both files have the same number of unique movie IDs")

# Show movies only in one file
if len(unique1) != len(unique2):
    only_in_file1 = unique1 - unique2
    only_in_file2 = unique2 - unique1
    
    if only_in_file1:
        print(f"\nMovie IDs only in '{file1.name}' (first 10):")
        for i, movie_id in enumerate(sorted(only_in_file1)[:10], 1):
            print(f"  {i}. {movie_id}")
    
    if only_in_file2:
        print(f"\nMovie IDs only in '{file2.name}' (first 10):")
        for i, movie_id in enumerate(sorted(only_in_file2)[:10], 1):
            print(f"  {i}. {movie_id}")

