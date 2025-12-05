#!/usr/bin/env python3
"""
Parse IMDb soundtrack HTML files and generate TTL (Turtle) files
following the schema.org structure for MusicRecording and MusicComposition.
"""

import os
import re
import json
import html
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field

from soundtrack_property_mapping import (
    PROPERTY_MAPPING,
    COMPOUND_ROLES,
    normalize_label,
    get_compound_roles,
)


@dataclass
class Person:
    """Represents a person with IMDb ID and name."""
    id: str  # e.g., "nm0000138"
    name: str
    
    @property
    def uri(self) -> str:
        return f"https://www.imdb.com/name/{self.id}/"
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        return isinstance(other, Person) and self.id == other.id


@dataclass
class SoundtrackEntry:
    """Represents a single soundtrack entry."""
    title: str
    performers: List[Person] = field(default_factory=list)
    producers: List[Person] = field(default_factory=list)
    composers: List[Person] = field(default_factory=list)
    lyricists: List[Person] = field(default_factory=list)
    authors: List[Person] = field(default_factory=list)
    arrangers: List[Person] = field(default_factory=list)
    conductors: List[Person] = field(default_factory=list)


def extract_next_data(html_content: str) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    next_data_script = soup.find('script', id='__NEXT_DATA__')
    
    if not next_data_script:
        return None
    
    try:
        return json.loads(next_data_script.string)
    except json.JSONDecodeError:
        return None


def get_movie_id_from_path(filepath: Path) -> str:
    """Extract movie ID from file path."""
    # Path structure: .../tt#######/movie_soundtrack/tt#######_sound.html
    return filepath.stem.replace('_sound', '')


def extract_person_from_html(html_text: str) -> List[Person]:
    """
    Extract person ID and name from HTML text containing links.
    Example: '<a href="/name/nm0000138/">Leonardo DiCaprio</a>'
    """
    persons = []
    
    # Pattern to match IMDb name links
    pattern = r'<a[^>]*href="[^"]*(/name/(nm\d+))[^"]*"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html_text)
    
    for _, person_id, name in matches:
        # Clean up the name
        name = html.unescape(name.strip())
        if name and person_id:
            persons.append(Person(id=person_id, name=name))
    
    return persons


def categorize_label_to_role(label: str) -> List[str]:
    """
    Map a label to role categories.
    Returns list of roles (can be multiple for compound labels).
    """
    normalized = normalize_label(label)
    
    # First check compound roles
    compound_roles = get_compound_roles(label)
    if compound_roles:
        return compound_roles
    
    # Then check single-role mappings
    for category, known_labels in PROPERTY_MAPPING.items():
        for known in known_labels:
            known_normalized = normalize_label(known)
            if known_normalized == normalized or normalized.startswith(known_normalized):
                return [category]
    
    return []


def parse_soundtrack_item(item: dict) -> Optional[SoundtrackEntry]:
    """Parse a single soundtrack item from the JSON data."""
    # Get the track title - it's in 'rowTitle' field
    title_text = item.get('rowTitle', '') or item.get('text', '')
    if not title_text:
        return None
    
    # Clean up the title (remove HTML and quotes)
    title = html.unescape(title_text)
    title = re.sub(r'<[^>]+>', '', title)
    title = title.strip().strip('"').strip("'")
    
    if not title:
        return None
    
    entry = SoundtrackEntry(title=title)
    
    # Parse the list content for properties
    list_content = item.get('listContent', [])
    
    for content_item in list_content:
        if not isinstance(content_item, dict):
            continue
        
        # Get the HTML content which contains the label and linked persons
        html_text = content_item.get('html', '')
        if not html_text:
            continue
        
        # Extract the label (text before the first link or colon)
        # Pattern: "Label by <a href...>Name</a>"
        label_match = re.match(r'^([^<]+)', html_text)
        if not label_match:
            continue
        
        label = label_match.group(1).strip()
        
        # Get the roles for this label
        roles = categorize_label_to_role(label)
        
        if not roles:
            continue
        
        # Extract persons from the HTML
        persons = extract_person_from_html(html_text)
        
        # Assign persons to the appropriate role lists
        for role in roles:
            for person in persons:
                if role == 'byArtist' and person not in entry.performers:
                    entry.performers.append(person)
                elif role == 'producer' and person not in entry.producers:
                    entry.producers.append(person)
                elif role == 'composer' and person not in entry.composers:
                    entry.composers.append(person)
                elif role == 'lyricist' and person not in entry.lyricists:
                    entry.lyricists.append(person)
                elif role == 'author' and person not in entry.authors:
                    entry.authors.append(person)
                elif role == 'arranger' and person not in entry.arrangers:
                    entry.arrangers.append(person)
                elif role == 'conductor' and person not in entry.conductors:
                    entry.conductors.append(person)
    
    return entry


