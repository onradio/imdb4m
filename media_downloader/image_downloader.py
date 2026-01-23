"""
Image Downloader for IMDB4M Knowledge Graph.

Downloads images from Amazon CDN URLs extracted from the KG.
"""

import logging
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, unquote

import requests
from tqdm import tqdm

from .kg_parser import KGParser, ImageInfo, EntityMedia

logger = logging.getLogger(__name__)

# Default headers to mimic a browser request
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.imdb.com/',
}


class ImageDownloader:
    """Downloads images from Amazon CDN URLs."""

    def __init__(
        self,
        output_dir: str = "output",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ):
        """
        Initialize the image downloader.

        Args:
            output_dir: Base directory for downloaded files
            max_retries: Maximum number of retry attempts for failed downloads
            retry_delay: Delay between retries in seconds
            timeout: Request timeout in seconds
        """
        self.output_dir = Path(output_dir)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _get_filename_from_url(self, url: str) -> str:
        """
        Extract a clean filename from an image URL.

        Args:
            url: The image URL

        Returns:
            A clean filename for saving the image
        """
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = Path(path).name
        
        # Clean up the filename (remove special chars except allowed ones)
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        
        # Ensure it has an extension
        if not any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            filename += '.jpg'
        
        return filename

    def download_image(
        self,
        url: str,
        output_path: Path,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Download a single image.

        Args:
            url: The image URL to download
            output_path: Directory to save the image
            filename: Optional custom filename (auto-generated if not provided)

        Returns:
            Path to the downloaded file, or None if download failed
        """
        if filename is None:
            filename = self._get_filename_from_url(url)
        
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        file_path = output_path / filename
        
        # Skip if already downloaded
        if file_path.exists():
            logger.debug(f"Skipping (exists): {filename}")
            return file_path
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, stream=True)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    logger.warning(f"Unexpected content type for {url}: {content_type}")
                
                # Download with progress for large files
                total_size = int(response.headers.get('content-length', 0))
                
                with open(file_path, 'wb') as f:
                    if total_size > 0:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    else:
                        f.write(response.content)
                
                logger.debug(f"Downloaded: {filename}")
                return file_path
                
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
        
        logger.error(f"Failed to download: {url}")
        return None

    def download_images(
        self,
        images: List[ImageInfo],
        output_path: Path,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download multiple images.

        Args:
            images: List of ImageInfo objects
            output_path: Directory to save images
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded images
        """
        downloaded = []
        
        iterator = tqdm(images, desc="Downloading images", disable=not show_progress)
        for image in iterator:
            result = self.download_image(image.url, output_path)
            if result:
                downloaded.append(result)
        
        return downloaded

    def download_entity_images(
        self,
        entity_media: EntityMedia,
        base_output_dir: Optional[Path] = None,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download all images for an entity.

        Args:
            entity_media: EntityMedia object containing image information
            base_output_dir: Base output directory (defaults to self.output_dir)
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded images
        """
        if base_output_dir is None:
            base_output_dir = self.output_dir
        
        output_path = base_output_dir / entity_media.entity_id / "images"
        
        logger.info(f"Downloading {len(entity_media.images)} images for {entity_media.entity_id}")
        return self.download_images(entity_media.images, output_path, show_progress)


def download_all_images(
    kg_path: str,
    output_dir: str = "output",
    show_progress: bool = True,
) -> int:
    """
    Download all images from the KG.

    Args:
        kg_path: Path to the KG TTL file
        output_dir: Base output directory
        show_progress: Whether to show progress

    Returns:
        Number of images downloaded
    """
    parser = KGParser(kg_path)
    downloader = ImageDownloader(output_dir)
    
    logger.info("Loading all ImageObjects from KG...")
    images = parser.get_all_image_objects()
    logger.info(f"Found {len(images)} images")
    
    output_path = Path(output_dir) / "all_images"
    downloaded = downloader.download_images(images, output_path, show_progress)
    
    return len(downloaded)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    kg_path = Path(__file__).parent.parent / "data" / "kg" / "imdb_kg_cleaned.ttl"
    output_dir = Path(__file__).parent.parent / "output"
    
    if len(sys.argv) > 1:
        entity_uri = sys.argv[1]
    else:
        entity_uri = "https://www.imdb.com/title/tt0120338"  # Titanic
    
    parser = KGParser(str(kg_path))
    media = parser.get_entity_media(entity_uri)
    
    downloader = ImageDownloader(str(output_dir))
    downloaded = downloader.download_entity_images(media)
    
    print(f"\nDownloaded {len(downloaded)} images to {output_dir / media.entity_id / 'images'}")


