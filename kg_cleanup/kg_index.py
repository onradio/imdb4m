"""Load the Turtle KG once and build the lookup tables we need.

Three indexes are produced:

* ``images``  — ``{image_uri: ImageRecord}`` keyed by ``<…/mediaviewer/rmNNN/>``.
  Also exposes a reverse map ``by_cdn_url: {cdn_url: image_uri}``.
* ``videos``  — ``{video_uri: VideoRecord}`` keyed by ``<…/video/viNNN>``.
  Also exposes ``by_video_id: {viNNN: video_uri}``.
* ``audio``   — ``{entity_uri: [AudioRecord]}`` where each ``AudioRecord``
  captures the blank-node ``schema:MusicRecording`` with its title, artists,
  and the full set of triples that belong to the blank-node subgraph (so we
  can later excise it cleanly).

The graph itself is kept in the returned :class:`KGIndex` so that
:mod:`apply` can run destructive operations on it.
"""

from __future__ import annotations

import logging
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF
from rdflib.term import BNode, Node

from .config import GRAPH_CACHE_PATH, KG_PATH, SCHEMA_NS

logger = logging.getLogger(__name__)

SCHEMA_IMAGE_OBJECT = URIRef(SCHEMA_NS + "ImageObject")
SCHEMA_VIDEO_OBJECT = URIRef(SCHEMA_NS + "VideoObject")
SCHEMA_MUSIC_RECORDING = URIRef(SCHEMA_NS + "MusicRecording")
SCHEMA_URL = URIRef(SCHEMA_NS + "url")
SCHEMA_EMBED_URL = URIRef(SCHEMA_NS + "embedUrl")
SCHEMA_NAME = URIRef(SCHEMA_NS + "name")
SCHEMA_BY_ARTIST = URIRef(SCHEMA_NS + "byArtist")
SCHEMA_AUDIO = URIRef(SCHEMA_NS + "audio")
SCHEMA_IMAGE = URIRef(SCHEMA_NS + "image")
SCHEMA_TRAILER = URIRef(SCHEMA_NS + "trailer")
SCHEMA_VIDEO = URIRef(SCHEMA_NS + "video")
SCHEMA_THUMBNAIL = URIRef(SCHEMA_NS + "thumbnail")
SCHEMA_THUMBNAIL_URL = URIRef(SCHEMA_NS + "thumbnailUrl")

VIDEO_BACKREF_PREDICATES = (SCHEMA_TRAILER, SCHEMA_VIDEO)
IMAGE_BACKREF_PREDICATES = (SCHEMA_IMAGE, SCHEMA_THUMBNAIL)

ENTITY_ID_RE = re.compile(r"/(tt\d+|nm\d+)(?:/|$)")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class ImageRecord:
    uri: URIRef
    entity_id: Optional[str]       # derived from the mediaviewer path
    cdn_url: Optional[str]         # value of schema:url
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class VideoRecord:
    uri: URIRef
    entity_id: Optional[str]       # best-effort back-reference via schema:trailer
    embed_url: Optional[str]
    name: Optional[str] = None
    video_id: Optional[str] = None


@dataclass
class AudioRecord:
    """A blank-node ``MusicRecording`` under some ``schema:audio`` property."""
    entity_uri: URIRef             # the Movie/Title that owns this recording
    entity_id: str
    bnode: BNode
    title: Optional[str]
    performers: List[URIRef] = field(default_factory=list)


@dataclass
class KGIndex:
    graph: Graph
    images: Dict[URIRef, ImageRecord] = field(default_factory=dict)
    videos: Dict[URIRef, VideoRecord] = field(default_factory=dict)
    audio: Dict[str, List[AudioRecord]] = field(default_factory=dict)   # key = entity_id

    # reverse maps
    image_by_cdn: Dict[str, URIRef] = field(default_factory=dict)
    image_by_stem: Dict[str, URIRef] = field(default_factory=dict)
    video_by_id: Dict[str, URIRef] = field(default_factory=dict)

    def describe(self) -> str:
        return (f"KGIndex(images={len(self.images)}, videos={len(self.videos)}, "
                f"audio_entities={len(self.audio)}, "
                f"audio_bnodes={sum(len(v) for v in self.audio.values())})")


