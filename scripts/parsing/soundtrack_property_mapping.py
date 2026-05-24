"""
Comprehensive mapping of IMDb soundtrack property labels to schema.org properties.

Based on analysis of 376 soundtrack HTML files.

Schema.org structure:
- MusicRecording (the specific recording)
  - schema:byArtist -> performer
  - schema:producer -> producer
  
- MusicComposition (the underlying composition)
  - schema:composer -> composer (music)
  - schema:lyricist -> lyricist (words/lyrics)
  - schema:author -> author (for older songs where distinction is unclear)
"""

from typing import Dict, List, Tuple, Optional
import re

# =============================================================================
# PROPERTY MAPPING
# =============================================================================

# Maps IMDb labels to schema.org properties
# Priority order matters - more specific patterns should come first

PROPERTY_MAPPING: Dict[str, List[str]] = {
    # -------------------------------------------------------------------------
    # COMPOSER variations -> schema:composer (on MusicComposition)
    # For the person who wrote the MUSIC
    # -------------------------------------------------------------------------
    'composer': [
        'Music by',
        'Composed by',
        'Music Composed by',
        'Music Written by',
        'Score by',
        'Score Composed by',
        'Original Music by',
        'Original Music Composed by',
        'Original Music Written by',
        'Music Composed and Performed by',  # Extract composer
        'Music Composed and Produced by',   # Extract composer
        'Music Composed and Arranged by',   # Extract composer
        'Music and Lyrics by',              # Maps to BOTH composer and lyricist
        'Words and Music by',               # Maps to BOTH composer and lyricist
        'Music and Words by',               # Maps to BOTH composer and lyricist
        'Music and Spanish Lyrics by',      # Maps to composer (+ lyricist)
        'Adaptation and Music by',          # Extract composer
    ],
    
    # -------------------------------------------------------------------------
    # LYRICIST variations -> schema:lyricist (on MusicComposition)
    # For the person who wrote the WORDS/LYRICS
    # -------------------------------------------------------------------------
    'lyricist': [
        'Lyrics by',
        'Lyricist',
        'Words by',
        'Lyrics Written by',
        'Lyric by',
        'English Lyrics by',
        'French Lyrics by',
        'German Lyrics by',
        'Italian Lyrics by',
        'Spanish Lyrics by',
        'Sicilian Lyrics by',
        'Latin Lyrics by',
        'American Lyrics by',
        'Huttese Lyrics by',        # Star Wars!
        'Ewokese Lyrics by',        # Star Wars!
        'Additional Lyrics by',
        'Original Lyrics by',
        'Original Lyrics Written by',
        'English Version Lyrics by',
        'Libretto by',              # Opera/musical lyrics
        'Text by',                  # For classical/religious works
    ],
    
    # -------------------------------------------------------------------------
    # AUTHOR variations -> schema:author (on MusicComposition)
    # For older songs, traditional works, or when composer/lyricist unclear
    # -------------------------------------------------------------------------
    'author': [
        'Written by',               # Primary - often used for both music+lyrics
        'Song Written by',
        'Written and Composed by',  # Same as written by
        'Composed and Written by',  # Same as written by
        'By',                       # Common short form
        'Original Music and Lyrics by',
    ],
    
    # -------------------------------------------------------------------------
    # PERFORMER variations -> schema:byArtist (on MusicRecording)
    # The person/group performing the recording
    # -------------------------------------------------------------------------
    'byArtist': [
        'Performed by',
        'Sung by',
        'Vocals by',
        'Vocal by',
        'Vocalist',
        'Singer',
        'Artist',
        'Performer',
        'Additional Vocals by',
        'Background Vocals by',
        'Background Choir Vocals by',
        'Featuring Vocals by',
        'Featuring Vocal Performances by',
        'Vocal Performance by',
        'Sung A Cappella by',
        'Sung A Cappella Offscreen by',
        'Sung Briefly by',
        'Excerpts Sung by',
        'Hummed by',
        'Whistled by',
        'Chants by',
        'Recited by',
        'Played by',
        'Piano Solo by',
        'Guitar Solo by',
        'Cello by',
        'Violin by',
        'Guitar by',
        'Guitars by',
        'Saxophone by',
        'Sitar by',
        'Pan Flute Performed by',
        'Piano Performed by',
        'Solos by',
        'Originally Performed by',
        'Also Performed by',
        'As Performed by',
        'Parody Version Performed by',
        'Instrumental Version Performed by',
        'Disney Version Performed by',
        'Streamline Version Performed by',
        'African Vocals Performed by',
        'End Title Performance by',
        'String Quartet Performed by',
        'Performed on Original Instruments by',
        'Music Performed by',
        'Danced by',
        'Squawked by',  # Yes, this exists!
        'Dholak by',    # Indian drum performer
    ],
    
    # -------------------------------------------------------------------------
    # PRODUCER variations -> schema:producer (on MusicRecording)
    # -------------------------------------------------------------------------
    'producer': [
        'Produced by',
        'Producer',
        'Music Produced by',
        'Record Produced by',
        'Executive Produced by',
        'Additional Music Produced by',
        'Sessions Produced by',
        'Recorded and Produced by',
    ],
    
    # -------------------------------------------------------------------------
    # ARRANGER variations -> could use schema:contributor or custom property
    # -------------------------------------------------------------------------
    'arranger': [
        'Arranged by',
        'Arrangement by',
        'Arrangements by',
        'Choir Arranged by',
        'Strings Arranged by',
        'Arranged for Harp by',
        'Traditional Arrangement by',
        'Master Arranged by',
        'Adapted and Arranged by',
        'Transcribed and Arranged by',
        'As Arranged by',
    ],
    
    # -------------------------------------------------------------------------
    # CONDUCTOR variations -> could use schema:contributor or custom property
    # -------------------------------------------------------------------------
    'conductor': [
        'Conducted by',
        'Conductor',
        'Orchestra Conducted by',
        'String Orchestra Conducted by',
        'String Section Conducted by',
    ],
    
    # -------------------------------------------------------------------------
    # ORCHESTRATOR variations -> could use schema:contributor
    # -------------------------------------------------------------------------
    'orchestrator': [
        'Orchestrated by',
        'Orchestration by',
        'Orchestrations by',
    ],
    
    # -------------------------------------------------------------------------
    # AUDIO ENGINEER variations -> schema:contributor
    # -------------------------------------------------------------------------
    'engineer': [
        'Mixed by',
        'Song Mixed by',
        'Engineered by',
        'Engineering by',
        'Recorded by',
        'Recorded and Mixed by',
        'Mixing and Mastering by',
        'Programmed and Mixed by',
        'Mixed and Edited by',
        'Remixed by',
        'Programmed by',
    ],
    
    # -------------------------------------------------------------------------
    # RIGHTS/PUBLISHING (informational, not creative roles)
    # These don't map to schema.org creative properties
    # -------------------------------------------------------------------------
    'publisher': [
        'Published by',
        'Originally Published by',
        'Copyright by',
    ],
    
    'rights_administrator': [
        'Administered by',
        'All Rights Administered by',
        'Rights Administered by',
        'Rights Controlled and Administered by',
        'Worldwide Rights Administered by',
        'Administered for the World by',
    ],
    
    'license': [
        'Licensed by',
        'Under License by',
        'Courtesy of',
        'Courtesy by',
        'By Arrangement with',
        'License Arranged by',
        'Used by',
        'Provided by',
        'And Licensed by',
    ],
}

