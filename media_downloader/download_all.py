#!/usr/bin/env python3
"""
Download all media for all entities in the IMDB4M Knowledge Graph.

Features:
- Iterates through all movies and persons in the KG
- Tracks progress to allow stopping and restarting
- Rate limiting to avoid anti-bot measures
- Configurable delays between downloads

Usage:
    python -m media_downloader.download_all [options]
    
Examples:
    python -m media_downloader.download_all
    python -m media_downloader.download_all --movies-only
    python -m media_downloader.download_all --delay 5 --batch-delay 60
"""

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from tqdm import tqdm

from .kg_parser import KGParser
from .image_downloader import ImageDownloader
from .video_downloader import VideoDownloader
from .audio_downloader import AudioDownloader

logger = logging.getLogger(__name__)

SCHEMA = Namespace("http://schema.org/")

# Default rate limiting settings
DEFAULT_DELAY_BETWEEN_ITEMS = 2.0  # seconds between each media item
DEFAULT_DELAY_BETWEEN_ENTITIES = 5.0  # seconds between entities
DEFAULT_BATCH_SIZE = 10  # entities per batch
DEFAULT_BATCH_DELAY = 30.0  # seconds between batches
DEFAULT_RANDOM_DELAY_RANGE = (0.5, 2.0)  # random additional delay range


