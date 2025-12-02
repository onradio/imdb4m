#!/usr/bin/env env python3
"""
Extract YouTube links for movie soundtracks from TTL files.

This script processes all movies in a dataset folder, extracts soundtrack metadata
from TTL files, finds matching YouTube videos using the MusicLinker pipeline,
and saves the results to JSON files in each movie's soundtrack folder.
"""
import sys
import time
import random
import argparse
import logging
from pathlib import Path
from typing import List

from googleapiclient.errors import HttpError
from tqdm import tqdm

from linker import MusicLinker, SoundtrackParser, setup_logging
from linker.models import MusicLinkResult
from linker.utils import save_results_to_json

logger = logging.getLogger(__name__)


class QuotaExceededException(Exception):
	"""Raised when YouTube API quota is exceeded.

	Includes resume information (track index) and partial results so processing
	can continue with next API key without losing work.
	"""

	def __init__(self, message: str, resume_index: int | None = None, partial_results: List[MusicLinkResult] | None = None):
		super().__init__(message)
		self.resume_index = resume_index
		self.partial_results = partial_results or []


def parse_args():
	"""Parse command-line arguments."""
	parser = argparse.ArgumentParser(
		description="Extract YouTube links for movie soundtracks from TTL files",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter
	)
	
	# Input/Output
	parser.add_argument(
		'--dataset-root',
		type=str,
		default='../data/subset/',
		help='Root folder containing movie subdirectories with TTL files'
	)
	parser.add_argument(
		'--output-filename',
		type=str,
		default='soundtrack_links.json',
		help='Output JSON filename to save in each movie_soundtrack folder'
	)
	
	# API Keys (single key or file of keys)
	parser.add_argument(
		'--youtube-api-key',
		type=str,
		required=False,
		help='YouTube Data API v3 key'
	)
	parser.add_argument(
		'--youtube-api-file',
		type=str,
		required=False,
		help='Path to text file with one YouTube API key per line (overrides --youtube-api-key)'
	)
	parser.add_argument(
		'--gemini-api-key',
		type=str,
		required=True,
		help='Google AI API key for Gemini'
	)
	
	# Processing limits
	parser.add_argument(
		'--max-soundtracks-per-movie',
		type=int,
		default=None,
		help='Maximum number of soundtracks to process per movie (None = all)'
	)
	parser.add_argument(
		'--max-movies',
		type=int,
		default=None,
		help='Maximum number of movies to process (None = all)'
	)
	
	# MusicLinker parameters
	parser.add_argument(
		'--max-search-results',
		type=int,
		default=10,
		help='Maximum YouTube search results per soundtrack'
	)
	parser.add_argument(
		'--max-comments-per-video',
		type=int,
		default=0,
		help='Maximum comments to fetch per video (0 = disabled)'
	)
	parser.add_argument(
		'--use-comments',
		action='store_true',
		help='Use YouTube comments in matching analysis'
	)
	parser.add_argument(
		'--gemini-model',
		type=str,
		default='gemini-2.5-flash',
		help='Gemini model name to use for matching'
	)
	
	# Delay parameters
	parser.add_argument(
		'--delay-min',
		type=float,
		default=1.0,
		help='Minimum delay (seconds) between soundtrack requests'
	)
	parser.add_argument(
		'--delay-max',
		type=float,
		default=3.0,
		help='Maximum delay (seconds) between soundtrack requests'
	)
	
	# Logging
	parser.add_argument(
		'--log-level',
		type=str,
		default='INFO',
		choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
		help='Logging level'
	)
	parser.add_argument(
		'--skip-existing',
		action='store_true',
		help='Skip movies that already have output files'
	)
	
	return parser.parse_args()


def _load_youtube_keys_from_file(path: Path) -> List[str]:
	"""Load YouTube API keys from plaintext file (one per line)."""
	if not path.exists():
		raise FileNotFoundError(f"YouTube API keys file not found: {path}")
	keys: List[str] = []
	for line in path.read_text().splitlines():
		line = line.strip()
		if not line or line.startswith('#'):
			continue
		keys.append(line)
	if not keys:
		raise ValueError(f"No usable keys found in file: {path}")
	return keys