# ---------------------------------------------------------------------------
# Graph loading (with a pickle cache because the TTL is 1.67 M lines)
# ---------------------------------------------------------------------------

def load_graph(kg_path: Path = KG_PATH,
               cache_path: Path = GRAPH_CACHE_PATH,
               use_cache: bool = True) -> Graph:
    """Parse the KG, or load a cached pickle if it's newer than the source."""
    if use_cache and cache_path.exists() and cache_path.stat().st_mtime >= kg_path.stat().st_mtime:
        logger.info("Loading graph from cache: %s", cache_path)
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    logger.info("Parsing %s (this may take a few minutes)…", kg_path)
    g = Graph()
    g.parse(str(kg_path), format="turtle")
    logger.info("Parsed %d triples", len(g))

    if use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Writing graph cache: %s", cache_path)
        with open(cache_path, "wb") as f:
            pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
    return g


# ---------------------------------------------------------------------------
# Indexers
# ---------------------------------------------------------------------------

def _entity_id_from_uri(uri: str) -> Optional[str]:
    """Extract the ``ttNNN`` / ``nmNNN`` slug from any IMDB URI."""
    m = ENTITY_ID_RE.search(str(uri))
    return m.group(1) if m else None


def _filename_stem_from_cdn_url(url: str) -> str:
    """Same rule as :func:`disk_scan.image_stem_from_url` — kept local to avoid a cycle."""
    from urllib.parse import unquote, urlparse
    from pathlib import Path as _P
    from .config import IMAGE_EXTS as _IE

    parsed = urlparse(url)
    filename = _P(unquote(parsed.path)).name
    filename = re.sub(r"[^\w\-_\.]", "_", filename)
    if not any(filename.lower().endswith(e) for e in _IE):
        filename += ".jpg"
    return _P(filename).stem


def _int(val: Optional[Node]) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _str(val: Optional[Node]) -> Optional[str]:
    return str(val) if val is not None else None


def index_images(g: Graph) -> Tuple[Dict[URIRef, ImageRecord], Dict[str, URIRef], Dict[str, URIRef]]:
    out: Dict[URIRef, ImageRecord] = {}
    by_cdn: Dict[str, URIRef] = {}
    by_stem: Dict[str, URIRef] = {}

    SCHEMA_WIDTH = URIRef(SCHEMA_NS + "width")
    SCHEMA_HEIGHT = URIRef(SCHEMA_NS + "height")

    for uri in g.subjects(RDF.type, SCHEMA_IMAGE_OBJECT):
        if not isinstance(uri, URIRef):
            continue
        cdn_url = g.value(uri, SCHEMA_URL)
        rec = ImageRecord(
            uri=uri,
            entity_id=_entity_id_from_uri(str(uri)),
            cdn_url=_str(cdn_url),
            width=_int(g.value(uri, SCHEMA_WIDTH)),
            height=_int(g.value(uri, SCHEMA_HEIGHT)),
        )
        out[uri] = rec
        if rec.cdn_url:
            by_cdn[rec.cdn_url] = uri
            by_stem[_filename_stem_from_cdn_url(rec.cdn_url)] = uri
    return out, by_cdn, by_stem


