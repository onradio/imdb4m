"""
Configuration and utilities for the music linker.
"""
import os
import logging
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Configuration manager for API keys and settings."""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Load configuration from environment variables.
        
        Args:
            env_file: Path to .env file (optional)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # Search settings
        self.max_search_results = int(os.getenv('MAX_SEARCH_RESULTS', '10'))
        self.max_comments_per_video = int(os.getenv('MAX_COMMENTS_PER_VIDEO', '20'))
        self.use_comments = os.getenv('USE_COMMENTS', 'true').lower() == 'true'
        
        # LLM settings
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')
        
        # Parallel processing
        self.max_workers = int(os.getenv('MAX_WORKERS', '3'))
        
        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    def validate(self) -> bool:
        """
        Validate that required API keys are present.
        
        Returns:
            True if configuration is valid
        
        Raises:
            ValueError: If required keys are missing
        """
        if not self.youtube_api_key:
            raise ValueError("YOUTUBE_API_KEY environment variable is required")
        
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        return True


def setup_logging(level: str = 'INFO'):
    """
    Configure logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def save_results_to_json(results: list, output_file: str):
    """
    Save music link results to a JSON file.
    
    Args:
        results: List of MusicLinkResult objects
        output_file: Path to output file
    """
    import json
    from datetime import datetime
    
    output_data = []
    
    for result in results:
        data = {
            'soundtrack': {
                'title': result.soundtrack.title,
                'performer': result.soundtrack.performer,
                'composer': result.soundtrack.composer,
                'movie_title': result.soundtrack.movie_title,
            },
            'search_query': result.search_query,
            'timestamp': result.timestamp.isoformat(),
        }
        
        if result.best_match:
            data['best_match'] = {
                'video_id': result.best_match.video_id,
                'url': result.best_match.url,
                'title': result.best_match.title,
                'channel': result.best_match.channel_title,
                'views': result.best_match.view_count,
                'likes': result.best_match.like_count,
            }
        
        if result.match_score:
            data['match_score'] = {
                'confidence': result.match_score.confidence,
                'reasoning': result.match_score.reasoning,
                'key_factors': result.match_score.key_factors,
                'concerns': result.match_score.concerns,
            }
        
        if result.error:
            data['error'] = result.error
        
        output_data.append(data)
    
    # Create output directory if needed
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def save_results_to_csv(results: list, output_file: str):
    """
    Save music link results to a CSV file.
    
    Args:
        results: List of MusicLinkResult objects
        output_file: Path to output file
    """
    import csv
    from pathlib import Path
    
    # Create output directory if needed
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'Song Title',
            'Performer',
            'Composer',
            'Movie',
            'Search Query',
            'YouTube URL',
            'Video Title',
            'Channel',
            'Confidence',
            'Views',
            'Likes',
            'Error'
        ])
        
        # Data rows
        for result in results:
            writer.writerow([
                result.soundtrack.title,
                result.soundtrack.performer or '',
                result.soundtrack.composer or '',
                result.soundtrack.movie_title or '',
                result.search_query,
                result.best_match.url if result.best_match else '',
                result.best_match.title if result.best_match else '',
                result.best_match.channel_title if result.best_match else '',
                f"{result.match_score.confidence:.2f}" if result.match_score else '',
                result.best_match.view_count if result.best_match else '',
                result.best_match.like_count if result.best_match else '',
                result.error or ''
            ])