class ProgressTracker:
    """Tracks download progress to support resume functionality."""

    def __init__(self, progress_file: str):
        """
        Initialize the progress tracker.

        Args:
            progress_file: Path to the JSON file storing progress
        """
        self.progress_file = Path(progress_file)
        self.progress = self._load_progress()

    def _load_progress(self) -> dict:
        """Load progress from file or create new."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load progress file: {e}")
        
        return {
            'completed_entities': [],
            'failed_entities': [],
            'started_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'stats': {
                'total_images': 0,
                'total_videos': 0,
                'total_audio': 0,
                'total_entities': 0,
            }
        }

    def save(self) -> None:
        """Save progress to file."""
        self.progress['last_updated'] = datetime.now().isoformat()
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def is_completed(self, entity_id: str) -> bool:
        """Check if an entity has been completed."""
        return entity_id in self.progress['completed_entities']

    def mark_completed(self, entity_id: str, images: int, videos: int, audio: int) -> None:
        """Mark an entity as completed."""
        if entity_id not in self.progress['completed_entities']:
            self.progress['completed_entities'].append(entity_id)
            self.progress['stats']['total_images'] += images
            self.progress['stats']['total_videos'] += videos
            self.progress['stats']['total_audio'] += audio
            self.progress['stats']['total_entities'] += 1

    def mark_failed(self, entity_id: str, error: str) -> None:
        """Mark an entity as failed."""
        failed_entry = {'entity_id': entity_id, 'error': error, 'timestamp': datetime.now().isoformat()}
        self.progress['failed_entities'].append(failed_entry)

    def get_completed_count(self) -> int:
        """Get count of completed entities."""
        return len(self.progress['completed_entities'])

    def get_stats(self) -> dict:
        """Get download statistics."""
        return self.progress['stats']


class RateLimiter:
    """Handles rate limiting for downloads."""

    def __init__(
        self,
        delay_between_items: float = DEFAULT_DELAY_BETWEEN_ITEMS,
        delay_between_entities: float = DEFAULT_DELAY_BETWEEN_ENTITIES,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_delay: float = DEFAULT_BATCH_DELAY,
        random_delay_range: tuple = DEFAULT_RANDOM_DELAY_RANGE,
    ):
        """
        Initialize the rate limiter.

        Args:
            delay_between_items: Base delay between individual media downloads
            delay_between_entities: Delay between processing different entities
            batch_size: Number of entities to process before taking a longer break
            batch_delay: Delay after processing a batch
            random_delay_range: Range for random additional delay
        """
        self.delay_between_items = delay_between_items
        self.delay_between_entities = delay_between_entities
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self.random_delay_range = random_delay_range
        self.entities_processed = 0

    def wait_between_items(self) -> None:
        """Wait between individual media downloads."""
        delay = self.delay_between_items + random.uniform(*self.random_delay_range)
        time.sleep(delay)

    def wait_between_entities(self) -> None:
        """Wait between processing different entities."""
        self.entities_processed += 1
        
        # Check if we need a batch break
        if self.entities_processed % self.batch_size == 0:
            logger.info(f"Batch of {self.batch_size} entities completed. Taking a {self.batch_delay}s break...")
            time.sleep(self.batch_delay)
        else:
            delay = self.delay_between_entities + random.uniform(*self.random_delay_range)
            time.sleep(delay)


def get_all_entities(kg_path: str, entity_type: Optional[str] = None) -> List[str]:
    """
    Get all entity URIs from the Knowledge Graph.

    Args:
        kg_path: Path to the KG TTL file
        entity_type: Optional filter - 'movie', 'person', or None for all

    Returns:
        List of entity URIs
    """
    logger.info("Loading Knowledge Graph to extract all entities...")
    graph = Graph()
    graph.parse(kg_path, format="turtle")
    logger.info(f"Loaded {len(graph)} triples")

    entities = []

    if entity_type is None or entity_type == 'movie':
        # Get all movies
        for movie_uri in graph.subjects(RDF.type, SCHEMA.Movie):
            uri_str = str(movie_uri)
            if '/title/tt' in uri_str:
                entities.append(uri_str)
        logger.info(f"Found {len([e for e in entities if '/title/' in e])} movies")

    if entity_type is None or entity_type == 'person':
        # Get all persons
        person_count = 0
        for person_uri in graph.subjects(RDF.type, SCHEMA.Person):
            uri_str = str(person_uri)
            if '/name/nm' in uri_str:
                entities.append(uri_str)
                person_count += 1
        logger.info(f"Found {person_count} persons")

    return entities


def download_entity_with_rate_limit(
    entity_uri: str,
    parser: KGParser,
    image_downloader: ImageDownloader,
    video_downloader: VideoDownloader,
    audio_downloader: AudioDownloader,
    output_dir: Path,
    rate_limiter: RateLimiter,
    download_images: bool = True,
    download_videos: bool = True,
    download_audio: bool = True,
) -> dict:
    """
    Download all media for an entity with rate limiting.

    Returns:
        Dictionary with download counts
    """
    media = parser.get_entity_media(entity_uri)
    
    stats = {
        'images': 0,
        'videos': 0,
        'audio': 0,
    }

    entity_output = output_dir / media.entity_id

    # Download images
    if download_images and media.images:
        images_path = entity_output / "images"
        for image in media.images:
            result = image_downloader.download_image(image.url, images_path)
            if result:
                stats['images'] += 1
            rate_limiter.wait_between_items()

    # Download videos
    if download_videos and media.videos:
        videos_path = entity_output / "videos"
        for video in media.videos:
            result = video_downloader.download_from_imdb(video, videos_path)
            if result:
                stats['videos'] += 1
            rate_limiter.wait_between_items()

    # Download audio
    if download_audio and media.audio:
        audio_path = entity_output / "audio"
        for audio in media.audio:
            result = audio_downloader.download_audio(audio, audio_path)
            if result:
                stats['audio'] += 1
            rate_limiter.wait_between_items()

    return stats


def download_all(
    kg_path: str,
    output_dir: str = "output",
    progress_file: str = "output/download_progress.json",
    entity_type: Optional[str] = None,
    download_images: bool = True,
    download_videos: bool = True,
    download_audio: bool = True,
    delay_between_items: float = DEFAULT_DELAY_BETWEEN_ITEMS,
    delay_between_entities: float = DEFAULT_DELAY_BETWEEN_ENTITIES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_delay: float = DEFAULT_BATCH_DELAY,
    max_entities: Optional[int] = None,
    headless: bool = True,
) -> dict:
    """
    Download all media for all entities in the KG.

    Args:
        kg_path: Path to the KG TTL file
        output_dir: Base output directory
        progress_file: Path to progress tracking file
        entity_type: Filter by type ('movie', 'person', or None for all)
        download_images: Whether to download images
        download_videos: Whether to download videos
        download_audio: Whether to download audio
        delay_between_items: Delay between individual downloads
        delay_between_entities: Delay between entities
        batch_size: Entities per batch before longer break
        batch_delay: Delay between batches
        max_entities: Maximum entities to process (for testing)
        headless: Whether to run browser in headless mode

    Returns:
        Final statistics dictionary
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize components
    progress = ProgressTracker(progress_file)
    rate_limiter = RateLimiter(
        delay_between_items=delay_between_items,
        delay_between_entities=delay_between_entities,
        batch_size=batch_size,
        batch_delay=batch_delay,
    )

    # Get all entities
    all_entities = get_all_entities(kg_path, entity_type)
    
    if max_entities:
        all_entities = all_entities[:max_entities]

    # Filter out already completed
    pending_entities = [e for e in all_entities if not progress.is_completed(
        e.split('/')[-1].rstrip('/') or e.split('/')[-2]
    )]

    logger.info(f"Total entities: {len(all_entities)}")
    logger.info(f"Already completed: {progress.get_completed_count()}")
    logger.info(f"Pending: {len(pending_entities)}")

    if not pending_entities:
        logger.info("All entities already processed!")
        return progress.get_stats()

    # Initialize downloaders
    parser = KGParser(kg_path)
    image_downloader = ImageDownloader(output_dir)
    video_downloader = VideoDownloader(output_dir, headless=headless) if download_videos else None
    audio_downloader = AudioDownloader(output_dir) if download_audio else None

    try:
        # Process entities with progress bar
        with tqdm(pending_entities, desc="Processing entities") as pbar:
            for entity_uri in pbar:
                # Extract entity ID for display and tracking
                entity_id = entity_uri.split('/')[-1].rstrip('/') or entity_uri.split('/')[-2]
                pbar.set_postfix_str(entity_id[:15])

                try:
                    stats = download_entity_with_rate_limit(
                        entity_uri=entity_uri,
                        parser=parser,
                        image_downloader=image_downloader,
                        video_downloader=video_downloader,
                        audio_downloader=audio_downloader,
                        output_dir=output_path,
                        rate_limiter=rate_limiter,
                        download_images=download_images,
                        download_videos=download_videos,
                        download_audio=download_audio,
                    )

                    progress.mark_completed(
                        entity_id,
                        images=stats['images'],
                        videos=stats['videos'],
                        audio=stats['audio'],
                    )

                except Exception as e:
                    logger.error(f"Error processing {entity_id}: {e}")
                    progress.mark_failed(entity_id, str(e))

                # Save progress periodically
                progress.save()

                # Rate limit between entities
                rate_limiter.wait_between_entities()

    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user. Progress has been saved.")
        progress.save()
        raise

    finally:
        # Cleanup video downloader
        if video_downloader:
            video_downloader._close_driver()

    # Save final progress
    progress.save()

    return progress.get_stats()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download all media for all entities in the IMDB4M Knowledge Graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Rate Limiting:
  The script includes several rate limiting mechanisms to avoid triggering
  anti-bot measures and to be respectful to server resources:
  
  - Delay between individual media downloads (default: 2s + random 0.5-2s)
  - Delay between entities (default: 5s + random 0.5-2s)
  - Batch breaks every N entities (default: 30s every 10 entities)