def process_movie(
	movie_folder: Path,
	dataset_root: Path,
	linker: MusicLinker,
	args: argparse.Namespace,
	start_index: int = 0,
	existing_results: List[MusicLinkResult] | None = None
) -> tuple[int, int]:
	"""
	Process a single movie: parse TTL, find YouTube matches, save results.
	
	Args:
		movie_folder: Path to movie folder
		dataset_root: Root dataset path
		linker: MusicLinker instance
		args: Command-line arguments
		
	Returns:
		Tuple of (total_tracks, successful_matches)
	"""
	imdb_id = movie_folder.name
	output_path = movie_folder / 'movie_soundtrack' / args.output_filename
	
	# Check if output already exists
	if args.skip_existing and output_path.exists():
		logger.info(f"⏭️  Skipping {imdb_id}: output file already exists")
		return (0, 0)
	
	logger.info(f"\n{'='*70}")
	logger.info(f"Processing: {imdb_id}")
	logger.info('='*70)
	
	try:
		# Parse soundtrack metadata from TTL
		tracks = SoundtrackParser.parse_soundtrack_ttl(str(dataset_root), imdb_id)
		logger.info(f"Found {len(tracks)} tracks in TTL files")
		
		if not tracks:
			logger.warning(f"⚠️  No soundtracks found for {imdb_id}")
			logger.warning(f"   Check if TTL files exist in: {movie_folder / 'movie_soundtrack'}")
			return (0, 0)
		
		# Limit tracks if specified
		if args.max_soundtracks_per_movie:
			original_count = len(tracks)
			tracks = tracks[:args.max_soundtracks_per_movie]
			logger.info(f"Limited to {len(tracks)}/{original_count} tracks")
		
		# Track-by-track processing to allow mid-movie resume on quota limits
		logger.info(f"Finding YouTube matches track-by-track (delay {args.delay_min}-{args.delay_max}s)...")
		results: List[MusicLinkResult] = list(existing_results or [])
		for idx in range(start_index, len(tracks)):
			track = tracks[idx]
			try:
				res = linker.find_match(track)
				# Detect quota error swallowed by MusicLinker and escalate (do not append result)
				if res.error and ('quotaExceeded' in res.error or 'quota' in res.error.lower()):
					logger.error(
						f"🚫 Quota exceeded detected inside linker for track {idx} ('{track.title}') of movie {imdb_id}"
					)
					# Do NOT append the failed track result; resume should retry it
					raise QuotaExceededException(
						"YouTube API quota exceeded",
						resume_index=idx,
						partial_results=results,
					)
				# Logging linking result -----------------------------------------
				if res.is_successful():
					logger.info(
						f"✓ Found match for '{track.title}': "
						f"{res.best_match.url} "
						f"(confidence: {res.match_score.confidence:.2f})"
					)
				else:
					logger.warning(f"✗ No match found for '{track.title}'")
				# ----------------------------------------------------------------
				results.append(res)
				if idx < len(tracks) - 1:
					delay = random.uniform(args.delay_min, args.delay_max)
					time.sleep(delay)
			except HttpError as e:  # again in case linker missed it
				if e.resp.status == 403 and 'quota' in str(e).lower():
					logger.error(f"🚫 Quota exceeded while processing track {idx} ('{track.title}') of movie {imdb_id}")
					raise QuotaExceededException(
						"YouTube API quota exceeded",
						resume_index=idx,
						partial_results=results,
					) from e
				# Other HTTP errors propagate
				raise
	
		# Analyse results
		successful_matches = 0
		no_youtube_results = 0
		llm_failures = 0
		
		for result in results:
			if result.best_match:
				successful_matches += 1
			elif result.error:
				if "No YouTube videos found" in result.error:
					no_youtube_results += 1
					logger.warning(
						f"⚠️  No YouTube results for '{result.soundtrack.title}' "
						f"(query: {result.search_query})"
					)
				else:
					llm_failures += 1
					logger.warning(
						f"⚠️  LLM/processing error for '{result.soundtrack.title}': "
						f"{result.error[:100]}"
					)
		
		# Save results
		output_path.parent.mkdir(parents=True, exist_ok=True)
		save_results_to_json(results, str(output_path))
		logger.info(f"✓ Saved results to: {output_path}")
		
		# Print summary
		logger.info(f"\nSummary for {imdb_id}:")
		logger.info(f"  Total tracks: {len(tracks)}")
		logger.info(f"  Successful matches: {successful_matches}")
		if no_youtube_results > 0:
			logger.info(f"  No YouTube results: {no_youtube_results}")
		if llm_failures > 0:
			logger.info(f"  LLM/processing failures: {llm_failures}")
		logger.info(f"  Success rate: {successful_matches/len(tracks)*100:.1f}%")
		
		return (len(tracks), successful_matches)
	
	except QuotaExceededException:
		# Re-raise quota exception to stop processing
		raise
		
	except Exception as e:
		logger.error(f"✗ Error processing {imdb_id}: {e}", exc_info=True)
		return (0, 0)


