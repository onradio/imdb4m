"""Execute the :class:`Manifest` against the KG.

High-level flow:

1. **Video rewrites & deletions** work at the *back-reference* granularity
   (``(entity, predicate, video_uri)``).  For each rewrite we ensure the
   target ``VideoObject`` exists (cloning the original's triples if needed
   because two entities might rewrite the *same* source URI to two
   different new URIs) and swap the back-reference.  After all per-entity
   decisions are applied, any source ``VideoObject`` that has lost every
   back-reference is removed outright.

2. **Image deletions** remove the ``ImageObject`` subject block *and*
   every triple that points at it (``schema:image``, ``schema:thumbnail``,
   …).  Images are never rewritten in this pipeline.

3. **Audio deletions** remove the parent ``schema:audio`` edge plus the
   full blank-node subgraph (``MusicRecording`` → ``recordingOf`` →
   ``MusicComposition`` …).

4. **Export** — every removed triple is written verbatim to the side
   graph (``data/kg/imdb_kg_failed_media.ttl``).  The main graph (minus
   those triples, plus the rewrites) is serialised to
   ``data/kg/imdb_kg_cleaned.pruned.ttl``.  The original TTL is never
   modified.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

from rdflib import Graph, Namespace, URIRef
from rdflib.term import BNode, Node

from .config import (
    PRUNED_KG_PATH,
    SCHEMA_NS,
    SIDE_GRAPH_PATH,
)
from .kg_index import (
    IMAGE_BACKREF_PREDICATES,
    KGIndex,
    SCHEMA_AUDIO,
    SCHEMA_EMBED_URL,
    SCHEMA_IMAGE,
    SCHEMA_THUMBNAIL,
    SCHEMA_TRAILER,
    SCHEMA_VIDEO,
    VIDEO_BACKREF_PREDICATES,
    collect_bnode_subgraph,
)
from .reconcile import Action, Decision, Manifest

logger = logging.getLogger(__name__)

Triple = Tuple[Node, Node, Node]


# ---------------------------------------------------------------------------
# Rewrite helper
# ---------------------------------------------------------------------------

def _uri_pair(uri_str: str) -> Tuple[URIRef, URIRef]:
    """Return (bare, trailing_slash) URIRef variants."""
    bare = URIRef(uri_str.rstrip("/"))
    slash = URIRef(uri_str.rstrip("/") + "/")
    return bare, slash


def _clone_video_node(g: Graph, old_uri_str: str, new_uri_str: str,
                      removed: Set[Triple]) -> None:
    """Ensure a VideoObject exists at ``new_uri_str`` by cloning ``old_uri_str``.

    We copy every ``(old, p, o)`` triple to ``(new, p, o)`` with the
    ``schema:embedUrl`` literal rewritten so it still points at the new
    video id.  If the new URI is already typed as a VideoObject we leave
    it alone.
    """
    from rdflib.namespace import RDF

    new_bare, new_slash = _uri_pair(new_uri_str)
    old_bare, old_slash = _uri_pair(old_uri_str)

    already_new = ((new_bare, RDF.type, URIRef(SCHEMA_NS + "VideoObject")) in g
                   or (new_slash, RDF.type, URIRef(SCHEMA_NS + "VideoObject")) in g)
    if already_new:
        return

    # Find the actual old subject in the graph (slash OR no slash — only one exists)
    old_subject = old_slash if (old_slash, None, None) in g else old_bare
    new_subject = new_slash if str(old_subject).endswith("/") else new_bare

    for _, p, o in g.triples((old_subject, None, None)):
        new_o = o
        if p == SCHEMA_EMBED_URL and isinstance(o, URIRef):
            new_o = URIRef(str(o).replace(str(old_subject).rstrip("/"),
                                          str(new_subject).rstrip("/")))
        g.add((new_subject, p, new_o))


def _apply_video_backref_changes(g: Graph, decisions: List[Decision],
                                 removed: Set[Triple]) -> Dict[str, int]:
    """Execute REWRITE + DELETE decisions for individual video back-references."""
    stats = {"rewritten": 0, "removed": 0, "cloned": 0, "node_deleted": 0}

    # First, clone whichever new VideoObjects don't exist yet
    seen_rewrites: Set[Tuple[str, str]] = set()
    for d in decisions:
        if d.media_type != "videos" or d.action is not Action.REWRITE:
            continue
        if not d.old_uri or not d.new_uri:
            continue
        key = (d.old_uri, d.new_uri)
        if key in seen_rewrites:
            continue
        seen_rewrites.add(key)
        before = len(g)
        _clone_video_node(g, d.old_uri, d.new_uri, removed)
        if len(g) > before:
            stats["cloned"] += 1

    # Then rewrite back-references per entity
    from .kg_index import _entity_id_from_uri
    for d in decisions:
        if d.media_type != "videos":
            continue
        if d.action is Action.KEEP:
            continue
        if not d.backref_predicate or not d.old_uri:
            continue
        pred = URIRef(d.backref_predicate)
        old_bare, old_slash = _uri_pair(d.old_uri)

        # The entity might point at either URI variant — check both.
        entity_uri = None
        chosen_old = None
        for variant in (old_slash, old_bare):
            for s, _, _ in g.triples((None, pred, variant)):
                if _entity_id_from_uri(str(s)) == d.entity_id:
                    entity_uri = s
                    chosen_old = variant
                    break
            if entity_uri is not None:
                break
        if entity_uri is None:
            logger.debug("Could not locate %s back-ref from %s to %s",
                         d.backref_predicate, d.entity_id, d.old_uri)
            continue

        t_old = (entity_uri, pred, chosen_old)
        g.remove(t_old)
        removed.add(t_old)

        if d.action is Action.REWRITE and d.new_uri:
            new_bare, new_slash = _uri_pair(d.new_uri)
            new_target = new_slash if str(chosen_old).endswith("/") else new_bare
            g.add((entity_uri, pred, new_target))
            stats["rewritten"] += 1
        else:
            stats["removed"] += 1

    # Finally, garbage-collect any source VideoObject that has lost all back-refs
    referenced_videos: Set[URIRef] = set()
    for pred in VIDEO_BACKREF_PREDICATES:
        for _, _, v in g.triples((None, pred, None)):
            if isinstance(v, URIRef):
                referenced_videos.add(v)
    for d in decisions:
        if d.media_type != "videos" or d.action is Action.KEEP:
            continue
        if not d.old_uri:
            continue
        old_bare, old_slash = _uri_pair(d.old_uri)
        for cand in (old_bare, old_slash):
            if cand in referenced_videos:
                continue
            subject_triples = list(g.triples((cand, None, None)))
            if subject_triples:
                for t in subject_triples:
                    g.remove(t)
                    removed.add(t)
                stats["node_deleted"] += 1

    return stats


# ---------------------------------------------------------------------------
# Deletion helper
# ---------------------------------------------------------------------------

@dataclass
class DeletionPlan:
    """Triples to be removed from the main graph (and copied to the side)."""
    triples: Set[Triple] = field(default_factory=set)

    def add(self, t: Triple) -> None:
        self.triples.add(t)


def _plan_audio_delete(g: Graph, entity_uri: URIRef, bnode: BNode,
                       plan: DeletionPlan) -> None:
    plan.add((entity_uri, SCHEMA_AUDIO, bnode))
    for t in collect_bnode_subgraph(g, bnode):
        plan.add(t)


def _build_audio_deletion_plan(g: Graph, kg: KGIndex,
                               decisions: List[Decision]) -> DeletionPlan:
    """Collect triples to remove for audio DELETE decisions."""
    plan = DeletionPlan()
    for d in decisions:
        if d.action is not Action.DELETE:
            continue
        if d.media_type == "audio" and d.audio_bnode:
            found = None
            for rec in kg.audio.get(d.entity_id, []):
                if str(rec.bnode) == d.audio_bnode:
                    found = rec
                    break
            if found is not None:
                _plan_audio_delete(g, found.entity_uri, found.bnode, plan)
            else:
                logger.warning("Audio BNode not found in index for %s/%s",
                               d.entity_id, d.audio_title)
    return plan


# ---------------------------------------------------------------------------
# Image back-reference deletions (mirror of _apply_video_backref_changes)
# ---------------------------------------------------------------------------

def _apply_image_backref_deletions(g: Graph, decisions: List[Decision],
                                   removed: Set[Triple]) -> Dict[str, int]:
    """Remove per-entity image back-references, then GC orphan ImageObjects.

    Image decisions are made per ``(entity, predicate, image_uri)`` triple
    because the same ``ImageObject`` may be referenced by several entities
    (movie + billed cast) and only some of those back-references may be
    stale.  A ``DELETE`` decision therefore removes *one* specific
    back-reference; once all decisions are applied, any ``ImageObject``
    that has lost every incoming edge is itself removed.
    """
    from .kg_index import _entity_id_from_uri

    stats = {"backref_removed": 0, "node_deleted": 0}
    touched: Set[URIRef] = set()

    for d in decisions:
        if d.media_type != "images" or d.action is not Action.DELETE:
            continue
        if not d.old_uri:
            continue
        img_uri = URIRef(d.old_uri)
        touched.add(img_uri)
        pred = URIRef(d.backref_predicate) if d.backref_predicate else SCHEMA_IMAGE

        for s, _, _ in list(g.triples((None, pred, img_uri))):
            if _entity_id_from_uri(str(s)) != d.entity_id:
                continue
            t = (s, pred, img_uri)
            g.remove(t)
            removed.add(t)
            stats["backref_removed"] += 1
            break

    # GC: any ImageObject with no remaining back-reference under any
    # image-style predicate is removed along with its full subject block.
    for img_uri in touched:
        has_ref = False
        for pred in IMAGE_BACKREF_PREDICATES:
            if next(g.triples((None, pred, img_uri)), None) is not None:
                has_ref = True
                break
        if has_ref:
            continue
        subject_triples = list(g.triples((img_uri, None, None)))
        if not subject_triples:
            continue
        for t in subject_triples:
            g.remove(t)
            removed.add(t)
        stats["node_deleted"] += 1

    return stats


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _make_side_graph(triples: Set[Triple]) -> Graph:
    side = Graph()
    side.bind("schema1", Namespace(SCHEMA_NS))
    side.bind("schema", Namespace(SCHEMA_NS))
    for t in triples:
        side.add(t)
    return side


def apply_manifest(kg: KGIndex, manifest: Manifest,
                   pruned_path: Path = PRUNED_KG_PATH,
                   side_path: Path = SIDE_GRAPH_PATH,
                   dry_run: bool = False) -> Dict[str, int]:
    """Apply every rewrite and deletion; serialise the two outputs."""
    g = kg.graph
    stats: Dict[str, int] = {"triples_before": len(g)}
    removed: Set[Triple] = set()

    # --- 1. Videos (per-backref rewrites + deletions + node GC).  Must run
    #        before any serialisation so cloned VideoObjects are in the graph.
    if not dry_run:
        vstats = _apply_video_backref_changes(g, manifest.decisions, removed)
        stats.update({"video_" + k: v for k, v in vstats.items()})
    else:
        n_rewrite = sum(1 for d in manifest.decisions
                        if d.media_type == "videos" and d.action is Action.REWRITE)
        n_delete = sum(1 for d in manifest.decisions
                       if d.media_type == "videos" and d.action is Action.DELETE)
        stats["video_rewritten"] = n_rewrite
        stats["video_removed"] = n_delete

    # --- 2. Images (per-backref deletions + node GC).
    if not dry_run:
        istats = _apply_image_backref_deletions(g, manifest.decisions, removed)
        stats.update({"image_" + k: v for k, v in istats.items()})
    else:
        n_idelete = sum(1 for d in manifest.decisions
                        if d.media_type == "images" and d.action is Action.DELETE)
        stats["image_backref_removed"] = n_idelete

    # --- 3. Audio deletion plan
    plan = _build_audio_deletion_plan(g, kg, manifest.decisions)
    stats["audio_triples_to_delete"] = len(plan.triples)

    if dry_run:
        stats["triples_to_delete_total"] = (
            len(plan.triples)
            + stats["video_removed"]
            + stats["image_backref_removed"]
        )
        logger.info(
            "Dry run: %d audio triples + %d image back-refs would be deleted; "
            "%d video back-refs would be removed, %d rewritten",
            len(plan.triples), stats["image_backref_removed"],
            stats["video_removed"], stats["video_rewritten"],
        )
        return stats

    # --- 4. Apply audio deletions
    for t in plan.triples:
        g.remove(t)
        removed.add(t)
    stats["triples_after"] = len(g)
    stats["triples_removed_total"] = len(removed)

    # --- 4. Serialise
    pruned_path.parent.mkdir(parents=True, exist_ok=True)
    side_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Serialising pruned KG → %s  (%d triples)", pruned_path, len(g))
    g.serialize(destination=str(pruned_path), format="turtle")

    side = _make_side_graph(removed)
    logger.info("Serialising side graph → %s  (%d triples)", side_path, len(side))
    side.serialize(destination=str(side_path), format="turtle")

    stats.update({
        "sidegraph_triples": len(side),
    })
    return stats
