#!/usr/bin/env python3
"""
Modality coverage statistics computed directly from the cleaned KG TTL.

Unlike `modality_count_movies.py` / `modality_count_actors.py`, which read the
raw per-entity TTL/JSON files in `data/movies/`, this script operates on
`data/kg/imdb_kg_cleaned.ttl` so that any media that was removed from the
released KG (because the underlying file could not be downloaded) is excluded.

For each seed movie / actor we count, in the cleaned graph:

* Text:   literal values of name, abstract, description, reviewBody, caption,
          keywords, genre, inLanguage, contentRating, alternateName,
          characterName, jobTitle, currency, unitCode -- on the entity itself,
          on attached blank nodes (reviews, performance roles, recordings, ...)
          and on directly linked media objects (images, videos, music
          recordings, music compositions).
* Images: the number of ImageObjects linked to the entity through schema:image,
          plus schema:thumbnail values.
* Videos: the number of VideoObjects linked through schema:trailer/schema:video,
          plus schema:trailer / schema:video values that point to URIs that are
          declared as VideoObject elsewhere in the graph.
* Audio:  the number of MusicRecording (or MusicComposition) blank nodes
          attached to a movie through schema:audio (only applies to movies).
"""

import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from tqdm import tqdm

from scripts.paths import DATA_DIR, KG_DIR, REPORTS_STATS

SCHEMA = Namespace("http://schema.org/")

TEXT_PREDICATES = {
    SCHEMA.name,
    SCHEMA.abstract,
    SCHEMA.description,
    SCHEMA.reviewBody,
    SCHEMA.caption,
    SCHEMA.keywords,
    SCHEMA.genre,
    SCHEMA.inLanguage,
    SCHEMA.contentRating,
    SCHEMA.alternateName,
    SCHEMA.characterName,
    SCHEMA.jobTitle,
    SCHEMA.currency,
    SCHEMA.unitCode,
}

IMAGE_PREDICATES = {SCHEMA.image, SCHEMA.thumbnail}
VIDEO_PREDICATES = {SCHEMA.trailer, SCHEMA.video}
AUDIO_PREDICATES = {SCHEMA.audio}


from scripts.paths import DATA_DIR, KG_DIR, REPORTS_STATS

TTL_PATH = KG_DIR / "imdb_kg_cleaned.ttl"
MOVIES_DIR = DATA_DIR / "movies"
ACTORS_DIR = MOVIES_DIR / "actors"


def discover_seed_ids() -> tuple[list[str], list[str]]:
    """Return (movie_ids, actor_ids) of the seed entities on disk."""
    movie_ids = sorted(
        d.name for d in MOVIES_DIR.iterdir()
        if d.is_dir() and d.name.startswith("tt") and d.name[2:].isdigit()
    )
    actor_ids = sorted(
        d.name for d in ACTORS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("nm") and d.name[2:].isdigit()
    )
    return movie_ids, actor_ids


def load_graph(ttl_path: Path) -> Graph:
    print(f"Loading {ttl_path} ({ttl_path.stat().st_size/1024/1024:.1f} MB)...")
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    print(f"  parsed {len(g):,} triples")
    return g


def build_indexes(g: Graph):
    """Build subject -> [(p,o)] and object -> [(s,p)] indexes plus type index."""
    spo: dict = defaultdict(list)
    ops: dict = defaultdict(list)
    types: dict = defaultdict(set)
    for s, p, o in tqdm(g, desc="Indexing", total=len(g)):
        spo[s].append((p, o))
        ops[o].append((s, p))
        if p == URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"):
            types[s].add(o)
    return spo, ops, types


EXPAND_TYPES = {
    SCHEMA.ImageObject,
    SCHEMA.VideoObject,
    SCHEMA.MusicRecording,
    SCHEMA.MusicComposition,
    SCHEMA.PerformanceRole,
    SCHEMA.Review,
    SCHEMA.AggregateRating,
    SCHEMA.Rating,
    SCHEMA.QuantitativeValue,
    SCHEMA.MonetaryAmount,
    SCHEMA.Place,
    SCHEMA.Award,
    SCHEMA.PropertyValue,
}


