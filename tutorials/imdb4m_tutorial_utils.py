"""Utilities shared by the IMDB4M tutorial notebooks.

The helpers in this module keep the notebooks short while applying the same
preprocessing used in the data release: media and text vectors are
L2-normalized, mean-pooled per movie when several rows belong to the same
title, and L2-normalized again. Knowledge-graph embeddings produced by
RotatE are already entity-level and only require the final L2 step.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef


SCHEMA = Namespace("http://schema.org/")
IMDB4M = Namespace("http://imdb4m.org/embedding/")

MEDIA_MODALITIES: Tuple[str, ...] = ("image", "video", "audio")
TEXT_MODALITY: str = "text"
KG_MODALITY: str = "kg"
MODALITIES: Tuple[str, ...] = MEDIA_MODALITIES + (TEXT_MODALITY, KG_MODALITY)

DEFAULT_FUSION_WEIGHTS: Dict[str, float] = {
    "image": 2.0,
    "video": 1.0,
    "audio": 1.0,
    "text": 1.5,
    "kg": 1.5,
}

KG_VARIANTS: Tuple[str, ...] = ("full", "genre", "rating", "decade", "language", "all_labels")
KG_VARIANT_LABEL: Dict[str, Optional[str]] = {
    "full": None,
    "genre": "genre",
    "rating": "rating",
    "decade": "decade",
    "language": "language",
    "all_labels": None,
}
KG_VARIANT_FILENAMES: Dict[str, str] = {
    "full": "kg_embeddings.parquet",
    "genre": "kg_heldout_genre_embeddings.parquet",
    "rating": "kg_heldout_rating_embeddings.parquet",
    "decade": "kg_heldout_decade_embeddings.parquet",
    "language": "kg_heldout_language_embeddings.parquet",
    "all_labels": "kg_heldout_all_labels_embeddings.parquet",
}


@dataclass(frozen=True)
class TutorialPaths:
    """Resolved paths used by both notebooks."""

    project_root: Path
    release_root: Path
    kg_path: Path
    embeddings_dir: Path
    embeddings_card: Path
    embedding_metadata: Path
    alignment_report: Path
    media_dir: Path
    qa_queries: Path


def project_root() -> Path:
    """Return the repository root when called from either repo or notebooks."""

    return Path(__file__).resolve().parents[1]


def resolve_paths(data_root: Optional[str | Path] = None) -> TutorialPaths:
    """Resolve the release bundle and source-checkout fallback paths.

    The release bundle is preferred; when individual artifacts (such as the
    text or RotatE embedding tables) are not yet packaged, the
    source-checkout ``embeddings_output`` directory is used as a fallback so
    the notebooks remain runnable end-to-end.
    """

    root = project_root()
    release_root = Path(data_root) if data_root else root / "release_output" / "imdb4m-release-v1"
    embeddings_dir = release_root / "embeddings"
    kg_path = release_root / "kg" / "imdb_kg_cleaned.pruned.ttl"

    if not kg_path.exists():
        kg_path = root / "data" / "kg" / "imdb_kg_cleaned.pruned.ttl"
    has_media = (embeddings_dir / "image_embeddings.parquet").exists()
    has_text = (embeddings_dir / "text_embeddings.parquet").exists()
    has_kg = (embeddings_dir / "kg_embeddings.parquet").exists()
    if not (has_media and has_text and has_kg):
        embeddings_dir = root / "embeddings_output"

    return TutorialPaths(
        project_root=root,
        release_root=release_root,
        kg_path=kg_path,
        embeddings_dir=embeddings_dir,
        embeddings_card=embeddings_dir / "embeddings_card.json",
        embedding_metadata=embeddings_dir / "embedding_metadata.ttl",
        alignment_report=release_root / "alignment_report.json",
        media_dir=root / "output",
        qa_queries=root / "QA" / "sparql_queries.txt",
    )


def load_json(path: Path) -> dict:
    """Load JSON when present, returning an empty dict for optional artifacts."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_kg(path: Path) -> Graph:
    """Load a Turtle KG with the prefixes used throughout IMDB4M."""

    graph = Graph()
    graph.bind("schema", SCHEMA)
    graph.bind("imdb4m", IMDB4M)
    graph.parse(str(path), format="turtle")
    return graph


