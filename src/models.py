"""
Data models for the music linker pipeline.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class SoundtrackMetadata(BaseModel):
    """Represents metadata for a soundtrack entry from IMDb."""
    
    title: str = Field(..., description="Song title")
    composer: Optional[str] = Field(None, description="Composer or writer")
    lyrics_by: Optional[str] = Field(None, description="Lyricist")
    performer: Optional[str] = Field(None, description="Performing artist")
    producer: Optional[str] = Field(None, description="Producer")
    movie_title: Optional[str] = Field(None, description="Movie this soundtrack is from")
    additional_info: Optional[str] = Field(None, description="Additional context or notes")
    is_traditional: bool = Field(False, description="Whether the song is traditional")
    is_uncredited: bool = Field(False, description="Whether the entry is uncredited")
    
    def to_search_query(self) -> str:
        """Generate a search query for YouTube."""
        parts = []
        
        # Title is always included
        parts.append(self.title)
        
        # Add performer if available (most important for finding the right version)
        if self.performer:
            parts.append(self.performer)
        
        # Add movie context if available
        if self.movie_title:
            parts.append(f"from {self.movie_title}")
        
        return " ".join(parts)
    
    def to_context_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for LLM context."""
        return {
            "title": self.title,
            "composer": self.composer,
            "lyrics_by": self.lyrics_by,
            "performer": self.performer,
            "producer": self.producer,
            "movie_title": self.movie_title,
            "additional_info": self.additional_info,
            "is_traditional": self.is_traditional,
            "is_uncredited": self.is_uncredited,
        }


class YouTubeComment(BaseModel):
    """Represents a YouTube comment."""
    
    author: str
    text: str
    like_count: int = 0
    published_at: Optional[str] = None


class YouTubeVideo(BaseModel):
    """Represents a YouTube video with metadata."""
    
    video_id: str
    title: str
    url: str
    description: Optional[str] = None
    channel_title: Optional[str] = None
    published_at: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    duration: Optional[str] = None
    comments: List[YouTubeComment] = Field(default_factory=list)
    
    def get_url(self) -> str:
        """Get the full YouTube URL."""
        return f"https://www.youtube.com/watch?v={self.video_id}"


class MatchScore(BaseModel):
    """Represents the LLM's confidence score and reasoning for a match."""
    
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: str = Field(..., description="Explanation for the score")
    key_factors: List[str] = Field(default_factory=list, description="Key matching factors")
    concerns: List[str] = Field(default_factory=list, description="Potential concerns or mismatches")


class MusicLinkResult(BaseModel):
    """Final result of the music linking process."""
    
    soundtrack: SoundtrackMetadata
    best_match: Optional[YouTubeVideo] = None
    match_score: Optional[MatchScore] = None
    candidates: List[YouTubeVideo] = Field(default_factory=list)
    search_query: str
    timestamp: datetime = Field(default_factory=datetime.now)
    error: Optional[str] = None
    
    def is_successful(self) -> bool:
        """Check if a match was found."""
        return self.best_match is not None and self.error is None
