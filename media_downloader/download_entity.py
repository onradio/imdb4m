#!/usr/bin/env python3
"""
Main script to download all media for an entity from the IMDB4M Knowledge Graph.

Usage:
    python -m media_downloader.download_entity <entity_uri> [options]
    
Examples:
    python -m media_downloader.download_entity https://www.imdb.com/title/tt0120338
    python -m media_downloader.download_entity https://www.imdb.com/name/nm0000138
    python -m media_downloader.download_entity tt0120338  # Short form
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .kg_parser import KGParser, EntityMedia
from .image_downloader import ImageDownloader
from .video_downloader import VideoDownloader
from .audio_downloader import AudioDownloader

logger = logging.getLogger(__name__)


def normalize_entity_uri(entity_input: str) -> str:
    """
    Normalize entity input to a full URI.
    
    Args:
        entity_input: Can be a full URI or just an ID (tt0120338 or nm0000138)
        
    Returns:
        Full IMDB URI
    """
    entity_input = entity_input.strip().rstrip('/')
    
    # Already a full URI
    if entity_input.startswith('http'):
        return entity_input
    
    # Movie ID (tt...)
    if entity_input.startswith('tt'):
        return f"https://www.imdb.com/title/{entity_input}"
    
    # Person ID (nm...)
    if entity_input.startswith('nm'):
        return f"https://www.imdb.com/name/{entity_input}"
    
    # Try to guess
    raise ValueError(
        f"Cannot parse entity input: {entity_input}. "
        "Please provide a full URI or an ID starting with 'tt' (movie) or 'nm' (person)"
    )


def download_entity_media(
    entity_uri: str,
    kg_path: str,
    output_dir: str = "output",
    download_images: bool = True,
    download_videos: bool = True,
    download_audio: bool = True,
    headless: bool = True,
    show_progress: bool = True,
) -> dict:
    """
    Download all media for an entity.
    
    Args:
        entity_uri: The entity URI or ID
        kg_path: Path to the KG TTL file
        output_dir: Base output directory
        download_images: Whether to download images
        download_videos: Whether to download videos
        download_audio: Whether to download audio
        headless: Whether to run browser in headless mode
        show_progress: Whether to show progress bars
        
    Returns:
        Dictionary with download statistics
    """
    # Normalize URI
    entity_uri = normalize_entity_uri(entity_uri)
    
    # Parse KG
    logger.info(f"Parsing KG for entity: {entity_uri}")
    parser = KGParser(kg_path)
    media = parser.get_entity_media(entity_uri)
    
    logger.info(f"Found media for {media.entity_id} ({media.entity_type}):")
    logger.info(f"  - Images: {len(media.images)}")
    logger.info(f"  - Videos: {len(media.videos)}")
    logger.info(f"  - Audio: {len(media.audio)}")
    
    output_base = Path(output_dir)
    stats = {
        'entity_id': media.entity_id,
        'entity_type': media.entity_type,
        'images_found': len(media.images),
        'videos_found': len(media.videos),
        'audio_found': len(media.audio),
        'images_downloaded': 0,
        'videos_downloaded': 0,
        'audio_downloaded': 0,
    }
    
    # Download images
    if download_images and media.images:
        logger.info("Downloading images...")
        image_downloader = ImageDownloader(output_dir)
        downloaded = image_downloader.download_entity_images(media, output_base, show_progress)
        stats['images_downloaded'] = len(downloaded)
        logger.info(f"Downloaded {len(downloaded)}/{len(media.images)} images")
    
    # Download videos
    if download_videos and media.videos:
        logger.info("Downloading videos...")
        video_downloader = VideoDownloader(output_dir, headless=headless)
        downloaded = video_downloader.download_entity_videos(media, output_base, show_progress)
        stats['videos_downloaded'] = len(downloaded)
        logger.info(f"Downloaded {len(downloaded)}/{len(media.videos)} videos")
    
    # Download audio
    if download_audio and media.audio:
        logger.info("Downloading audio...")
        audio_downloader = AudioDownloader(output_dir)
        downloaded = audio_downloader.download_entity_audio(media, output_base, show_progress)
        stats['audio_downloaded'] = len(downloaded)
        logger.info(f"Downloaded {len(downloaded)}/{len(media.audio)} audio files")
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download all media for an IMDB entity from the Knowledge Graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://www.imdb.com/title/tt0120338     # Download Titanic media
  %(prog)s tt1375666                                # Download Inception media (short form)
  %(prog)s nm0000138                                # Download Leonardo DiCaprio media
  %(prog)s tt0120338 --images-only                  # Only download images
  %(prog)s tt0120338 --no-videos                    # Skip video downloads
        """
    )
    
    parser.add_argument(
        'entity',
        help="Entity URI or ID (e.g., https://www.imdb.com/title/tt0120338, tt0120338, nm0000138)"
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
    
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help="Show browser window (useful for debugging)"
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help="Suppress progress bars"
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
    
    # Determine default KG path
    if args.kg_path is None:
        # Try to find the KG file relative to this script
        script_dir = Path(__file__).parent.parent
        default_kg_path = script_dir / "data" / "kg" / "imdb_kg_cleaned.ttl"
        if default_kg_path.exists():
            args.kg_path = str(default_kg_path)
        else:
            logger.error(f"KG file not found at {default_kg_path}")
            logger.error("Please specify --kg-path")
            sys.exit(1)
    
    # Determine what to download
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
        stats = download_entity_media(
            entity_uri=args.entity,
            kg_path=args.kg_path,
            output_dir=args.output_dir,
            download_images=download_images,
            download_videos=download_videos,
            download_audio=download_audio,
            headless=not args.no_headless,
            show_progress=not args.quiet,
        )
        
        # Print summary
        print("\n" + "=" * 50)
        print(f"Download Summary for {stats['entity_id']} ({stats['entity_type']})")
        print("=" * 50)
        print(f"Images:  {stats['images_downloaded']}/{stats['images_found']} downloaded")
        print(f"Videos:  {stats['videos_downloaded']}/{stats['videos_found']} downloaded")
        print(f"Audio:   {stats['audio_downloaded']}/{stats['audio_found']} downloaded")
        print(f"\nOutput directory: {Path(args.output_dir).absolute() / stats['entity_id']}")
        print("=" * 50)
        
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Download interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