_MOVIE_URI_RE = re.compile(r"^<(https?://www\.imdb\.com/title/(tt\d+)/?)>")
_GENRE_BLOCK_RE = re.compile(r"schema1?:genre\s+(.+?)(?=\s;|\s\.)", re.DOTALL)
_QUOTED_RE = re.compile(r'"([^"]+)"')
_DATE_RE = re.compile(r'schema1?:datePublished\s+"([^"]+)"')
_RATING_RE = re.compile(r'schema1?:contentRating\s+"([^"]+)"')
_LANG_BLOCK_RE = re.compile(r"schema1?:inLanguage\s+(.+?)(?=\s;|\s\.)", re.DOTALL)
_NAME_RE = re.compile(r'^    schema1?:name\s+"([^"]+)"', re.MULTILINE)
_DESC_RE = re.compile(r'^    schema1?:(?:abstract|description)\s+"([^"]+)"', re.MULTILINE)


def parse_movie_labels(kg_ttl: Path) -> Dict[str, Dict]:
    """Parse lightweight movie labels from the large Turtle file.

    This mirrors ``plots/embedding_projections.py`` but accepts both
    ``schema:`` and ``schema1:`` prefixes.
    """

    labels: Dict[str, Dict] = {}
    current_tt: Optional[str] = None
    current_block: List[str] = []

    def flush() -> None:
        if current_tt is None:
            return
        text = "".join(current_block)
        if "schema1:Movie" not in text and "schema:Movie" not in text:
            return
        record: Dict = {}
        if match := _NAME_RE.search(text):
            record["name"] = match.group(1)
        if match := _DESC_RE.search(text):
            record["description"] = match.group(1)
        if match := _GENRE_BLOCK_RE.search(text):
            genres = _QUOTED_RE.findall(match.group(1))
            if genres:
                record["genres"] = genres
        if match := _DATE_RE.search(text):
            year = match.group(1)[:4]
            if year.isdigit():
                record["year"] = int(year)
                record["decade"] = f"{(int(year) // 10) * 10}s"
        if match := _RATING_RE.search(text):
            record["contentRating"] = match.group(1)
        if match := _LANG_BLOCK_RE.search(text):
            languages = _QUOTED_RE.findall(match.group(1))
            if languages:
                record["languages"] = languages

        existing = labels.get(current_tt, {})
        existing.update(record)
        labels[current_tt] = existing

    with kg_ttl.open("r", encoding="utf-8") as f:
        for line in f:
            match = _MOVIE_URI_RE.match(line)
            if match:
                flush()
                current_tt = match.group(2)
                current_block = [line]
            else:
                current_block.append(line)
        flush()
    return labels


def imdb_movie_uri(movie_id: str) -> URIRef:
    """Return the canonical IMDb title URI used in the KG."""

    return URIRef(f"https://www.imdb.com/title/{movie_id}/")


def movie_display_name(movie_id: str, labels: Mapping[str, Mapping]) -> str:
    """Return a compact movie label for tables and plots."""

    record = labels.get(movie_id, {})
    name = record.get("name", movie_id)
    year = record.get("year")
    return f"{name} ({year})" if year else str(name)


def load_parquet_embeddings(path: Path) -> Tuple[pd.DataFrame, np.ndarray]:
    """Load one modality Parquet file and return metadata plus float32 matrix."""

    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["entity_id", "kg_uri", "source_url", "filename", "model_id", "embedding"])
    df = table.to_pandas()
    matrix = np.asarray(df["embedding"].to_list(), dtype=np.float32)
    return df.drop(columns=["embedding"]), matrix


