"""
Parser for IMDb soundtrack metadata.
"""
from typing import List, Optional
import re
from pathlib import Path
from rdflib import Graph, Namespace, URIRef
from rdflib.term import Literal
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

	# ----------------------------------------------------------------------
	# TTL-based parsing using rdflib
	# ----------------------------------------------------------------------
	@staticmethod
	def parse_soundtrack_ttl(subset_root: str, imdb_id: str) -> List[SoundtrackMetadata]:
		"""
		Parse soundtrack metadata from Turtle files using rdflib.

		Reads movie title from `data/subset/<id>/movie_html/<id>.ttl` and
		soundtrack entries from `data/subset/<id>/movie_soundtrack/<id>_soundtrack.ttl`.

		Args:
			subset_root: Path to the `data/subset` directory
			imdb_id: IMDb title id (e.g., "tt0405159")

		Returns:
			List of SoundtrackMetadata
		"""
		base_path = Path(subset_root) / imdb_id
		movie_ttl = base_path / "movie_html" / f"{imdb_id}.ttl"
		soundtrack_ttl = base_path / "movie_soundtrack" / f"{imdb_id}_soundtrack.ttl"

		if not movie_ttl.exists():
			raise FileNotFoundError(f"Movie TTL not found: {movie_ttl}")
		if not soundtrack_ttl.exists():
			raise FileNotFoundError(f"Soundtrack TTL not found: {soundtrack_ttl}")

		schema = Namespace("http://schema.org/")

		# Parse graphs
		g_movie = Graph()
		g_movie.parse(movie_ttl.as_posix(), format="turtle")

		g_sound = Graph()
		g_sound.parse(soundtrack_ttl.as_posix(), format="turtle")

		# Movie title: try both URI variants (with and without trailing slash)
		movie_uri_no_slash = URIRef(f"https://www.imdb.com/title/{imdb_id}")
		movie_uri_slash = URIRef(f"https://www.imdb.com/title/{imdb_id}/")

		movie_title = SoundtrackParser._find_first_literal(
			g_movie, movie_uri_no_slash, schema.name
		) or SoundtrackParser._find_first_literal(
			g_movie, movie_uri_slash, schema.name
		)

		# Collect soundtracks via schema:audio
		soundtracks: List[SoundtrackMetadata] = []

		# Try both movie URIs when collecting audio nodes
		audio_nodes = set()
		for _, _, audio_node in g_sound.triples((movie_uri_slash, schema.audio, None)):
			audio_nodes.add(audio_node)
		for _, _, audio_node in g_sound.triples((movie_uri_no_slash, schema.audio, None)):
			audio_nodes.add(audio_node)

		for audio_node in audio_nodes:
			# audio_node is a blank node representing a schema:MusicRecording
			title_literal = SoundtrackParser._find_first_literal(g_sound, audio_node, schema.name)
			recording_of = SoundtrackParser._find_first_node(g_sound, audio_node, schema.recordingOf)

			composer_names: List[str] = []
			lyrics_names: List[str] = []

			if recording_of:
				# Prefer schema:composer; fall back to schema:author
				for _, _, comp_node in g_sound.triples((recording_of, schema.composer, None)):
					name = SoundtrackParser._resolve_person_name(g_sound, comp_node, schema)
					if name:
						composer_names.append(name)
				# Explicit lyricist if present
				for _, _, lyr_node in g_sound.triples((recording_of, schema.lyricist, None)):
					name = SoundtrackParser._resolve_person_name(g_sound, lyr_node, schema)
					if name:
						lyrics_names.append(name)
				for _, _, auth_node in g_sound.triples((recording_of, schema.author, None)):
					name = SoundtrackParser._resolve_person_name(g_sound, auth_node, schema)
					if name:
						# If composer already present, treat author as lyrics by
						if composer_names:
							lyrics_names.append(name)
						else:
							composer_names.append(name)

			# Performer/producer are not present in the provided TTL samples;
			# attempt to read if available.
			performer_names: List[str] = []
			for _, _, perf_node in g_sound.triples((audio_node, schema.byArtist, None)):
				name = SoundtrackParser._resolve_person_name(g_sound, perf_node, schema)
				if name:
					performer_names.append(name)

			producer_names: List[str] = []
			for _, _, prod_node in g_sound.triples((audio_node, schema.producer, None)):
				name = SoundtrackParser._resolve_person_name(g_sound, prod_node, schema)
				if name:
					producer_names.append(name)

			if title_literal:
				soundtracks.append(
					SoundtrackMetadata(
						title=str(title_literal),
						composer=", ".join(composer_names) if composer_names else None,
						lyrics_by=", ".join(lyrics_names) if lyrics_names else None,
						performer=", ".join(performer_names) if performer_names else None,
						producer=", ".join(producer_names) if producer_names else None,
						movie_title=str(movie_title) if isinstance(movie_title, Literal) else None,
						additional_info=None,
						is_traditional=False,
						is_uncredited=False,
					)
				)

		return soundtracks

	@staticmethod
	def _find_first_literal(g: Graph, subject: URIRef, predicate: URIRef) -> Optional[Literal]:
		for _, _, obj in g.triples((subject, predicate, None)):
			if isinstance(obj, Literal):
				return obj
		return None

	@staticmethod
	def _find_first_node(g: Graph, subject: URIRef, predicate: URIRef) -> Optional[URIRef]:
		for _, _, obj in g.triples((subject, predicate, None)):
			return obj
		return None

	@staticmethod
	def _resolve_person_name(g: Graph, node: URIRef, schema: Namespace) -> Optional[str]:
		"""Given a URIRef for a Person, return its schema:name if defined."""
		# If node is a URI, try to look up its name, else if it's a literal just return str
		if isinstance(node, URIRef):
			lit = SoundtrackParser._find_first_literal(g, node, schema.name)
			if lit:
				return str(lit)
			# If no name triple exists, fall back to the URI path tail
			return str(node).rstrip('/').split('/')[-1]
		elif isinstance(node, Literal):
			return str(node)
		return None
    
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
