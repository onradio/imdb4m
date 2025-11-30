"""
Main music linker pipeline orchestrator.
"""
from typing import List, Optional
import logging
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

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
			retries = 3
			for attempt in range(retries):
				# Generate search query
				logger.info(f"Search attempt {attempt + 1} for '{soundtrack.title}'")
				add_movie = attempt < 1  # Add movie title only on first attempt
				add_performer = attempt < 2  # Add performer for first 2 attempts
				# Last attempt uses only the song title for broader search
				search_query = soundtrack.to_search_query(
					add_movie=add_movie, add_performer=add_performer)
				logger.info(f"Searching for: {search_query}")
				# Search YouTube for candidates
				candidates = self.youtube_client.search_videos(
					query=search_query,
					max_results=self.max_search_results
				)
				# Stop retrying if we found candidates
				if candidates:
					break
				# Generate a backoff delay before retrying
				backoff_delay = (2 ** attempt) + random.uniform(0, 1)
				logger.info(f"No candidates found, retrying in {backoff_delay:.2f} seconds...")
				time.sleep(backoff_delay)
            
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
    
	def find_matches_sequential(
		self,
		soundtracks: List[SoundtrackMetadata],
		delay_range: tuple = (1.0, 3.0)
	) -> List[MusicLinkResult]:
		"""
		Find matches for multiple soundtracks sequentially (useful for debugging).
        
		Args:
			soundtracks: List of soundtrack metadata
			delay_range: Tuple of (min, max) seconds to wait between requests
            
		Returns:
			List of MusicLinkResult objects
		"""
		results = []
		
		for i, soundtrack in enumerate(tqdm(soundtracks, desc="Processing tracks", unit="track")):
			try:
				result = self.find_match(soundtrack)
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
			
			# Add random delay between requests (except after the last one)
			if i < len(soundtracks) - 1:
				delay = random.uniform(delay_range[0], delay_range[1])
				time.sleep(delay)
		
		return results
	
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
            
			# Collect results as they complete with progress bar
			with tqdm(total=len(soundtracks), desc="Processing tracks", unit="track") as pbar:
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
					
					pbar.update(1)
        
		return results