def index_videos(g: Graph) -> Tuple[Dict[URIRef, VideoRecord], Dict[str, URIRef]]:
    """Build the VideoObject index.

    Back-references live under both ``schema:trailer`` (movies→trailer) and
    ``schema:video`` (persons→clip).  We record the first entity that points
    at each VideoObject so the reconciler knows which ``output/<entity>/``
    folder to check.
    """
    out: Dict[URIRef, VideoRecord] = {}
    by_id: Dict[str, URIRef] = {}

    parent_rev: Dict[URIRef, URIRef] = {}
    for pred in VIDEO_BACKREF_PREDICATES:
        for ent, _, vid in g.triples((None, pred, None)):
            if isinstance(vid, URIRef) and isinstance(ent, URIRef):
                parent_rev.setdefault(vid, ent)

    for uri in g.subjects(RDF.type, SCHEMA_VIDEO_OBJECT):
        if not isinstance(uri, URIRef):
            continue
        embed = g.value(uri, SCHEMA_EMBED_URL)
        name = g.value(uri, SCHEMA_NAME)
        vid_id_match = re.search(r"(vi\d+)", str(uri))
        video_id = vid_id_match.group(1) if vid_id_match else None
        parent = parent_rev.get(uri)
        rec = VideoRecord(
            uri=uri,
            entity_id=_entity_id_from_uri(str(parent)) if parent else _entity_id_from_uri(str(uri)),
            embed_url=_str(embed),
            name=_str(name),
            video_id=video_id,
        )
        out[uri] = rec
        if video_id:
            by_id[video_id] = uri
    return out, by_id


def index_audio(g: Graph) -> Dict[str, List[AudioRecord]]:
    """Collect every blank-node ``MusicRecording`` reachable via ``schema:audio``.

    Only records whose parent is a Movie/Title URI (``ttXXX``) are kept —
    a Name/Person doesn't have audio soundtracks in IMDB's schema.
    """
    out: Dict[str, List[AudioRecord]] = {}
    for entity_uri, _, rec_node in g.triples((None, SCHEMA_AUDIO, None)):
        if not isinstance(entity_uri, URIRef) or not isinstance(rec_node, (BNode, URIRef)):
            continue
        eid = _entity_id_from_uri(str(entity_uri))
        if not eid or not eid.startswith("tt"):
            continue
        # verify it actually is typed as MusicRecording (defensive)
        if (rec_node, RDF.type, SCHEMA_MUSIC_RECORDING) not in g:
            continue
        title = _str(g.value(rec_node, SCHEMA_NAME))
        performers = [p for p in g.objects(rec_node, SCHEMA_BY_ARTIST)
                      if isinstance(p, URIRef)]
        out.setdefault(eid, []).append(AudioRecord(
            entity_uri=entity_uri,
            entity_id=eid,
            bnode=rec_node if isinstance(rec_node, BNode) else BNode(str(rec_node)),
            title=title,
            performers=performers,
        ))
    return out


def build_index(g: Graph) -> KGIndex:
    logger.info("Indexing ImageObjects…")
    images, by_cdn, by_stem = index_images(g)
    logger.info("  %d image nodes", len(images))

    logger.info("Indexing VideoObjects…")
    videos, by_id = index_videos(g)
    logger.info("  %d video nodes", len(videos))

    logger.info("Indexing audio MusicRecording blank nodes…")
    audio = index_audio(g)
    logger.info("  %d MusicRecording blank nodes across %d movies",
                sum(len(v) for v in audio.values()), len(audio))

    return KGIndex(
        graph=g,
        images=images,
        videos=videos,
        audio=audio,
        image_by_cdn=by_cdn,
        image_by_stem=by_stem,
        video_by_id=by_id,
    )


# ---------------------------------------------------------------------------
# Blank-node subgraph extraction (used later by apply.py)
# ---------------------------------------------------------------------------

def collect_bnode_subgraph(g: Graph, root: BNode,
                           seen: Optional[Set[BNode]] = None) -> Set[Tuple]:
    """Return every triple reachable from ``root`` via blank-node chains."""
    if seen is None:
        seen = set()
    if root in seen:
        return set()
    seen.add(root)
    triples: Set[Tuple] = set()
    for s, p, o in g.triples((root, None, None)):
        triples.add((s, p, o))
        if isinstance(o, BNode):
            triples |= collect_bnode_subgraph(g, o, seen)
    return triples
