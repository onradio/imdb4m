"""
Main music linker pipeline orchestrator.
"""
from typing import List, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import SoundtrackMetadata, MusicLinkResult, YouTubeVideo
from .youtube_client import YouTubeClient
from .gemini_matcher import GeminiMatcher

logger = logging.getLogger(__name__)


class MusicLinker:
    """
    Main pipeline for linking soundtrack metadata to YouTube videos.
    
    This orchestrates the entire process:
    1. Search YouTube for potential matches
    2. Fetch detailed video information including comments
    3. Use LLM to analyze and select the best match
    """
    
    def __init__(
        self,
        youtube_api_key: str,
        gemini_api_key: str,
        max_search_results: int = 10,
        max_comments_per_video: int = 20,
        use_comments: bool = True,
        gemini_model: str = "gemini-2.0-flash-exp"
    ):
        """
        Initialize the music linker.
        
        Args:
            youtube_api_key: YouTube Data API v3 key
            gemini_api_key: Google AI API key for Gemini
            max_search_results: Maximum number of YouTube search results
            max_comments_per_video: Maximum comments to fetch per video
            use_comments: Whether to fetch and use comments in matching
            gemini_model: Gemini model to use for matching
        """
        self.youtube_client = YouTubeClient(youtube_api_key)
        self.gemini_matcher = GeminiMatcher(gemini_api_key, gemini_model)
        self.max_search_results = max_search_results
        self.max_comments_per_video = max_comments_per_video
        self.use_comments = use_comments
    
    def find_match(self, soundtrack: SoundtrackMetadata) -> MusicLinkResult:
        """
        Find the best YouTube match for a single soundtrack.
        
        Args:
            soundtrack: Soundtrack metadata
            
        Returns:
            MusicLinkResult with the best match and analysis
        """
        try:
            # Generate search query
            search_query = soundtrack.to_search_query()
            logger.info(f"Searching for: {search_query}")
            
            # Search YouTube
            candidates = self.youtube_client.search_videos(
                query=search_query,
                max_results=self.max_search_results
            )
            
            if not candidates:
                return MusicLinkResult(
                    soundtrack=soundtrack,
                    search_query=search_query,
                    error="No YouTube videos found"
                )
            
            logger.info(f"Found {len(candidates)} candidates")
            
            # Optionally fetch comments
            if self.use_comments:
                logger.info("Fetching comments for candidates...")
                candidates = self.youtube_client.enrich_videos_with_comments(
                    candidates,
                    max_comments_per_video=self.max_comments_per_video
                )
            
            # Use LLM to find best match
            logger.info("Analyzing candidates with LLM...")
            best_match, match_score = self.gemini_matcher.find_best_match(
                soundtrack=soundtrack,
                candidates=candidates,
                use_comments=self.use_comments
            )
            
            return MusicLinkResult(
                soundtrack=soundtrack,
                best_match=best_match,
                match_score=match_score,
                candidates=candidates,
                search_query=search_query
            )
            
        except Exception as e:
            logger.error(f"Error finding match for '{soundtrack.title}': {e}")
            return MusicLinkResult(
                soundtrack=soundtrack,
                search_query=soundtrack.to_search_query(),
                error=str(e)
            )
    
    def find_matches_batch(
        self,
        soundtracks: List[SoundtrackMetadata],
        max_workers: int = 3
    ) -> List[MusicLinkResult]:
        """
        Find matches for multiple soundtracks in parallel.
        
        Args:
            soundtracks: List of soundtrack metadata
            max_workers: Maximum number of parallel workers
            
        Returns:
            List of MusicLinkResult objects
        """
        results = []
        
        # Process in parallel with thread pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_soundtrack = {
                executor.submit(self.find_match, soundtrack): soundtrack
                for soundtrack in soundtracks
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_soundtrack):
                soundtrack = future_to_soundtrack[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.is_successful():
                        logger.info(
                            f"✓ Found match for '{soundtrack.title}': "
                            f"{result.best_match.url} "
                            f"(confidence: {result.match_score.confidence:.2f})"
                        )
                    else:
                        logger.warning(f"✗ No match found for '{soundtrack.title}'")
                        
                except Exception as e:
                    logger.error(f"Exception processing '{soundtrack.title}': {e}")
                    results.append(MusicLinkResult(
                        soundtrack=soundtrack,
                        search_query=soundtrack.to_search_query(),
                        error=str(e)
                    ))
        
        return results
