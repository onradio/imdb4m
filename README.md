# imdb4m - Music Linker
The IMDB Multimodal Knowledge Graph (IMDB4M) - Music Linker Module

An intelligent pipeline that retrieves the most relevant YouTube video URLs for movie soundtracks using IMDb metadata, YouTube search, and LLM-powered matching.

## Features

🎵 **Smart Metadata Parsing** - Extracts structured data from IMDb soundtrack pages  
🔍 **YouTube Integration** - Searches and fetches video details, descriptions, and comments  
🤖 **LLM-Powered Matching** - Uses Google's Gemini 2.5 Flash to analyze and select the best match  
📊 **Batch Processing** - Process multiple soundtracks in parallel  
💾 **Export Results** - Save results to JSON or CSV formats  
🎯 **High Accuracy** - Leverages video metadata, descriptions, and user comments for precise matching

## How It Works

1. **Parse Metadata**: Converts IMDb soundtrack text or local TTL files into structured `SoundtrackMetadata` objects
2. **Search YouTube**: Queries YouTube API with optimized search terms (title + performer + movie)
3. **Enrich Data**: Fetches video descriptions, statistics, and top comments
4. **LLM Analysis**: Gemini analyzes all candidates considering:
   - Title and performer match
   - Video description relevance
   - User comments validation
   - Popularity metrics
   - Authenticity indicators
5. **Select Best Match**: Returns the highest confidence match with detailed reasoning

## Installation

```bash
# Clone the repository
git clone https://github.com/onradio/imdb4m.git
cd imdb4m

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.template .env
# Edit .env and add your API keys
```

## API Keys Required

### YouTube Data API v3
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials (API Key)
5. Add to `.env` as `YOUTUBE_API_KEY`

### Google AI (Gemini) API
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create an API key
3. Add to `.env` as `GEMINI_API_KEY`

## Quick Start

```python
from linker import MusicLinker, SoundtrackParser, Config, setup_logging

# Setup
setup_logging('INFO')
config = Config()
config.validate()

# Option A: Parse IMDb soundtrack text
soundtrack_text = """My Heart Will Go On
Music by James Horner
Lyrics by Will Jennings
Performed by Céline Dion"""

soundtracks = SoundtrackParser.parse_soundtrack_text(
    soundtrack_text,
    movie_title="Titanic"
)

# Option B: Parse from local TTL (data/subset/<IMDB_ID>)
from pathlib import Path
from linker import SoundtrackParser

soundtracks = SoundtrackParser.parse_soundtrack_ttl(
  subset_root="data/subset",
  imdb_id="tt0405159",
)

# Initialize linker
linker = MusicLinker(
    youtube_api_key=config.youtube_api_key,
    gemini_api_key=config.gemini_api_key
)

# Find matches
results = linker.find_matches_batch(soundtracks)

# Access results
for result in results:
    if result.best_match:
        print(f"{result.soundtrack.title}: {result.best_match.url}")
        print(f"Confidence: {result.match_score.confidence:.2%}")
```

## Usage Example

Run the provided example script:

```bash
python example.py

# Optionally override the IMDb ID used for TTL parsing
IMDB_ID=tt0405159 python example.py
```

This will:
- Prefer reading soundtrack TTL from `data/subset/<IMDB_ID>`
- Fall back to the built-in Titanic text example if TTL is missing
- Search YouTube for each song
- Use Gemini to find the best matches
- Save results to `output/results.json` and `output/results.csv`

## Project Structure

```
imdb4m/
├── linker/
│   ├── __init__.py           # Package exports
│   ├── models.py             # Pydantic data models
│   ├── parser.py             # IMDb soundtrack parser
│   ├── youtube_client.py     # YouTube API client
│   ├── gemini_matcher.py     # Gemini LLM matcher
│   ├── music_linker.py       # Main pipeline orchestrator
│   └── utils.py              # Config and utilities
├── example.py                # Example usage script
├── requirements.txt          # Python dependencies
├── .env.template             # Environment variables template
└── README.md                 # This file
```

## Configuration

All settings can be configured via environment variables in `.env`:

```bash
# API Keys
YOUTUBE_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here

# Search Settings
MAX_SEARCH_RESULTS=10          # Max YouTube results per song
MAX_COMMENTS_PER_VIDEO=20      # Max comments to fetch per video
USE_COMMENTS=true              # Whether to use comments in matching

# LLM Settings
GEMINI_MODEL=gemini-2.0-flash-exp

# Processing
MAX_WORKERS=3                  # Parallel processing threads

# Logging
LOG_LEVEL=INFO
```

## Advanced Usage

### Using Individual Components

```python
from linker import YouTubeClient, GeminiMatcher, SoundtrackMetadata

# Direct YouTube search
youtube = YouTubeClient(api_key="your_key")
videos = youtube.search_videos("My Heart Will Go On Celine Dion")

# Fetch comments
videos_with_comments = youtube.enrich_videos_with_comments(videos)

# LLM matching
matcher = GeminiMatcher(api_key="your_gemini_key")
soundtrack = SoundtrackMetadata(
    title="My Heart Will Go On",
    performer="Céline Dion",
    movie_title="Titanic"
)
best_match, score = matcher.find_best_match(soundtrack, videos_with_comments)
```

### Custom Parser

```python
from linker.parser import SoundtrackParser

# Parse custom soundtrack format
soundtracks = SoundtrackParser.parse_soundtrack_text(
    your_soundtrack_text,
    movie_title="Your Movie"
)
```

## Output Format

### JSON Output
```json
[
  {
    "soundtrack": {
      "title": "My Heart Will Go On",
      "performer": "Céline Dion",
      "composer": "James Horner",
      "movie_title": "Titanic"
    },
    "search_query": "My Heart Will Go On Céline Dion from Titanic",
    "best_match": {
      "video_id": "DNyKDI9pn0Q",
      "url": "https://www.youtube.com/watch?v=DNyKDI9pn0Q",
      "title": "Celine Dion - My Heart Will Go On",
      "channel": "CelineDionVEVO",
      "views": 830000000,
      "likes": 5200000
    },
    "match_score": {
      "confidence": 0.95,
      "reasoning": "Perfect match: official Celine Dion video...",
      "key_factors": [
        "Official artist channel",
        "Exact title match",
        "Titanic mentioned in description"
      ],
      "concerns": []
    }
  }
]
```

## Performance Considerations

- **API Rate Limits**: YouTube API has quota limits (~10,000 units/day for free tier)
- **Parallel Processing**: Adjust `MAX_WORKERS` based on your rate limits
- **Comment Fetching**: Disable `USE_COMMENTS` for faster processing
- **Gemini Costs**: Gemini 2.5 Flash is very cost-effective but monitor usage

## Limitations

- Requires valid API keys for YouTube and Gemini
- Subject to API rate limits and quotas
- LLM matching quality depends on metadata completeness
- Some videos may have comments disabled
- Traditional/classical music may have multiple valid versions

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- IMDb for soundtrack metadata
- YouTube Data API v3
- Google Gemini for intelligent matching