def parse_soundtrack_html(filepath: Path) -> Tuple[str, List[SoundtrackEntry]]:
    """
    Parse a soundtrack HTML file and extract all entries.
    
    Returns:
        Tuple of (movie_id, list of SoundtrackEntry objects)
    """
    movie_id = get_movie_id_from_path(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    next_data = extract_next_data(html_content)
    if not next_data:
        return movie_id, []
    
    # Navigate to the soundtrack items
    content_data = next_data.get('props', {}).get('pageProps', {}).get('contentData', {})
    section = content_data.get('section', {})
    items = section.get('items', [])
    
    entries = []
    for item in items:
        entry = parse_soundtrack_item(item)
        if entry:
            entries.append(entry)
    
    return movie_id, entries


def escape_ttl_string(s: str) -> str:
    """Escape a string for TTL format."""
    # Escape backslashes first, then quotes
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def generate_ttl(movie_id: str, entries: List[SoundtrackEntry]) -> str:
    """
    Generate TTL content for the soundtrack entries.
    """
    if not entries:
        return ""
    
    lines = []
    
    # Prefixes
    lines.append("@prefix schema: <http://schema.org/> .")
    lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
    lines.append("")
    lines.append("# " + "="*78)
    lines.append("# SOUNDTRACKS")
    lines.append("# " + "="*78)
    lines.append("")
    
    # Collect all unique persons for later definition
    all_persons: Set[Person] = set()
    
    # Movie URI
    movie_uri = f"<https://www.imdb.com/title/{movie_id}/>"
    
    # Start the schema:audio statement
    lines.append(f"{movie_uri} schema:audio")
    
    # Generate each soundtrack entry as a blank node
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        
        lines.append("    [")
        lines.append("        a schema:MusicRecording ;")
        lines.append(f'        schema:name "{escape_ttl_string(entry.title)}" ;')
        
        # Add performers (schema:byArtist)
        if entry.performers:
            all_persons.update(entry.performers)
            uris = [f"<{p.uri}>" for p in entry.performers]
            if len(uris) == 1:
                lines.append(f"        schema:byArtist {uris[0]} ; # {entry.performers[0].name}")
            else:
                # Multiple performers
                lines.append(f"        schema:byArtist {uris[0]}, # {entry.performers[0].name}")
                for j, (uri, person) in enumerate(zip(uris[1:], entry.performers[1:])):
                    if j == len(uris) - 2:
                        lines.append(f"                        {uri} ; # {person.name}")
                    else:
                        lines.append(f"                        {uri}, # {person.name}")
        
        # Add producers (schema:producer)
        if entry.producers:
            all_persons.update(entry.producers)
            uris = [f"<{p.uri}>" for p in entry.producers]
            if len(uris) == 1:
                lines.append(f"        schema:producer {uris[0]} ; # {entry.producers[0].name}")
            else:
                lines.append(f"        schema:producer {uris[0]}, # {entry.producers[0].name}")
                for j, (uri, person) in enumerate(zip(uris[1:], entry.producers[1:])):
                    if j == len(uris) - 2:
                        lines.append(f"                       {uri} ; # {person.name}")
                    else:
                        lines.append(f"                       {uri}, # {person.name}")
        
        # Check if we have composition-level properties
        has_composition = entry.composers or entry.lyricists or entry.authors
        
        if has_composition:
            lines.append("        schema:recordingOf")
            lines.append("        [")
            lines.append("            a schema:MusicComposition ;")
            lines.append(f'            schema:name "{escape_ttl_string(entry.title)}" ;')
            
            # Add composers
            if entry.composers:
                all_persons.update(entry.composers)
                uris = [f"<{p.uri}>" for p in entry.composers]
                if len(uris) == 1:
                    suffix = " ;" if entry.lyricists or entry.authors else ""
                    lines.append(f"            schema:composer {uris[0]}{suffix} # {entry.composers[0].name}")
                else:
                    lines.append(f"            schema:composer {uris[0]}, # {entry.composers[0].name}")
                    for j, (uri, person) in enumerate(zip(uris[1:], entry.composers[1:])):
                        is_last_composer = j == len(uris) - 2
                        suffix = " ;" if (entry.lyricists or entry.authors) and is_last_composer else ""
                        if is_last_composer:
                            lines.append(f"                        {uri}{suffix} # {person.name}")
                        else:
                            lines.append(f"                        {uri}, # {person.name}")
            
            # Add lyricists
            if entry.lyricists:
                all_persons.update(entry.lyricists)
                uris = [f"<{p.uri}>" for p in entry.lyricists]
                if len(uris) == 1:
                    suffix = " ;" if entry.authors else ""
                    lines.append(f"            schema:lyricist {uris[0]}{suffix} # {entry.lyricists[0].name}")
                else:
                    lines.append(f"            schema:lyricist {uris[0]}, # {entry.lyricists[0].name}")
                    for j, (uri, person) in enumerate(zip(uris[1:], entry.lyricists[1:])):
                        is_last_lyricist = j == len(uris) - 2
                        suffix = " ;" if entry.authors and is_last_lyricist else ""
                        if is_last_lyricist:
                            lines.append(f"                        {uri}{suffix} # {person.name}")
                        else:
                            lines.append(f"                        {uri}, # {person.name}")
            
            # Add authors
            if entry.authors:
                all_persons.update(entry.authors)
                uris = [f"<{p.uri}>" for p in entry.authors]
                if len(uris) == 1:
                    lines.append(f"            schema:author {uris[0]} # {entry.authors[0].name}")
                else:
                    lines.append(f"            schema:author {uris[0]}, # {entry.authors[0].name}")
                    for j, (uri, person) in enumerate(zip(uris[1:], entry.authors[1:])):
                        if j == len(uris) - 2:
                            lines.append(f"                       {uri} # {person.name}")
                        else:
                            lines.append(f"                       {uri}, # {person.name}")
            
            lines.append("        ] ;")
        
        # Close the MusicRecording blank node
        if is_last:
            lines.append("    ] .")
        else:
            lines.append("    ],")
    
    # Add person definitions
    lines.append("")
    lines.append("# --- Define People (Composers, Performers, etc.) ---")
    lines.append("")
    
    # Sort persons by ID for consistent output
    sorted_persons = sorted(all_persons, key=lambda p: p.id)
    
    for person in sorted_persons:
        lines.append(f"<{person.uri}> a schema:Person ;")
        lines.append(f'    schema:name "{escape_ttl_string(person.name)}" .')
    
    lines.append("# " + "="*78)
    
    return '\n'.join(lines)


def process_soundtrack_file(html_path: Path, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Process a single soundtrack HTML file and generate a TTL file.
    
    Args:
        html_path: Path to the HTML file
        output_dir: Optional output directory (defaults to same as HTML file)
    
    Returns:
        Path to the generated TTL file, or None if no soundtracks found
    """
    movie_id, entries = parse_soundtrack_html(html_path)
    
    if not entries:
        return None
    
    ttl_content = generate_ttl(movie_id, entries)
    
    if not ttl_content:
        return None
    
    # Determine output path
    if output_dir is None:
        output_dir = html_path.parent
    
    ttl_path = output_dir / f"{movie_id}_soundtrack.ttl"
    
    with open(ttl_path, 'w', encoding='utf-8') as f:
        f.write(ttl_content)
    
    return ttl_path


def main():
    """Main function to process all soundtrack HTML files."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Parse IMDb soundtrack HTML files and generate TTL files'
    )
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path('/home/ioannis/PycharmProjects/imdb4m/extractor/movies'),
        help='Base directory containing movie folders'
    )
    parser.add_argument(
        '--single-file',
        type=Path,
        help='Process a single HTML file instead of all files'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without writing files'
    )
    
    args = parser.parse_args()
    
    if args.single_file:
        # Process single file
        html_path = args.single_file
        if not html_path.exists():
            print(f"Error: File not found: {html_path}")
            return
        
        print(f"Processing: {html_path}")
        movie_id, entries = parse_soundtrack_html(html_path)
        print(f"  Found {len(entries)} soundtrack entries")
        
        if entries:
            ttl_content = generate_ttl(movie_id, entries)
            if args.dry_run:
                print("\n--- Generated TTL ---")
                print(ttl_content[:2000])
                if len(ttl_content) > 2000:
                    print(f"\n... ({len(ttl_content)} total characters)")
            else:
                ttl_path = process_soundtrack_file(html_path)
                print(f"  Generated: {ttl_path}")
        return
    
    # Process all files
    sound_files = list(args.input_dir.glob('**/movie_soundtrack/*_sound.html'))
    
    print(f"Found {len(sound_files)} soundtrack HTML files")
    print()
    
    processed = 0
    skipped = 0
    errors = 0
    
    for i, html_path in enumerate(sound_files):
        try:
            movie_id, entries = parse_soundtrack_html(html_path)
            
            if not entries:
                skipped += 1
                continue
            
            if args.dry_run:
                print(f"Would process: {html_path.name} ({len(entries)} tracks)")
                processed += 1
            else:
                ttl_path = process_soundtrack_file(html_path)
                if ttl_path:
                    processed += 1
                else:
                    skipped += 1
            
            # Progress update
            if (i + 1) % 50 == 0:
                print(f"Progress: {i + 1}/{len(sound_files)} files processed...")
                
        except Exception as e:
            print(f"Error processing {html_path}: {e}")
            errors += 1
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total files:      {len(sound_files)}")
    print(f"Processed:        {processed}")
    print(f"Skipped (empty):  {skipped}")
    print(f"Errors:           {errors}")


if __name__ == '__main__':
    main()

