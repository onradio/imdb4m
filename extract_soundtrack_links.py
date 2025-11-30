#!/usr/bin/env env python3
"""
Extract YouTube links for movie soundtracks from TTL files.

This script processes all movies in a dataset folder, extracts soundtrack metadata
from TTL files, finds matching YouTube videos using the MusicLinker pipeline,
and saves the results to JSON files in each movie's soundtrack folder.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List

from linker import MusicLinker, SoundtrackParser, setup_logging
from linker.models import SoundtrackMetadata, MusicLinkResult
from linker.utils import save_results_to_json

logger = logging.getLogger(__name__)


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
	
	# API Keys
	parser.add_argument(
		'--youtube-api-key',
		type=str,
		required=True,
		help='YouTube Data API v3 key'
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


def process_movie(
	movie_folder: Path,
	dataset_root: Path,
	linker: MusicLinker,
	args: argparse.Namespace
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
		
		# Process soundtracks sequentially with delays
		logger.info(f"Finding YouTube matches (delay: {args.delay_min}-{args.delay_max}s)...")
		results = linker.find_matches_sequential(
			tracks,
			delay_range=(args.delay_min, args.delay_max)
		)
		
		# Analyze results
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
	
	# Get all movie folders
	movie_folders = sorted([d for d in dataset_root.iterdir() if d.is_dir()])
	
	if not movie_folders:
		logger.error(f"No movie folders found in: {dataset_root}")
		sys.exit(1)
	
	# Limit movies if specified
	if args.max_movies:
		movie_folders = movie_folders[:args.max_movies]
	
	logger.info(f"Found {len(movie_folders)} movies to process")
	logger.info(f"Movie IDs: {[d.name for d in movie_folders]}")
	
	# Initialize MusicLinker
	logger.info("\nInitializing MusicLinker...")
	logger.info(f"  Gemini model: {args.gemini_model}")
	logger.info(f"  Max search results: {args.max_search_results}")
	logger.info(f"  Use comments: {args.use_comments}")
	
	linker = MusicLinker(
		youtube_api_key=args.youtube_api_key,
		gemini_api_key=args.gemini_api_key,
		max_search_results=args.max_search_results,
		max_comments_per_video=args.max_comments_per_video,
		use_comments=args.use_comments,
		gemini_model=args.gemini_model
	)
	
	# Process all movies
	total_tracks_processed = 0
	total_successful_matches = 0
	
	for movie_folder in movie_folders:
		tracks_count, matches_count = process_movie(
			movie_folder,
			dataset_root,
			linker,
			args
		)
		total_tracks_processed += tracks_count
		total_successful_matches += matches_count
	
	# Final summary
	logger.info(f"\n{'='*70}")
	logger.info("FINAL SUMMARY")
	logger.info('='*70)
	logger.info(f"Movies processed: {len(movie_folders)}")
	logger.info(f"Total tracks processed: {total_tracks_processed}")
	logger.info(f"Total successful matches: {total_successful_matches}")
	if total_tracks_processed > 0:
		success_rate = total_successful_matches / total_tracks_processed * 100
		logger.info(f"Overall success rate: {success_rate:.1f}%")
	logger.info(f"Output files saved to: <movie_folder>/movie_soundtrack/{args.output_filename}")
	logger.info('='*70)


if __name__ == '__main__':
	main()