def count_modalities(
    entity_uris: list[URIRef],
    spo: dict,
    ops: dict,
    types: dict,
    *,
    include_audio: bool,
    include_inverse_actor: bool,
):
    """Count text/image/video/audio elements reachable from `entity_uris`.

    The closure follows blank nodes attached to the entity, as well as
    directly-linked ImageObject / VideoObject / MusicRecording /
    MusicComposition nodes (so their `caption`, `name`, ... literals count
    toward text). When `include_inverse_actor` is set, performance role nodes
    that point to the actor via `schema:actor` are also expanded so that
    `characterName` literals are credited to the actor.
    """
    text = 0
    images = 0
    videos = 0
    audio = 0

    visited: set = set()
    stack = list(entity_uris)
    visited.update(entity_uris)

    if include_inverse_actor:
        for entity in entity_uris:
            for s, p in ops.get(entity, ()):
                if p == SCHEMA.actor and SCHEMA.PerformanceRole in types.get(s, set()):
                    if s not in visited:
                        visited.add(s)
                        stack.append(s)
            for s, p in ops.get(entity, ()):
                if (
                    p == SCHEMA.mainEntity
                    and SCHEMA.ImageObject in types.get(s, set())
                ):
                    if s not in visited:
                        visited.add(s)
                        stack.append(s)

    while stack:
        node = stack.pop()
        for p, o in spo.get(node, ()):
            if p in TEXT_PREDICATES and isinstance(o, Literal):
                text += 1
            if p in IMAGE_PREDICATES:
                images += 1
            if p in VIDEO_PREDICATES:
                videos += 1
            if include_audio and p in AUDIO_PREDICATES:
                audio += 1
            if isinstance(o, BNode) and o not in visited:
                visited.add(o)
                stack.append(o)
                continue
            if isinstance(o, URIRef) and o not in visited:
                if types.get(o, set()) & EXPAND_TYPES:
                    visited.add(o)
                    stack.append(o)
    return text, images, videos, audio


def entity_uri_variants(prefix: str, ident: str) -> list[URIRef]:
    base = f"{prefix}{ident}"
    return [URIRef(base), URIRef(base + "/")]


def summarise(label: str, df: pd.DataFrame, *, with_audio: bool, n_seed: int):
    print(f"\n{'='*70}\n{label} (n={n_seed})\n{'='*70}")
    cov_text = (df["text"] > 0).mean() * 100
    cov_img = (df["images"] > 0).mean() * 100
    cov_vid = (df["videos"] > 0).mean() * 100
    avg_text = df["text"].mean()
    avg_img = df["images"].mean()
    avg_vid = df["videos"].mean()
    print(f"  Text   coverage {cov_text:6.2f}%  avg {avg_text:7.2f}")
    print(f"  Images coverage {cov_img:6.2f}%  avg {avg_img:7.2f}")
    print(f"  Videos coverage {cov_vid:6.2f}%  avg {avg_vid:7.2f}")
    if with_audio:
        cov_aud = (df["audio"] > 0).mean() * 100
        avg_aud = df["audio"].mean()
        print(f"  Audio  coverage {cov_aud:6.2f}%  avg {avg_aud:7.2f}")
        all_mask = (df[["text", "images", "videos", "audio"]] > 0).all(axis=1)
    else:
        all_mask = (df[["text", "images", "videos"]] > 0).all(axis=1)
    print(f"  All applicable modalities present: {all_mask.mean()*100:6.2f}%")


def main() -> int:
    movie_ids, actor_ids = discover_seed_ids()
    print(f"Seed: {len(movie_ids)} movies, {len(actor_ids)} actors")

    g = load_graph(TTL_PATH)
    spo, ops, types = build_indexes(g)

    movie_rows = []
    for mid in tqdm(movie_ids, desc="Movies"):
        uris = entity_uri_variants("https://www.imdb.com/title/", mid)
        t, i, v, a = count_modalities(
            uris, spo, ops, types,
            include_audio=True, include_inverse_actor=False,
        )
        movie_rows.append({"id": mid, "text": t, "images": i, "videos": v, "audio": a})

    actor_rows = []
    for aid in tqdm(actor_ids, desc="Actors"):
        uris = entity_uri_variants("https://www.imdb.com/name/", aid)
        t, i, v, _ = count_modalities(
            uris, spo, ops, types,
            include_audio=False, include_inverse_actor=True,
        )
        actor_rows.append({"id": aid, "text": t, "images": i, "videos": v, "audio": 0})

    movies_df = pd.DataFrame(movie_rows)
    actors_df = pd.DataFrame(actor_rows)

    summarise("MOVIES", movies_df, with_audio=True, n_seed=len(movie_ids))
    summarise("ACTORS", actors_df, with_audio=False, n_seed=len(actor_ids))

    out = REPORTS_STATS / "modality_counts_from_cleaned_kg.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        movies_df.to_excel(w, sheet_name="Movies", index=False)
        actors_df.to_excel(w, sheet_name="Actors", index=False)
    print(f"\nSaved per-entity counts to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