def main():
	"""Main entry point."""
	args = parse_args()
	
	# Setup logging
	setup_logging(args.log_level)
	
	# Resolve dataset path
	dataset_root = Path(args.dataset_root).resolve()
	if not dataset_root.exists():
		logger.error(f"Dataset root does not exist: {dataset_root}")
		sys.exit(1)
	
	# Get all movie folders but skip 'actors' folder
	movie_folders = sorted([d for d in dataset_root.iterdir() if d.is_dir() and d.name != 'actors'])
	
	if not movie_folders:
		logger.error(f"No movie folders found in: {dataset_root}")
		sys.exit(1)
	
	# Limit movies if specified
	if args.max_movies:
		movie_folders = movie_folders[:args.max_movies]
	
	logger.info(f"Found {len(movie_folders)} movies to process")
	logger.info(f"Movie IDs: {[d.name for d in movie_folders]}")
	
	# Prepare YouTube API keys (single or multiple)
	if args.youtube_api_file:
		try:
			yt_keys = _load_youtube_keys_from_file(Path(args.youtube_api_file))
			logger.info(f"Loaded {len(yt_keys)} YouTube API keys from file")
		except Exception as e:
			logger.error(f"Failed loading keys file: {e}")
			sys.exit(1)
	else:
		if not args.youtube_api_key:
			logger.error("Provide --youtube-api-key or --youtube-api-file")
			sys.exit(1)
		yt_keys = [args.youtube_api_key]

	current_key_index = 0

	def build_linker(youtube_key: str) -> MusicLinker:
		return MusicLinker(
			youtube_api_key=youtube_key,
			gemini_api_key=args.gemini_api_key,
			max_search_results=args.max_search_results,
			max_comments_per_video=args.max_comments_per_video,
			use_comments=args.use_comments,
			gemini_model=args.gemini_model
		)

	logger.info("\nInitializing MusicLinker...")
	logger.info(f"  Gemini model: {args.gemini_model}")
	logger.info(f"  Max search results: {args.max_search_results}")
	logger.info(f"  Use comments: {args.use_comments}")
	linker = build_linker(yt_keys[current_key_index])
	
	# Process all movies
	total_tracks_processed = 0
	total_successful_matches = 0
	movies_processed = 0
	quota_exceeded = False
	
	try:
		with tqdm(total=len(movie_folders), desc="Processing movies", unit="movie") as pbar:
			for movie_folder in movie_folders:
				start_index = 0
				partial_results: List[MusicLinkResult] = []
				while True:
					try:
						tracks_count, matches_count = process_movie(
							movie_folder,
							dataset_root,
							linker,
							args,
							start_index=start_index,
							existing_results=partial_results
						)
						total_tracks_processed += tracks_count
						total_successful_matches += matches_count
						movies_processed += 1
						pbar.update(1)
						break  # finished this movie
					except QuotaExceededException as qe:
						current_key_index += 1
						if current_key_index >= len(yt_keys):
							logger.error(f"\n{'='*70}")
							logger.error("🚫 YOUTUBE API QUOTA EXCEEDED (ALL KEYS)")
							logger.error('='*70)
							logger.error(f"Processed {movies_processed}/{len(movie_folders)} movies before quota limit")
							logger.error(f"Remaining movies: {len(movie_folders) - movies_processed}")
							logger.error("Processing stopped to avoid saving empty/partial results.")
							logger.error("Add more keys or wait for quota reset to continue.")
							quota_exceeded = True
							break  # exit movie retry loop
						logger.warning(
							f"Quota hit. Switching to key {current_key_index+1}/{len(yt_keys)} and resuming movie {movie_folder.name} at track {qe.resume_index}"
						)
						linker = build_linker(yt_keys[current_key_index])
						start_index = qe.resume_index or 0
						partial_results = qe.partial_results
				if quota_exceeded:
					break
	
	except KeyboardInterrupt:
		logger.warning("\n\n⚠️  Processing interrupted by user")
	
	# Final summary
	logger.info(f"\n{'='*70}")
	logger.info("FINAL SUMMARY")
	logger.info('='*70)
	logger.info(f"Movies processed: {movies_processed}/{len(movie_folders)}")
	logger.info(f"Total tracks processed: {total_tracks_processed}")
	logger.info(f"Total successful matches: {total_successful_matches}")
	if total_tracks_processed > 0:
		success_rate = total_successful_matches / total_tracks_processed * 100
		logger.info(f"Overall success rate: {success_rate:.1f}%")
	logger.info(f"Output files saved to: <movie_folder>/movie_soundtrack/{args.output_filename}")
	if quota_exceeded:
		logger.info(f"⚠️  Stopped early due to quota limit")
	logger.info('='*70)
	
	# Exit with error code if quota was exceeded
	if quota_exceeded:
		sys.exit(2)


if __name__ == '__main__':
	main()