# =============================================================================
# COMPOUND ROLE MAPPING
# These labels indicate multiple roles for the same person
# =============================================================================

COMPOUND_ROLES: Dict[str, List[str]] = {
    # Label -> list of roles the person holds
    'Written and Performed by': ['author', 'byArtist'],
    'Composed and Performed by': ['composer', 'byArtist'],
    'Written and Produced by': ['author', 'producer'],
    'Produced and Performed by': ['producer', 'byArtist'],
    'Performed and Produced by': ['byArtist', 'producer'],
    'Arranged and Performed by': ['arranger', 'byArtist'],
    'Arranged and Conducted by': ['arranger', 'conductor'],
    'Arranged and Produced by': ['arranger', 'producer'],
    'Arranged and Orchestrated by': ['arranger', 'orchestrator'],
    'Composed and Arranged by': ['composer', 'arranger'],
    'Written and Conducted by': ['author', 'conductor'],
    'Conducted and Written by': ['conductor', 'author'],
    'Performed and Arranged by': ['byArtist', 'arranger'],
    'Written and Sung by': ['author', 'byArtist'],
    'Produced and Mixed by': ['producer', 'engineer'],
    'Produced and Arranged by': ['producer', 'arranger'],
    'Produced and Written by': ['producer', 'author'],
    'Produced and Recorded Binaurally by': ['producer', 'engineer'],
    'Composed and Recorded by': ['composer', 'engineer'],
    'Written and Recorded by': ['author', 'engineer'],
    'Music and Lyrics by': ['composer', 'lyricist'],
    'Words and Music by': ['lyricist', 'composer'],
    'Music and Words by': ['composer', 'lyricist'],
    'Lyrics and Music by': ['lyricist', 'composer'],
    'Original Music and Lyrics by': ['composer', 'lyricist'],
    'Song and Words by': ['composer', 'lyricist'],
    'Arranged and Additional Lyrics by': ['arranger', 'lyricist'],
    'Performed and Written by': ['byArtist', 'author'],
    'Music and Performed by': ['composer', 'byArtist'],
}

