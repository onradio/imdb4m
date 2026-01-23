"""
Video Downloader for IMDB4M Knowledge Graph.

Uses Selenium to extract video URLs from IMDB video pages and downloads them.
"""

import logging
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

from .kg_parser import KGParser, VideoInfo, EntityMedia

logger = logging.getLogger(__name__)

# Default headers for downloading videos
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.imdb.com/',
}


class VideoDownloader:
    """Downloads videos from IMDB using Selenium to extract video URLs."""

    def __init__(
        self,
        output_dir: str = "output",
        headless: bool = True,
        timeout: int = 30,
        download_timeout: int = 300,
    ):
        """
        Initialize the video downloader.

        Args:
            output_dir: Base directory for downloaded files
            headless: Whether to run browser in headless mode
            timeout: Selenium wait timeout in seconds
            download_timeout: Download timeout in seconds
        """
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.driver: Optional[webdriver.Chrome] = None
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _init_driver(self) -> None:
        """Initialize the Chrome WebDriver."""
        if self.driver is not None:
            return
        
        options = Options()
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Disable automation flags
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Remove webdriver flag
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })

    def _close_driver(self) -> None:
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _extract_video_url(self, embed_url: str) -> Optional[str]:
        """
        Extract the actual video URL from an IMDB video page.

        Args:
            embed_url: The IMDB video page URL

        Returns:
            The direct video URL, or None if extraction failed
        """
        self._init_driver()
        
        try:
            logger.debug(f"Loading video page: {embed_url}")
            self.driver.get(embed_url)
            
            # Wait for the page to load
            time.sleep(2)
            
            # Try to find video element
            wait = WebDriverWait(self.driver, self.timeout)
            
            # Method 1: Look for video tag with source
            try:
                video_elem = wait.until(
                    EC.presence_of_element_located((By.TAG_NAME, "video"))
                )
                
                # Check for src attribute
                video_src = video_elem.get_attribute('src')
                if video_src and video_src.startswith('http'):
                    logger.debug(f"Found video src: {video_src[:60]}...")
                    return video_src
                
                # Check for source child elements
                sources = video_elem.find_elements(By.TAG_NAME, "source")
                for source in sources:
                    src = source.get_attribute('src')
                    if src and src.startswith('http'):
                        logger.debug(f"Found source src: {src[:60]}...")
                        return src
                        
            except TimeoutException:
                logger.debug("No video element found directly")
            
            # Method 2: Look in page source for video URLs
            page_source = self.driver.page_source
            
            # Pattern for IMDB video URLs
            patterns = [
                r'"playbackURLs":\s*\[\s*{\s*"videoMimeType":\s*"video/mp4",\s*"url":\s*"([^"]+)"',
                r'"url":\s*"(https://[^"]*\.mp4[^"]*)"',
                r'(https://imdb-video\.media-imdb\.com/[^"\'>\s]+\.mp4[^"\'>\s]*)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_source)
                if matches:
                    # Get the highest quality URL (usually first or largest)
                    for match in matches:
                        url = match.replace('\\u0026', '&')
                        if '.mp4' in url:
                            logger.debug(f"Found video URL via regex: {url[:60]}...")
                            return url
            
            # Method 3: Check network requests via performance log
            try:
                # Execute JavaScript to find video URLs in performance entries
                script = """
                    var entries = performance.getEntriesByType('resource');
                    var videos = entries.filter(e => e.name.includes('.mp4') || e.name.includes('video'));
                    return videos.map(v => v.name);
                """
                video_urls = self.driver.execute_script(script)
                for url in video_urls:
                    if '.mp4' in url:
                        return url
            except Exception as e:
                logger.debug(f"Performance log check failed: {e}")
            
            logger.warning(f"Could not extract video URL from {embed_url}")
            return None
            
        except WebDriverException as e:
            logger.error(f"WebDriver error for {embed_url}: {e}")
            return None

    def _get_filename_from_video_info(self, video_info: VideoInfo) -> str:
        """Generate a filename from video info."""
        # Extract video ID from URI
        video_id = video_info.uri.split('/')[-1] or video_info.uri.split('/')[-2]
        
        # Clean up name for filename
        name = video_info.name or "video"
        name = re.sub(r'[^\w\-_\s]', '', name)
        name = name.replace(' ', '_')[:50]
        
        return f"{video_id}_{name}.mp4"

    def download_video(
        self,
        video_url: str,
        output_path: Path,
        filename: str,
    ) -> Optional[Path]:
        """
        Download a video from a direct URL.

        Args:
            video_url: The direct video URL
            output_path: Directory to save the video
            filename: Filename for the video

        Returns:
            Path to the downloaded file, or None if download failed
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        file_path = output_path / filename
        
        # Skip if already downloaded
        if file_path.exists():
            logger.debug(f"Skipping (exists): {filename}")
            return file_path
        
        try:
            logger.info(f"Downloading video: {filename}")
            
            response = self.session.get(
                video_url,
                timeout=self.download_timeout,
                stream=True
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(file_path, 'wb') as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename[:30]) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            logger.info(f"Downloaded: {filename}")
            return file_path
            
        except requests.RequestException as e:
            logger.error(f"Failed to download video {filename}: {e}")
            # Clean up partial download
            if file_path.exists():
                file_path.unlink()
            return None

    def download_from_imdb(
        self,
        video_info: VideoInfo,
        output_path: Path,
    ) -> Optional[Path]:
        """
        Extract and download a video from an IMDB video page.

        Args:
            video_info: VideoInfo object with embed URL
            output_path: Directory to save the video

        Returns:
            Path to the downloaded file, or None if failed
        """
        # Extract the actual video URL
        video_url = self._extract_video_url(video_info.embed_url)
        
        if not video_url:
            logger.warning(f"Could not extract video URL for: {video_info.name}")
            return None
        
        filename = self._get_filename_from_video_info(video_info)
        return self.download_video(video_url, output_path, filename)

    def download_videos(
        self,
        videos: List[VideoInfo],
        output_path: Path,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download multiple videos.

        Args:
            videos: List of VideoInfo objects
            output_path: Directory to save videos
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded videos
        """
        downloaded = []
        
        try:
            iterator = tqdm(videos, desc="Downloading videos", disable=not show_progress)
            for video in iterator:
                iterator.set_postfix_str(video.name[:20] if video.name else "")
                result = self.download_from_imdb(video, output_path)
                if result:
                    downloaded.append(result)
        finally:
            self._close_driver()
        
        return downloaded

    def download_entity_videos(
        self,
        entity_media: EntityMedia,
        base_output_dir: Optional[Path] = None,
        show_progress: bool = True,
    ) -> List[Path]:
        """
        Download all videos for an entity.

        Args:
            entity_media: EntityMedia object containing video information
            base_output_dir: Base output directory (defaults to self.output_dir)
            show_progress: Whether to show a progress bar

        Returns:
            List of paths to successfully downloaded videos
        """
        if base_output_dir is None:
            base_output_dir = self.output_dir
        
        output_path = base_output_dir / entity_media.entity_id / "videos"
        
        logger.info(f"Downloading {len(entity_media.videos)} videos for {entity_media.entity_id}")
        return self.download_videos(entity_media.videos, output_path, show_progress)

    def __del__(self):
        """Cleanup WebDriver on destruction."""
        self._close_driver()


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
    
    if media.videos:
        downloader = VideoDownloader(str(output_dir), headless=True)
        downloaded = downloader.download_entity_videos(media)
        print(f"\nDownloaded {len(downloaded)} videos to {output_dir / media.entity_id / 'videos'}")
    else:
        print(f"No videos found for {entity_uri}")


