"""
KG Parser for extracting media URLs from IMDB4M Knowledge Graph.

Parses TTL files using rdflib to extract:
- Image URLs (schema:ImageObject)
- Video embed URLs (schema:VideoObject)
- YouTube URLs from soundtrack_links.json files
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF

logger = logging.getLogger(__name__)

# Define namespaces
SCHEMA = Namespace("http://schema.org/")
SCHEMA1 = Namespace("http://schema.org/")  # Some files use schema1: prefix


@dataclass
class ImageInfo:
    """Information about an image from the KG."""
    uri: str  # The ImageObject URI (e.g., mediaviewer URL)
    url: str  # The actual image URL (Amazon CDN)
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class VideoInfo:
    """Information about a video from the KG."""
    uri: str  # The VideoObject URI
    embed_url: str  # The IMDB video page URL
    name: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None


@dataclass
class AudioInfo:
    """Information about an audio track from the KG."""
    title: str
    youtube_url: str
    performer: Optional[str] = None
    composer: Optional[str] = None
    video_id: Optional[str] = None


@dataclass
class EntityMedia:
    """All media associated with an entity."""
    entity_uri: str
    entity_id: str  # e.g., tt0120338 or nm0000138
    entity_type: str  # 'movie' or 'person'
    images: List[ImageInfo] = field(default_factory=list)
    videos: List[VideoInfo] = field(default_factory=list)
    audio: List[AudioInfo] = field(default_factory=list)


class KGParser:
    """Parser for extracting media information from IMDB4M Knowledge Graph."""

    def __init__(self, kg_path: str, data_dir: Optional[str] = None):
        """
        Initialize the KG parser.

        Args:
            kg_path: Path to the main KG TTL file (imdb_kg_cleaned.ttl)
            data_dir: Path to the data directory containing movie/sample folders
                      with soundtrack_links.json files. If None, inferred from kg_path.
        """
        self.kg_path = Path(kg_path)
        self.data_dir = Path(data_dir) if data_dir else self.kg_path.parent.parent
        self.graph: Optional[Graph] = None
        self._loaded = False

    def load_graph(self) -> None:
        """Load the KG into memory. This may take a while for large files."""
        if self._loaded:
            return
        
        logger.info(f"Loading KG from {self.kg_path}...")
        self.graph = Graph()
        self.graph.parse(self.kg_path, format="turtle")
        self._loaded = True
        logger.info(f"Loaded {len(self.graph)} triples")

    def _extract_entity_id(self, uri: str) -> tuple[str, str]:
        """
        Extract entity ID and type from URI.
        
        Args:
            uri: Entity URI (e.g., https://www.imdb.com/title/tt0120338)
            
        Returns:
            Tuple of (entity_id, entity_type)
        """
        # Handle both with and without trailing slash
        uri = uri.rstrip('/')
        
        if '/title/' in uri:
            match = re.search(r'/title/(tt\d+)', uri)
            if match:
                return match.group(1), 'movie'
        elif '/name/' in uri:
            match = re.search(r'/name/(nm\d+)', uri)
            if match:
                return match.group(1), 'person'
        
        raise ValueError(f"Cannot extract entity ID from URI: {uri}")

    def get_entity_media(self, entity_uri: str) -> EntityMedia:
        """
        Get all media associated with an entity.

        Args:
            entity_uri: The entity URI (e.g., https://www.imdb.com/title/tt0120338)

        Returns:
            EntityMedia object containing all associated media
        """
        self.load_graph()
        
        entity_id, entity_type = self._extract_entity_id(entity_uri)
        
        # Try both with and without trailing slash since KG may use either
        entity_ref_no_slash = URIRef(entity_uri.rstrip('/'))
        entity_ref_with_slash = URIRef(entity_uri.rstrip('/') + '/')
        
        media = EntityMedia(
            entity_uri=entity_uri,
            entity_id=entity_id,
            entity_type=entity_type
        )
        
        # Get images (try both URI variants)
        media.images = self._get_images(entity_ref_no_slash)
        if not media.images:
            media.images = self._get_images(entity_ref_with_slash)
        
        # Get videos (try both URI variants)
        media.videos = self._get_videos(entity_ref_no_slash)
        if not media.videos:
            media.videos = self._get_videos(entity_ref_with_slash)
        
        # Get audio (from soundtrack_links.json if available)
        media.audio = self._get_audio(entity_id)
        
        return media

    def _get_images(self, entity_ref: URIRef) -> List[ImageInfo]:
        """Extract image information for an entity."""
        images = []
        seen_urls = set()
        
        # Query for images linked to this entity via schema:image
        for image_uri in self.graph.objects(entity_ref, SCHEMA.image):
            image_info = self._parse_image_object(image_uri)
            if image_info and image_info.url not in seen_urls:
                images.append(image_info)
                seen_urls.add(image_info.url)
        
        # Also check for thumbnail (direct image URL)
        for thumbnail in self.graph.objects(entity_ref, SCHEMA.thumbnail):
            url = str(thumbnail)
            if url.startswith('http') and url not in seen_urls:
                images.append(ImageInfo(
                    uri=url,
                    url=url,
                    caption="Thumbnail"
                ))
                seen_urls.add(url)
        
        # If no images found via direct links, search for ImageObjects
        # whose URI contains the entity ID (e.g., nm0000138/mediaviewer/)
        if not images:
            entity_str = str(entity_ref)
            # Extract the entity path (e.g., /name/nm0000138 or /title/tt0120338)
            entity_pattern = entity_str.replace('https://www.imdb.com', '')
            
            # Search all ImageObjects for ones that reference this entity
            for image_uri in self.graph.subjects(RDF.type, SCHEMA.ImageObject):
                uri_str = str(image_uri)
                if entity_pattern in uri_str:
                    image_info = self._parse_image_object(image_uri)
                    if image_info and image_info.url not in seen_urls:
                        images.append(image_info)
                        seen_urls.add(image_info.url)
        
        return images

    def _parse_image_object(self, image_uri: URIRef) -> Optional[ImageInfo]:
        """Parse an ImageObject to extract its properties."""
        # Get the actual image URL
        url = None
        for obj in self.graph.objects(image_uri, SCHEMA.url):
            url = str(obj)
            break
        
        if not url:
            # The URI itself might be the URL
            uri_str = str(image_uri)
            if uri_str.startswith('https://m.media-amazon.com'):
                url = uri_str
        
        if not url:
            return None
        
        # Get caption
        caption = None
        for obj in self.graph.objects(image_uri, SCHEMA.caption):
            caption = str(obj)
            break
        
        # Get dimensions
        width = None
        height = None
        for obj in self.graph.objects(image_uri, SCHEMA.width):
            try:
                width = int(obj)
            except (ValueError, TypeError):
                pass
        for obj in self.graph.objects(image_uri, SCHEMA.height):
            try:
                height = int(obj)
            except (ValueError, TypeError):
                pass
        
        return ImageInfo(
            uri=str(image_uri),
            url=url,
            caption=caption,
            width=width,
            height=height
        )

    def _get_videos(self, entity_ref: URIRef) -> List[VideoInfo]:
        """Extract video information for an entity."""
        videos = []
        seen_urls = set()
        
        # Check schema:trailer for movies
        for video_uri in self.graph.objects(entity_ref, SCHEMA.trailer):
            video_info = self._parse_video_object(video_uri)
            if video_info and video_info.embed_url not in seen_urls:
                videos.append(video_info)
                seen_urls.add(video_info.embed_url)
        
        # Check schema:video for persons
        for video_uri in self.graph.objects(entity_ref, SCHEMA.video):
            video_info = self._parse_video_object(video_uri)
            if video_info and video_info.embed_url not in seen_urls:
                videos.append(video_info)
                seen_urls.add(video_info.embed_url)
        
        # If no videos found, check for VideoObjects that are linked
        # via mainEntity or that reference this entity in reviews/descriptions
        if not videos:
            entity_str = str(entity_ref)
            
            # Search all VideoObjects
            for video_uri in self.graph.subjects(RDF.type, SCHEMA.VideoObject):
                # Check if this video references our entity via mainEntity
                for main_entity in self.graph.objects(video_uri, SCHEMA.mainEntity):
                    if str(main_entity).rstrip('/') == entity_str.rstrip('/'):
                        video_info = self._parse_video_object(video_uri)
                        if video_info and video_info.embed_url not in seen_urls:
                            videos.append(video_info)
                            seen_urls.add(video_info.embed_url)
                        break
        
        return videos

    def _parse_video_object(self, video_uri: URIRef) -> Optional[VideoInfo]:
        """Parse a VideoObject to extract its properties."""
        uri_str = str(video_uri)
        
        # Get embed URL
        embed_url = None
        for obj in self.graph.objects(video_uri, SCHEMA.embedUrl):
            embed_url = str(obj)
            break
        
        if not embed_url:
            # The URI might be the embed URL
            if 'imdb.com/video/' in uri_str:
                embed_url = uri_str if uri_str.endswith('/') else uri_str + '/'
        
        if not embed_url:
            return None
        
        # Get name
        name = None
        for obj in self.graph.objects(video_uri, SCHEMA.name):
            name = str(obj)
            break
        
        # Get description
        description = None
        for obj in self.graph.objects(video_uri, SCHEMA.description):
            description = str(obj)
            break
        
        # Get thumbnail
        thumbnail_url = None
        for obj in self.graph.objects(video_uri, SCHEMA.thumbnailUrl):
            thumbnail_url = str(obj)
            break
        
        # Get duration
        duration = None
        for obj in self.graph.objects(video_uri, SCHEMA.duration):
            duration = str(obj)
            break
        
        return VideoInfo(
            uri=uri_str,
            embed_url=embed_url,
            name=name,
            description=description,
            thumbnail_url=thumbnail_url,
            duration=duration
        )

    def _get_audio(self, entity_id: str) -> List[AudioInfo]:
        """
        Extract audio information from soundtrack_links.json files.
        
        Args:
            entity_id: The entity ID (e.g., tt0120338)
            
        Returns:
            List of AudioInfo objects
        """
        audio_list = []
        
        # Look for soundtrack_links.json in possible locations
        possible_paths = [
            self.data_dir / "movies" / entity_id / "movie_soundtrack" / "soundtrack_links.json",
            self.data_dir / "sample" / entity_id / "movie_soundtrack" / "soundtrack_links.json",
        ]
        
        for json_path in possible_paths:
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        soundtrack_data = json.load(f)
                    
                    for item in soundtrack_data:
                        best_match = item.get('best_match', {})
                        if best_match and best_match.get('url'):
                            soundtrack = item.get('soundtrack', {})
                            audio_list.append(AudioInfo(
                                title=soundtrack.get('title', best_match.get('title', 'Unknown')),
                                youtube_url=best_match['url'],
                                performer=soundtrack.get('performer'),
                                composer=soundtrack.get('composer'),
                                video_id=best_match.get('video_id')
                            ))
                    
                    logger.info(f"Found {len(audio_list)} audio tracks in {json_path}")
                    break  # Found the file, no need to check other paths
                    
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Error parsing {json_path}: {e}")
        
        return audio_list

    def get_all_image_objects(self) -> List[ImageInfo]:
        """Get all ImageObject instances from the KG."""
        self.load_graph()
        
        images = []
        for image_uri in self.graph.subjects(RDF.type, SCHEMA.ImageObject):
            image_info = self._parse_image_object(image_uri)
            if image_info:
                images.append(image_info)
        
        return images

    def get_all_video_objects(self) -> List[VideoInfo]:
        """Get all VideoObject instances from the KG."""
        self.load_graph()
        
        videos = []
        for video_uri in self.graph.subjects(RDF.type, SCHEMA.VideoObject):
            video_info = self._parse_video_object(video_uri)
            if video_info:
                videos.append(video_info)
        
        return videos

    def get_all_youtube_urls(self) -> List[AudioInfo]:
        """
        Get all YouTube URLs from all soundtrack_links.json files.
        
        Returns:
            List of AudioInfo objects from all available soundtrack files
        """
        all_audio = []
        
        # Search in movies directory
        movies_dir = self.data_dir / "movies"
        if movies_dir.exists():
            for entity_dir in movies_dir.iterdir():
                if entity_dir.is_dir():
                    audio = self._get_audio(entity_dir.name)
                    all_audio.extend(audio)
        
        # Search in sample directory
        sample_dir = self.data_dir / "sample"
        if sample_dir.exists():
            for entity_dir in sample_dir.iterdir():
                if entity_dir.is_dir():
                    audio = self._get_audio(entity_dir.name)
                    all_audio.extend(audio)
        
        return all_audio


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Default KG path
    kg_path = Path(__file__).parent.parent / "data" / "kg" / "imdb_kg_cleaned.ttl"
    
    if len(sys.argv) > 1:
        entity_uri = sys.argv[1]
    else:
        entity_uri = "https://www.imdb.com/title/tt0120338"  # Titanic
    
    parser = KGParser(str(kg_path))
    
    print(f"\nGetting media for: {entity_uri}")
    media = parser.get_entity_media(entity_uri)
    
    print(f"\nEntity: {media.entity_id} ({media.entity_type})")
    print(f"Images: {len(media.images)}")
    for img in media.images[:3]:
        print(f"  - {img.caption or 'No caption'}: {img.url[:60]}...")
    
    print(f"\nVideos: {len(media.videos)}")
    for vid in media.videos:
        print(f"  - {vid.name}: {vid.embed_url}")
    
    print(f"\nAudio tracks: {len(media.audio)}")
    for aud in media.audio[:3]:
        print(f"  - {aud.title} by {aud.performer}: {aud.youtube_url}")

