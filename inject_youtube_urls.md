# Inject YouTube URLs - Examples

## Basic Usage

### Single Movie (Dry Run)
```bash
python inject_youtube_urls.py --movie-folder data/subset/tt0120338 --dry-run
```

### Single Movie
```bash
python inject_youtube_urls.py --movie-folder data/subset/tt0120338
```

### All Movies
```bash
python inject_youtube_urls.py --dataset-root data/subset
```

## Python Usage

```python
from pathlib import Path
from inject_youtube_urls import inject_youtube_urls

ttl_path = Path("data/subset/tt0120338/movie_soundtrack/tt0120338_soundtrack.ttl")
json_path = Path("data/subset/tt0120338/movie_soundtrack/soundtrack_links.json")

total_tracks, injected_count = inject_youtube_urls(ttl_path, json_path)
print(f"Injected {injected_count}/{total_tracks} URLs")
```

## Complete Workflow

```bash
# Step 1: Extract YouTube links
python extract_soundtrack_links.py \
  --dataset-root data/subset \
  --youtube-api-key $YOUTUBE_API_KEY \
  --gemini-api-key $GEMINI_API_KEY

# Step 2: Inject URLs into TTL files
python inject_youtube_urls.py --dataset-root data/subset
```

## Before/After Example

**Before:**
```turtle
[
    a schema:MusicRecording ;
    schema:name "My Heart Will Go On" ;
    schema:byArtist <https://www.imdb.com/name/nm0001144/> ;
    schema:recordingOf [ ... ]
],
```

**After:**
```turtle
[
    a schema:MusicRecording ;
    schema:name "My Heart Will Go On" ;
    schema:byArtist <https://www.imdb.com/name/nm0001144/> ;
    schema:recordingOf [ ... ] ;
    schema:url "https://www.youtube.com/watch?v=DNyKDI9pn0Q"
],
```