def l2_normalize(matrix: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """L2-normalize rows of a matrix."""

    matrix = matrix.astype(np.float32, copy=False)
    denom = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(denom, eps)


def aggregate_per_entity(entity_ids: Sequence[str], matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """L2-normalize rows, mean-pool by entity id, and L2-normalize means."""

    matrix = l2_normalize(matrix)
    sums: Dict[str, np.ndarray] = {}
    counts: Dict[str, int] = defaultdict(int)
    for entity_id, vector in zip(entity_ids, matrix):
        if entity_id in sums:
            sums[entity_id] += vector
        else:
            sums[entity_id] = vector.copy()
        counts[entity_id] += 1

    ids = np.array(sorted(sums), dtype=object)
    pooled = np.vstack([sums[entity_id] / counts[entity_id] for entity_id in ids])
    return ids, l2_normalize(pooled)


def filter_movies(entity_ids: np.ndarray, matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Restrict aggregated embeddings to IMDb title IDs."""

    mask = np.array([str(entity_id).startswith("tt") for entity_id in entity_ids])
    return entity_ids[mask], matrix[mask]


def load_movie_embeddings(
    embeddings_dir: Path,
    modalities: Sequence[str] = MODALITIES,
    kg_variant: str = "full",
) -> Dict[str, Dict[str, np.ndarray]]:
    """Load and aggregate per-movie embeddings for the requested modalities.

    Image, video, audio, and text rows are pooled to the title level using
    the L2 -> mean -> L2 recipe applied at release time. The knowledge-graph
    modality is loaded from a single RotatE variant (default: ``full``);
    each movie has a single RotatE row, so no pooling is required.
    """

    result: Dict[str, Dict[str, np.ndarray]] = {}
    for modality in modalities:
        if modality == KG_MODALITY:
            filename = KG_VARIANT_FILENAMES.get(kg_variant)
            if filename is None:
                continue
            path = embeddings_dir / filename
        else:
            path = embeddings_dir / f"{modality}_embeddings.parquet"
        if not path.exists():
            continue
        df, matrix = load_parquet_embeddings(path)
        ids, pooled = aggregate_per_entity(df["entity_id"].to_numpy(), matrix)
        ids, pooled = filter_movies(ids, pooled)
        result[modality] = {
            "ids": ids,
            "X": pooled,
            "raw_df": df,
            "raw_X": matrix,
            "model_id": str(df["model_id"].iloc[0]) if len(df) else "",
            "kg_variant": kg_variant if modality == KG_MODALITY else None,
        }
    return result


def load_kg_variants(
    embeddings_dir: Path,
    variants: Sequence[str] = KG_VARIANTS,
) -> Dict[str, Dict[str, np.ndarray]]:
    """Load every available RotatE variant as title-level embedding tables.

    Returned dictionary keys are variant names (``full``, ``genre``,
    ``rating``, ``decade``, ``language``, ``all_labels``). Held-out variants
    are intended for label-clean classification of the corresponding label
    family; the ``full`` variant is intended for retrieval and visualization.
    """

    result: Dict[str, Dict[str, np.ndarray]] = {}
    for variant in variants:
        filename = KG_VARIANT_FILENAMES.get(variant)
        if filename is None:
            continue
        path = embeddings_dir / filename
        if not path.exists():
            continue
        df, matrix = load_parquet_embeddings(path)
        ids, pooled = aggregate_per_entity(df["entity_id"].to_numpy(), matrix)
        ids, pooled = filter_movies(ids, pooled)
        result[variant] = {
            "ids": ids,
            "X": pooled,
            "raw_df": df,
            "raw_X": matrix,
            "model_id": str(df["model_id"].iloc[0]) if len(df) else "",
        }
    return result


def common_movie_ids(embeddings: Mapping[str, Mapping[str, np.ndarray]]) -> np.ndarray:
    """Return sorted movie IDs present in all loaded modalities."""

    available = [set(data["ids"]) for data in embeddings.values() if len(data["ids"])]
    if not available:
        return np.array([], dtype=object)
    return np.array(sorted(set.intersection(*available)), dtype=object)


def restrict_to_ids(ids: np.ndarray, matrix: np.ndarray, wanted_ids: Sequence[str]) -> np.ndarray:
    """Return matrix rows in ``wanted_ids`` order."""

    position = {entity_id: idx for idx, entity_id in enumerate(ids)}
    return matrix[[position[entity_id] for entity_id in wanted_ids]]


def top_k_neighbors(query_id: str, ids: np.ndarray, matrix: np.ndarray, k: int = 10) -> List[Tuple[str, float]]:
    """Return nearest neighbors by cosine similarity, excluding the query."""

    matches = np.where(ids == query_id)[0]
    if not len(matches):
        raise ValueError(f"{query_id} is not present in this modality.")
    query_idx = int(matches[0])
    sims = matrix @ matrix[query_idx]
    order = np.argsort(-sims)
    neighbors: List[Tuple[str, float]] = []
    for idx in order:
        movie_id = str(ids[idx])
        if movie_id == query_id:
            continue
        neighbors.append((movie_id, float(sims[idx])))
        if len(neighbors) >= k:
            break
    return neighbors


def fused_neighbors(
    query_id: str,
    embeddings: Mapping[str, Mapping[str, np.ndarray]],
    weights: Mapping[str, float] = DEFAULT_FUSION_WEIGHTS,
    k: int = 10,
) -> List[Tuple[str, float]]:
    """Return late-fused neighbors using weighted cosine similarities."""

    ids = common_movie_ids(embeddings)
    if query_id not in set(ids):
        raise ValueError(f"{query_id} is not present in the all-modality intersection.")
    qidx = int(np.where(ids == query_id)[0][0])
    total_weight = 0.0
    scores = np.zeros(len(ids), dtype=np.float32)
    for modality, weight in weights.items():
        if modality not in embeddings or weight <= 0:
            continue
        X = restrict_to_ids(embeddings[modality]["ids"], embeddings[modality]["X"], ids)
        scores += float(weight) * (X @ X[qidx])
        total_weight += float(weight)
    if total_weight == 0:
        raise ValueError("At least one positive fusion weight is required.")
    scores /= total_weight
    order = np.argsort(-scores)
    neighbors: List[Tuple[str, float]] = []
    for idx in order:
        movie_id = str(ids[idx])
        if movie_id == query_id:
            continue
        neighbors.append((movie_id, float(scores[idx])))
        if len(neighbors) >= k:
            break
    return neighbors


def format_neighbors(
    neighbors: Sequence[Tuple[str, float]],
    labels: Mapping[str, Mapping],
) -> pd.DataFrame:
    """Turn retrieval results into a reviewer-friendly table."""

    rows = []
    for rank, (movie_id, score) in enumerate(neighbors, start=1):
        record = labels.get(movie_id, {})
        rows.append(
            {
                "rank": rank,
                "movie_id": movie_id,
                "title": record.get("name", movie_id),
                "year": record.get("year"),
                "genres": ", ".join(record.get("genres", [])),
                "rating": record.get("contentRating"),
                "score": round(float(score), 4),
                "imdb_url": f"https://www.imdb.com/title/{movie_id}/",
            }
        )
    return pd.DataFrame(rows)


def find_thumbnail(media_dir: Path, movie_id: str) -> Optional[Path]:
    """Return the first available local image for a movie."""

    image_dir = media_dir / movie_id / "images"
    if not image_dir.exists():
        return None
    for path in sorted(image_dir.iterdir()):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return path
    return None


def bounded_subgraph(
    graph: Graph,
    movie_id: str,
    predicates: Optional[Sequence[URIRef]] = None,
    hops: int = 1,
    max_edges: int = 250,
) -> Graph:
    """Extract a small outgoing/incoming RDF neighborhood around a movie."""

    seeds = [imdb_movie_uri(movie_id), URIRef(str(imdb_movie_uri(movie_id)).rstrip("/"))]
    predicate_filter = set(predicates or [])
    out = Graph()
    out.bind("schema", SCHEMA)
    queue: deque[Tuple[URIRef | BNode, int]] = deque((seed, 0) for seed in seeds)
    seen = set(seeds)

    while queue and len(out) < max_edges:
        node, depth = queue.popleft()
        if depth >= hops:
            continue
        triples = list(graph.triples((node, None, None))) + list(graph.triples((None, None, node)))
        for s, p, o in triples:
            if predicate_filter and p not in predicate_filter and p != RDF.type:
                continue
            out.add((s, p, o))
            for candidate in (s, o):
                if isinstance(candidate, (URIRef, BNode)) and candidate not in seen:
                    seen.add(candidate)
                    queue.append((candidate, depth + 1))
            if len(out) >= max_edges:
                break
    return out


def rdf_to_networkx(graph: Graph) -> nx.MultiDiGraph:
    """Convert an RDF graph to a labeled NetworkX graph."""

    nx_graph = nx.MultiDiGraph()
    for s, p, o in graph:
        s_id = short_term(s)
        o_id = short_term(o)
        nx_graph.add_node(s_id, rdf_type=type(s).__name__)
        nx_graph.add_node(o_id, rdf_type=type(o).__name__)
        nx_graph.add_edge(s_id, o_id, label=short_term(p))
    return nx_graph


def short_term(term) -> str:
    """Compact RDF terms for notebook tables and graph labels."""

    text = str(term)
    if isinstance(term, Literal):
        text = text[:60] + ("..." if len(text) > 60 else "")
    if text.startswith(str(SCHEMA)):
        return "schema:" + text.removeprefix(str(SCHEMA))
    if text.startswith(str(IMDB4M)):
        return "imdb4m:" + text.removeprefix(str(IMDB4M))
    if "imdb.com/title/" in text:
        match = re.search(r"(tt\d+)", text)
        return match.group(1) if match else text
    if "imdb.com/name/" in text:
        match = re.search(r"(nm\d+)", text)
        return match.group(1) if match else text
    return text


def structural_metrics(
    graph: Graph,
    include_clustering: bool = False,
    clustering_sample: int = 5000,
) -> Dict[str, object]:
    """Compute Table-4-style KG metrics from an RDF graph."""

    subjects = set(graph.subjects())
    objects = set(graph.objects())
    predicates = list(graph.predicates())
    all_nodes = subjects | objects
    predicate_counts = Counter(str(p) for p in predicates)
    type_counts = Counter(str(o) for o in graph.objects(None, RDF.type))

    directed = nx.DiGraph()
    entity_graph = nx.Graph()
    for s, p, o in graph:
        s_id, o_id = str(s), str(o)
        directed.add_edge(s_id, o_id)
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            entity_graph.add_edge(s_id, o_id)

    in_degrees = dict(directed.in_degree())
    out_degrees = dict(directed.out_degree())
    total_degrees = {node: in_degrees[node] + out_degrees[node] for node in directed.nodes}
    components = list(nx.connected_components(entity_graph)) if entity_graph.number_of_nodes() else []
    component_sizes = sorted((len(component) for component in components), reverse=True)

    if include_clustering and entity_graph.number_of_nodes() > 1:
        # Exact clustering on the full release graph can be expensive in a
        # notebook, so use a deterministic node sample by default.
        sample_nodes = sorted(entity_graph.nodes())[:clustering_sample]
        clustering = nx.average_clustering(entity_graph.subgraph(sample_nodes))
    else:
        clustering = None

    return {
        "triples": len(graph),
        "unique_subjects": len(subjects),
        "unique_objects": len(objects),
        "unique_predicates": len(set(predicates)),
        "unique_nodes": len(all_nodes),
        "uri_nodes": sum(isinstance(node, URIRef) for node in all_nodes),
        "blank_nodes": sum(isinstance(node, BNode) for node in all_nodes),
        "literal_nodes": sum(isinstance(node, Literal) for node in all_nodes),
        "directed_nodes": directed.number_of_nodes(),
        "directed_edges": directed.number_of_edges(),
        "avg_in_degree": _safe_mean(in_degrees.values()),
        "avg_out_degree": _safe_mean(out_degrees.values()),
        "max_in_degree": max(in_degrees.values(), default=0),
        "max_out_degree": max(out_degrees.values(), default=0),
        "source_nodes": sum(1 for node in directed.nodes if in_degrees[node] == 0 and out_degrees[node] > 0),
        "sink_nodes": sum(1 for node in directed.nodes if out_degrees[node] == 0 and in_degrees[node] > 0),
        "leaf_nodes": sum(1 for degree in total_degrees.values() if degree == 1),
        "entity_nodes": entity_graph.number_of_nodes(),
        "entity_edges": entity_graph.number_of_edges(),
        "connected_components": len(components),
        "largest_component": component_sizes[0] if component_sizes else 0,
        "density": nx.density(entity_graph) if entity_graph.number_of_nodes() > 1 else 0.0,
        "avg_clustering": clustering,
        "top_predicates": predicate_counts.most_common(20),
        "top_types": type_counts.most_common(20),
    }


def _safe_mean(values: Iterable[int | float]) -> float:
    values = list(values)
    return float(sum(values) / len(values)) if values else 0.0


def metrics_frame(metrics: Mapping[str, object]) -> pd.DataFrame:
    """Flatten scalar metrics to a two-column DataFrame."""

    return pd.DataFrame(
        [{"metric": key, "value": value} for key, value in metrics.items() if not isinstance(value, list)]
    )


def modality_coverage(
    graph: Graph,
    movie_ids: Sequence[str],
    audio_embedding_ids: Optional[Sequence[str]] = None,
    text_embedding_ids: Optional[Sequence[str]] = None,
    kg_embedding_ids: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Compute per-movie modality coverage from KG triples and embedding tables.

    Image, video, audio, and text counts are derived from the released
    knowledge graph. The optional ``*_embedding_ids`` arguments mark a movie
    as covered by the corresponding modality whenever a release embedding is
    available, even if the underlying KG asset is not separately enumerated.
    The KG modality is reported solely from RotatE coverage of the title.
    """

    audio_set = set(audio_embedding_ids) if audio_embedding_ids is not None else set()
    text_set = set(text_embedding_ids) if text_embedding_ids is not None else set()
    kg_set = set(kg_embedding_ids) if kg_embedding_ids is not None else set()
    rows = []
    for movie_id in movie_ids:
        uri_candidates = [imdb_movie_uri(movie_id), URIRef(str(imdb_movie_uri(movie_id)).rstrip("/"))]
        image_count = video_count = audio_count = review_count = text_count = 0
        for uri in uri_candidates:
            image_count += len(list(graph.objects(uri, SCHEMA.image)))
            video_count += len(list(graph.objects(uri, SCHEMA.trailer))) + len(list(graph.objects(uri, SCHEMA.video)))
            audio_count += len(list(graph.objects(uri, SCHEMA.audio)))
            review_count += len(list(graph.objects(uri, SCHEMA.review)))
            text_count += len(list(graph.objects(uri, SCHEMA.description))) + len(list(graph.objects(uri, SCHEMA.abstract)))
        if movie_id in audio_set:
            audio_count = max(audio_count, 1)
        text_total = text_count + review_count
        if movie_id in text_set:
            text_total = max(text_total, 1)
        rows.append(
            {
                "movie_id": movie_id,
                "text_count": text_total,
                "image_count": image_count,
                "video_count": video_count,
                "audio_count": audio_count,
                "has_text": text_total > 0,
                "has_image": image_count > 0,
                "has_video": video_count > 0,
                "has_audio": audio_count > 0,
                "has_kg": movie_id in kg_set,
            }
        )
    return pd.DataFrame(rows)


def summarize_coverage(coverage: pd.DataFrame) -> pd.DataFrame:
    """Summarize per-movie modality coverage across all five modalities."""

    if coverage.empty:
        return pd.DataFrame()
    rows = []
    for modality in ("text", "image", "video", "audio", "kg"):
        has_col = f"has_{modality}"
        count_col = f"{modality}_count"
        if has_col not in coverage.columns:
            continue
        if count_col in coverage.columns:
            total_elements = int(coverage[count_col].sum())
            avg_per_movie = round(float(coverage[count_col].mean()), 2)
        else:
            total_elements = ""
            avg_per_movie = ""
        rows.append(
            {
                "modality": modality,
                "movies_with_modality": int(coverage[has_col].sum()),
                "coverage_percent": round(100.0 * float(coverage[has_col].mean()), 2),
                "total_elements": total_elements,
                "avg_per_movie": avg_per_movie,
            }
        )
    has_columns = [col for col in ["has_text", "has_image", "has_video", "has_audio", "has_kg"] if col in coverage.columns]
    if has_columns:
        all_modalities = coverage[has_columns].all(axis=1)
        rows.append(
            {
                "modality": "all_modalities",
                "movies_with_modality": int(all_modalities.sum()),
                "coverage_percent": round(100.0 * float(all_modalities.mean()), 2),
                "total_elements": "",
                "avg_per_movie": "",
            }
        )
    return pd.DataFrame(rows)


def read_sparql_queries(path: Path) -> List[str]:
    """Read SPARQL queries separated by blank lines or comment headers."""

    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [block for block in blocks if "SELECT" in block.upper() or "ASK" in block.upper()]


def run_sparql_coverage(graph: Graph, queries: Sequence[str], limit: Optional[int] = None) -> pd.DataFrame:
    """Run SPARQL queries and report whether they produce non-empty results."""

    rows = []
    for idx, query in enumerate(queries[:limit], start=1):
        try:
            result = list(graph.query(query))
            rows.append({"query": idx, "success": True, "rows": len(result), "empty": len(result) == 0, "error": ""})
        except Exception as exc:  # pragma: no cover - notebook reporting path
            rows.append({"query": idx, "success": False, "rows": 0, "empty": True, "error": str(exc)})
    return pd.DataFrame(rows)


def label_arrays(movie_ids: Sequence[str], labels: Mapping[str, Mapping], label_name: str) -> Tuple[np.ndarray, np.ndarray]:
    """Return row mask and labels for embedding-quality metrics."""

    y = []
    keep = []
    for movie_id in movie_ids:
        record = labels.get(str(movie_id), {})
        value = None
        if label_name == "decade":
            value = record.get("decade")
        elif label_name == "rating":
            value = record.get("contentRating")
            if value not in {"G", "PG", "PG-13", "R"}:
                value = None
        elif label_name == "genre":
            genres = record.get("genres", [])
            value = genres[0] if genres else None
        elif label_name == "language":
            languages = record.get("languages", [])
            value = languages[0] if languages else None
        keep.append(value is not None)
        if value is not None:
            y.append(value)
    return np.array(keep), np.array(y)


def select_kg_variant_for_label(label_name: str) -> str:
    """Return the held-out RotatE variant intended for a label-clean metric."""

    direct = {"genre", "rating", "decade", "language"}
    if label_name in direct:
        return label_name
    return "all_labels"


def label_clean_metrics(
    movie_ids: Sequence[str],
    embeddings_per_modality: Mapping[str, Mapping[str, np.ndarray]],
    kg_variants: Mapping[str, Mapping[str, np.ndarray]],
    labels: Mapping[str, Mapping],
    label_names: Sequence[str] = ("decade", "rating", "genre", "language"),
    seed: int = 0,
) -> pd.DataFrame:
    """Compute embedding-quality metrics per modality and label.

    For media and text modalities the same embedding table is reused across
    all labels. For the KG modality the label-specific held-out variant is
    used instead of the ``full`` model so that no evaluation predicate is
    present in the training graph that produced the features.
    """

    movie_ids = np.asarray(list(movie_ids), dtype=object)
    rows: List[Dict[str, object]] = []
    for label_name in label_names:
        keep_mask, y = label_arrays(movie_ids, labels, label_name)
        if keep_mask.sum() < 5 or len(np.unique(y)) < 2:
            continue
        kept_ids = movie_ids[keep_mask]
        for modality, data in embeddings_per_modality.items():
            if modality == KG_MODALITY:
                variant = select_kg_variant_for_label(label_name)
                source = kg_variants.get(variant)
                if source is None:
                    continue
                ids_arr, X = source["ids"], source["X"]
                model_id = f"{source.get('model_id', '')} (variant={variant})"
            else:
                ids_arr, X = data["ids"], data["X"]
                model_id = data.get("model_id", "")
            id_to_idx = {movie_id: idx for idx, movie_id in enumerate(ids_arr)}
            mask = np.array([movie_id in id_to_idx for movie_id in kept_ids])
            if mask.sum() < 5:
                continue
            sub_ids = kept_ids[mask]
            sub_y = y[mask]
            sub_X = X[[id_to_idx[movie_id] for movie_id in sub_ids]]
            metric = compute_embedding_metrics(sub_X, sub_y, seed=seed)
            rows.append({"modality": modality, "label": label_name, "model_id": model_id, **metric})
    return pd.DataFrame(rows)


def compute_embedding_metrics(matrix: np.ndarray, labels: np.ndarray, seed: int = 0) -> Dict[str, float]:
    """Compute NCC accuracy, cosine silhouette, and K-Means ARI."""

    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    classes = np.unique(labels)
    if len(labels) < 3 or len(classes) < 2:
        return {"n": int(len(labels)), "n_classes": int(len(classes))}
    matrix = l2_normalize(matrix)
    sim = matrix @ matrix.T
    pred = []
    for i, label in enumerate(labels):
        best_label = None
        best_score = -math.inf
        for candidate in classes:
            mask = labels == candidate
            denom = int(mask.sum()) - int(candidate == label)
            if denom <= 0:
                continue
            score = float(sim[i, mask].sum() - (sim[i, i] if candidate == label else 0.0)) / denom
            if score > best_score:
                best_score = score
                best_label = candidate
        pred.append(best_label)
    kmeans = KMeans(n_clusters=len(classes), n_init=10, random_state=seed).fit(matrix)
    return {
        "n": int(len(labels)),
        "n_classes": int(len(classes)),
        "ncc_acc": float(np.mean(np.array(pred) == labels)),
        "ncc_baseline": float(1.0 / len(classes)),
        "silhouette_cosine": float(silhouette_score(matrix, labels, metric="cosine")),
        "ari_kmeans": float(adjusted_rand_score(labels, kmeans.labels_)),
    }
