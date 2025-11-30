"""
Music Linker - Find YouTube videos for movie soundtrack metadata.
"""

__version__ = "0.1.0"

from .models import (
    SoundtrackMetadata,
    YouTubeVideo,
    YouTubeComment,
    MatchScore,
    MusicLinkResult
)
from .youtube_client import YouTubeClient
from .gemini_matcher import GeminiMatcher
from .music_linker import MusicLinker
from .parser import SoundtrackParser
from .utils import Config, setup_logging

__all__ = [
    "SoundtrackMetadata",
    "YouTubeVideo",
    "YouTubeComment",
    "MatchScore",
    "MusicLinkResult",
    "YouTubeClient",
    "GeminiMatcher",
    "MusicLinker",
    "SoundtrackParser",
    "Config",
    "setup_logging",
]
