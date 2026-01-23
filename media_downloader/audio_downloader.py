"""
Audio Downloader for IMDB4M Knowledge Graph.

Uses yt-dlp to extract audio from YouTube URLs found in soundtrack_links.json files.
"""

import logging
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from .kg_parser import KGParser, AudioInfo, EntityMedia

logger = logging.getLogger(__name__)


class AudioDownloader:
    """Downloads audio from YouTube using yt-dlp."""

    def __init__(
        self,
        output_dir: str = "output",
        audio_format: str = "best",
        audio_quality: str = "192",
    ):
        """
        Initialize the audio downloader.

        Args:
            output_dir: Base directory for downloaded files
            audio_format: Output audio format (mp3, m4a, best, etc.)
                          'best' keeps original format (no conversion needed)
            audio_quality: Audio quality in kbps (for mp3)
        """
        self.output_dir = Path(output_dir)
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        
        # Check if yt-dlp is available
        self.ytdlp_path = self._find_ytdlp()
        
        # Check if ffmpeg is available for format conversion
        self.ffmpeg_available = shutil.which('ffmpeg') is not None
        if audio_format != 'best' and not self.ffmpeg_available:
            logger.warning(
                f"ffmpeg not found. Audio will be saved in original format instead of {audio_format}. "
                "Install ffmpeg for format conversion."
            )
            self.audio_format = 'best'

    def _find_ytdlp(self) -> str:
        """Find the yt-dlp executable."""
        # Check if yt-dlp is in PATH
        ytdlp = shutil.which('yt-dlp')
        if ytdlp:
            return ytdlp
        
        # Check common locations
        common_paths = [
            '/usr/local/bin/yt-dlp',
            '/usr/bin/yt-dlp',
            '~/.local/bin/yt-dlp',
        ]
        
        for path in common_paths:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return str(expanded)
        
        logger.warning("yt-dlp not found in PATH. Please install it with: pip install yt-dlp")
        return 'yt-dlp'  # Assume it will be installed

    def _sanitize_filename(self, title: str, max_length: int = 100) -> str:
        """
        Sanitize a string for use as a filename.

        Args:
            title: The original title
            max_length: Maximum filename length

        Returns:
            A sanitized filename
        """
        # Remove or replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        
        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized or "audio"

    def download_audio(
        self,
        audio_info: AudioInfo,
        output_path: Path,
    ) -> Optional[Path]:
        """
        Download audio from a YouTube URL.

        Args:
            audio_info: AudioInfo object with YouTube URL
            output_path: Directory to save the audio file

        Returns:
            Path to the downloaded file, or None if download failed
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename_base = self._sanitize_filename(audio_info.title)
        if audio_info.performer:
            performer_clean = self._sanitize_filename(audio_info.performer)
            filename_base = f"{performer_clean}-{filename_base}"
        
        expected_file = output_path / f"{filename_base}.{self.audio_format}"
        
        # Skip if already downloaded
        if expected_file.exists():
            logger.debug(f"Skipping (exists): {expected_file.name}")
            return expected_file
        
        # Build yt-dlp command
        output_template = str(output_path / f"{filename_base}.%(ext)s")
        
        cmd = [
            self.ytdlp_path,
            '--output', output_template,
            '--no-playlist',
            '--no-warnings',
            '--quiet',
            '--progress',
        ]
        
        # Use different strategies based on ffmpeg availability
        if self.ffmpeg_available:
            # With ffmpeg: extract and convert audio
            cmd.extend(['--extract-audio'])
            if self.audio_format != 'best':
                cmd.extend(['--audio-format', self.audio_format])
                cmd.extend(['--audio-quality', self.audio_quality])
        else:
            # Without ffmpeg: download best audio-only stream directly
            # This avoids the need for post-processing
            cmd.extend(['-f', 'bestaudio'])
        
        cmd.append(audio_info.youtube_url)
        
        try:
            logger.debug(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Find the downloaded file (extension might differ based on source)
                possible_extensions = ['mp3', 'm4a', 'opus', 'webm', 'ogg', 'wav', 'aac']
                if self.audio_format != 'best':
                    possible_extensions.insert(0, self.audio_format)
                
                for ext in possible_extensions:
                    potential_file = output_path / f"{filename_base}.{ext}"
                    if potential_file.exists():
                        logger.debug(f"Downloaded: {potential_file.name}")
                        return potential_file
                
                # Also check for any file starting with the filename_base
                for f in output_path.glob(f"{filename_base}.*"):
                    if f.is_file():
                        logger.debug(f"Downloaded: {f.name}")
                        return f
                
                logger.warning(f"Download succeeded but file not found: {filename_base}")
                return None
            else:
                logger.warning(f"yt-dlp failed for {audio_info.youtube_url}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout downloading: {audio_info.youtube_url}")
            return None
        except FileNotFoundError:
            logger.error(f"yt-dlp not found. Install with: pip install yt-dlp")
            return None
        except Exception as e:
            logger.error(f"Error downloading {audio_info.youtube_url}: {e}")
            return None

    def download_audios(
        self,
        audios: List[AudioInfo],
        output_path: Path,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download multiple audio files.

        Args:
            audios: List of AudioInfo objects
            output_path: Directory to save audio files
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded files
        """
        downloaded = []
        
        iterator = tqdm(audios, desc="Downloading audio", disable=not show_progress)
        for audio in iterator:
            iterator.set_postfix_str(audio.title[:25] if audio.title else "")
            result = self.download_audio(audio, output_path)
            if result:
                downloaded.append(result)
        
        return downloaded

    def download_entity_audio(
        self,
        entity_media: EntityMedia,
        base_output_dir: Optional[Path] = None,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download all audio for an entity.

        Args:
            entity_media: EntityMedia object containing audio information
            base_output_dir: Base output directory (defaults to self.output_dir)
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded files
        """
        if base_output_dir is None:
            base_output_dir = self.output_dir
        
        output_path = base_output_dir / entity_media.entity_id / "audio"
        
        logger.info(f"Downloading {len(entity_media.audio)} audio tracks for {entity_media.entity_id}")
        return self.download_audios(entity_media.audio, output_path, show_progress)


def download_all_audio(
    kg_path: str,
    data_dir: str,
    output_dir: str = "output",
    show_progress: bool = True,
) -> int:
    """
    Download all YouTube audio from all soundtrack_links.json files.

    Args:
        kg_path: Path to the KG TTL file
        data_dir: Path to the data directory
        output_dir: Base output directory
        show_progress: Whether to show progress

    Returns:
        Number of audio files downloaded
    """
    parser = KGParser(kg_path, data_dir)
    downloader = AudioDownloader(output_dir)
    
    logger.info("Finding all YouTube URLs from soundtrack files...")
    all_audio = parser.get_all_youtube_urls()
    logger.info(f"Found {len(all_audio)} audio tracks")
    
    output_path = Path(output_dir) / "all_audio"
    downloaded = downloader.download_audios(all_audio, output_path, show_progress)
    
    return len(downloaded)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    kg_path = Path(__file__).parent.parent / "data" / "kg" / "imdb_kg_cleaned.ttl"
    output_dir = Path(__file__).parent.parent / "output"
    
    if len(sys.argv) > 1:
        entity_uri = sys.argv[1]
    else:
        entity_uri = "https://www.imdb.com/title/tt1375666"  # Inception (has soundtrack)
    
    parser = KGParser(str(kg_path))
    media = parser.get_entity_media(entity_uri)
    
    if media.audio:
        downloader = AudioDownloader(str(output_dir))
        downloaded = downloader.download_entity_audio(media)
        print(f"\nDownloaded {len(downloaded)} audio files to {output_dir / media.entity_id / 'audio'}")
    else:
        print(f"No audio tracks found for {entity_uri}")
        print("Note: Audio tracks are only available for movies with soundtrack_links.json files")

