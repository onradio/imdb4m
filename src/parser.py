"""
Parser for IMDb soundtrack metadata.
"""
from typing import List, Optional
import re
from .models import SoundtrackMetadata


class SoundtrackParser:
    """Parser for IMDb soundtrack text format."""
    
    @staticmethod
    def parse_soundtrack_text(text: str, movie_title: Optional[str] = None) -> List[SoundtrackMetadata]:
        """
        Parse IMDb soundtrack text into structured metadata.
        
        Args:
            text: Raw soundtrack text from IMDb
            movie_title: Optional movie title to add context
            
        Returns:
            List of SoundtrackMetadata objects
        """
        soundtracks = []
        lines = text.strip().split('\n')
        
        current_title = None
        current_data = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this is a new song title (first line, not starting with metadata keywords)
            if not any(line.startswith(prefix) for prefix in [
                'Music by', 'Lyrics by', 'Written by', 'Performed by', 
                'Produced by', 'Arranged by', 'includes', 'Celine Dion',
                'by ', '(uncredited)'
            ]):
                # Save previous entry if exists
                if current_title:
                    soundtrack = SoundtrackParser._create_soundtrack(
                        current_title, current_data, movie_title
                    )
                    soundtracks.append(soundtrack)
                
                # Start new entry
                current_title = line
                current_data = {}
                current_data['is_uncredited'] = False
            
            # Parse metadata lines
            elif line.startswith('Music by'):
                current_data['composer'] = SoundtrackParser._extract_name(line, 'Music by')
            elif line.startswith('Lyrics by'):
                current_data['lyrics_by'] = SoundtrackParser._extract_name(line, 'Lyrics by')
            elif line.startswith('Written by'):
                current_data['composer'] = SoundtrackParser._extract_name(line, 'Written by')
            elif line.startswith('Performed by') or line.startswith('Performed &'):
                current_data['performer'] = SoundtrackParser._extract_name(line, 'Performed')
            elif line.startswith('Produced by') or line.startswith('Produced and'):
                current_data['producer'] = SoundtrackParser._extract_name(line, 'Produced')
            elif line.startswith('by ') and 'composer' not in current_data:
                # "by Author Name" format
                current_data['composer'] = SoundtrackParser._extract_name(line, 'by')
            elif '(uncredited)' in line:
                current_data['is_uncredited'] = True
                if not current_data.get('additional_info'):
                    current_data['additional_info'] = line
                else:
                    current_data['additional_info'] += ' ' + line
            elif line.startswith('includes') or 'Traditional' in line:
                if not current_data.get('additional_info'):
                    current_data['additional_info'] = line
                else:
                    current_data['additional_info'] += ' ' + line
                if 'Traditional' in line:
                    current_data['is_traditional'] = True
            else:
                # Additional info
                if not current_data.get('additional_info'):
                    current_data['additional_info'] = line
                else:
                    current_data['additional_info'] += ' ' + line
        
        # Don't forget the last entry
        if current_title:
            soundtrack = SoundtrackParser._create_soundtrack(
                current_title, current_data, movie_title
            )
            soundtracks.append(soundtrack)
        
        return soundtracks
    
    @staticmethod
    def _extract_name(line: str, prefix: str) -> str:
        """Extract name from a metadata line."""
        # Remove prefix
        if prefix in line:
            name = line.split(prefix, 1)[1].strip()
        else:
            name = line.strip()
        
        # Clean up common patterns
        name = re.sub(r'\s*\(as [^)]+\)', '', name)  # Remove "(as ...)"
        name = re.sub(r'\s+and Arranged.*', '', name)  # Remove "and Arranged by"
        name = re.sub(r'\s+and.*', '', name)  # Remove "and ..."
        name = re.sub(r'\s*&.*', '', name)  # Remove "& ..."
        
        return name.strip()
    
    @staticmethod
    def _create_soundtrack(
        title: str, 
        data: dict, 
        movie_title: Optional[str]
    ) -> SoundtrackMetadata:
        """Create a SoundtrackMetadata object from parsed data."""
        return SoundtrackMetadata(
            title=title,
            composer=data.get('composer'),
            lyrics_by=data.get('lyrics_by'),
            performer=data.get('performer'),
            producer=data.get('producer'),
            movie_title=movie_title,
            additional_info=data.get('additional_info'),
            is_traditional=data.get('is_traditional', False),
            is_uncredited=data.get('is_uncredited', False)
        )