# =============================================================================
# SCHEMA.ORG MAPPING
# Maps our internal categories to schema.org properties
# =============================================================================

SCHEMA_ORG_MAPPING = {
    # MusicRecording properties
    'byArtist': ('MusicRecording', 'schema:byArtist'),
    'producer': ('MusicRecording', 'schema:producer'),
    
    # MusicComposition properties
    'composer': ('MusicComposition', 'schema:composer'),
    'lyricist': ('MusicComposition', 'schema:lyricist'),
    'author': ('MusicComposition', 'schema:author'),
    
    # These could use schema:contributor or custom extensions
    'arranger': ('MusicRecording', 'schema:contributor'),  # or custom
    'conductor': ('MusicRecording', 'schema:contributor'),  # or custom
    'orchestrator': ('MusicRecording', 'schema:contributor'),  # or custom
    'engineer': ('MusicRecording', 'schema:contributor'),  # or custom
    
    # Non-creative roles (informational only)
    'publisher': None,  # Not a creative role
    'rights_administrator': None,
    'license': None,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def normalize_label(label: str) -> str:
    """Normalize a label for comparison."""
    return ' '.join(label.split()).lower().strip()


def categorize_label(label: str) -> Tuple[Optional[str], bool, bool]:
    """
    Categorize a label into schema.org property categories.
    
    Returns:
        Tuple of (category, is_matched, is_compound)
    """
    normalized = normalize_label(label)
    
    # First check compound roles
    for compound_label, roles in COMPOUND_ROLES.items():
        if normalize_label(compound_label) == normalized:
            return roles[0], True, True  # Return primary role, matched, is compound
    
    # Then check single-role mappings
    for category, known_labels in PROPERTY_MAPPING.items():
        for known in known_labels:
            known_normalized = normalize_label(known)
            if known_normalized == normalized:
                return category, True, False
            # Also check if label starts with known pattern
            if normalized.startswith(known_normalized):
                return category, True, False
    
    return None, False, False


def get_compound_roles(label: str) -> List[str]:
    """
    Get all roles for a compound label.
    
    Returns:
        List of role categories, or empty list if not compound
    """
    normalized = normalize_label(label)
    
    for compound_label, roles in COMPOUND_ROLES.items():
        if normalize_label(compound_label) == normalized:
            return roles
    
    return []


def get_schema_property(category: str) -> Optional[Tuple[str, str]]:
    """
    Get the schema.org class and property for a category.
    
    Returns:
        Tuple of (class_name, property_name) or None
    """
    return SCHEMA_ORG_MAPPING.get(category)


def extract_label_from_text(text: str) -> List[str]:
    """
    Extract property labels from free text.
    
    Args:
        text: Raw text containing "Label by Name" patterns
        
    Returns:
        List of extracted labels
    """
    # Common pattern: "Something by Name"
    pattern = r'([A-Za-z\s]+(?:by|By))'
    matches = re.findall(pattern, text)
    
    labels = []
    for match in matches:
        label = match.strip()
        if label and len(label) > 3:  # Filter out very short matches
            labels.append(label)
    
    return labels


# =============================================================================
# SUMMARY STATISTICS
# =============================================================================

def print_mapping_summary():
    """Print a summary of the property mapping."""
    print("="*60)
    print("IMDB SOUNDTRACK PROPERTY MAPPING SUMMARY")
    print("="*60)
    print()
    
    print("SINGLE-ROLE MAPPINGS:")
    print("-"*40)
    for category, labels in PROPERTY_MAPPING.items():
        schema_info = get_schema_property(category)
        if schema_info:
            class_name, prop_name = schema_info
            print(f"\n{category} -> {prop_name} (on {class_name})")
        else:
            print(f"\n{category} -> (informational only)")
        for label in labels[:5]:  # Show first 5
            print(f"    - {label}")
        if len(labels) > 5:
            print(f"    ... and {len(labels) - 5} more")
    
    print()
    print("COMPOUND-ROLE MAPPINGS:")
    print("-"*40)
    for label, roles in list(COMPOUND_ROLES.items())[:10]:
        print(f"  {label} -> {', '.join(roles)}")
    if len(COMPOUND_ROLES) > 10:
        print(f"  ... and {len(COMPOUND_ROLES) - 10} more")
    
    print()
    print("TOTAL COVERAGE:")
    print("-"*40)
    total_single = sum(len(labels) for labels in PROPERTY_MAPPING.values())
    total_compound = len(COMPOUND_ROLES)
    print(f"  Single-role labels: {total_single}")
    print(f"  Compound-role labels: {total_compound}")
    print(f"  Total: {total_single + total_compound}")


if __name__ == '__main__':
    print_mapping_summary()