Examples:
  %(prog)s                                    # Download all media
  %(prog)s --movies-only                      # Only process movies
  %(prog)s --persons-only                     # Only process persons
  %(prog)s --images-only                      # Only download images
  %(prog)s --max-entities 100                 # Process first 100 entities
  %(prog)s --delay 5 --batch-delay 120        # Slower rate limiting
        """
    )

    parser.add_argument(
        '--kg-path',
        default=None,
        help="Path to the KG TTL file (default: data/kg/imdb_kg_cleaned.ttl)"
    )

    parser.add_argument(
        '--output-dir', '-o',
        default="output",
        help="Output directory (default: output)"
    )

    parser.add_argument(
        '--progress-file',
        default=None,
        help="Progress tracking file (default: output/download_progress.json)"
    )

    # Entity type filters
    entity_group = parser.add_mutually_exclusive_group()
    entity_group.add_argument(
        '--movies-only',
        action='store_true',
        help="Only process movies"
    )
    entity_group.add_argument(
        '--persons-only',
        action='store_true',
        help="Only process persons"
    )

    # Media type filters
    parser.add_argument(
        '--images-only',
        action='store_true',
        help="Only download images"
    )
    parser.add_argument(
        '--videos-only',
        action='store_true',
        help="Only download videos"
    )
    parser.add_argument(
        '--audio-only',
        action='store_true',
        help="Only download audio"
    )
    parser.add_argument(
        '--no-images',
        action='store_true',
        help="Skip image downloads"
    )
    parser.add_argument(
        '--no-videos',
        action='store_true',
        help="Skip video downloads"
    )
    parser.add_argument(
        '--no-audio',
        action='store_true',
        help="Skip audio downloads"
    )

    # Rate limiting options
    parser.add_argument(
        '--delay',
        type=float,
        default=DEFAULT_DELAY_BETWEEN_ITEMS,
        help=f"Delay between individual downloads in seconds (default: {DEFAULT_DELAY_BETWEEN_ITEMS})"
    )
    parser.add_argument(
        '--entity-delay',
        type=float,
        default=DEFAULT_DELAY_BETWEEN_ENTITIES,
        help=f"Delay between entities in seconds (default: {DEFAULT_DELAY_BETWEEN_ENTITIES})"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Entities per batch before longer break (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        '--batch-delay',
        type=float,
        default=DEFAULT_BATCH_DELAY,
        help=f"Delay between batches in seconds (default: {DEFAULT_BATCH_DELAY})"
    )

    # Other options
    parser.add_argument(
        '--max-entities',
        type=int,
        default=None,
        help="Maximum number of entities to process (for testing)"
    )
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help="Show browser window for video downloads"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Determine KG path
    if args.kg_path is None:
        script_dir = Path(__file__).parent.parent
        default_kg_path = script_dir / "data" / "kg" / "imdb_kg_cleaned.ttl"
        if default_kg_path.exists():
            args.kg_path = str(default_kg_path)
        else:
            logger.error(f"KG file not found at {default_kg_path}")
            sys.exit(1)

    # Determine progress file
    if args.progress_file is None:
        args.progress_file = str(Path(args.output_dir) / "download_progress.json")

    # Determine entity type filter
    entity_type = None
    if args.movies_only:
        entity_type = 'movie'
    elif args.persons_only:
        entity_type = 'person'

    # Determine media type filters
    if args.images_only:
        download_images = True
        download_videos = False
        download_audio = False
    elif args.videos_only:
        download_images = False
        download_videos = True
        download_audio = False
    elif args.audio_only:
        download_images = False
        download_videos = False
        download_audio = True
    else:
        download_images = not args.no_images
        download_videos = not args.no_videos
        download_audio = not args.no_audio

    try:
        logger.info("=" * 60)
        logger.info("IMDB4M Media Downloader - Batch Download")
        logger.info("=" * 60)
        logger.info(f"KG Path: {args.kg_path}")
        logger.info(f"Output: {args.output_dir}")
        logger.info(f"Progress: {args.progress_file}")
        logger.info(f"Entity type: {entity_type or 'all'}")
        logger.info(f"Download images: {download_images}")
        logger.info(f"Download videos: {download_videos}")
        logger.info(f"Download audio: {download_audio}")
        logger.info(f"Rate limiting: {args.delay}s between items, {args.entity_delay}s between entities")
        logger.info(f"Batch: {args.batch_size} entities, then {args.batch_delay}s break")
        logger.info("=" * 60)

        stats = download_all(
            kg_path=args.kg_path,
            output_dir=args.output_dir,
            progress_file=args.progress_file,
            entity_type=entity_type,
            download_images=download_images,
            download_videos=download_videos,
            download_audio=download_audio,
            delay_between_items=args.delay,
            delay_between_entities=args.entity_delay,
            batch_size=args.batch_size,
            batch_delay=args.batch_delay,
            max_entities=args.max_entities,
            headless=not args.no_headless,
        )

        # Print final summary
        print("\n" + "=" * 60)
        print("Download Complete!")
        print("=" * 60)
        print(f"Total entities processed: {stats['total_entities']}")
        print(f"Total images downloaded: {stats['total_images']}")
        print(f"Total videos downloaded: {stats['total_videos']}")
        print(f"Total audio files downloaded: {stats['total_audio']}")
        print(f"Progress saved to: {args.progress_file}")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nDownload interrupted. Progress has been saved.")
        print(f"Resume by running the same command again.")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

