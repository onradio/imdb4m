"""Extract text literals from the IMDB4M KG for text embedding.

Rows are shaped like media items so the existing Parquet/HDF5 writers can
store text embeddings without a separate schema.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef

logger = logging.getLogger(__name__)

SCHEMA = Namespace("http://schema.org/")
TITLE_URI_RE = re.compile(r"https?://www\.imdb\.com/title/(tt\d+)/?")

TEXT_PREDICATES: Dict[str, URIRef] = {
    "abstract": SCHEMA.abstract,
    "description": SCHEMA.description,
    "reviewBody": SCHEMA.reviewBody,
    "caption": SCHEMA.caption,
}


@dataclass(frozen=True)
class TextItem:
    """One KG text literal with movie linkage metadata."""

    entity_id: str
    kg_uri: str
    source_url: str
    modality: str
    filepath: str
    filename: str
    text: str
    predicate: str
    subject_uri: str


def text_id(item: TextItem) -> str:
    """Stable row id used by progress tracking."""

    return item.filepath


class KGTextScanner:
    """Parse KG text literals and resolve each row to an owning movie."""

    def __init__(
        self,
        kg_path: str | Path,
        predicates: Optional[Iterable[str]] = None,
    ) -> None:
        self.kg_path = Path(kg_path)
        self.predicates = list(predicates or TEXT_PREDICATES.keys())
        unknown = sorted(set(self.predicates) - set(TEXT_PREDICATES))
        if unknown:
            raise ValueError(f"Unknown text predicate(s): {', '.join(unknown)}")

    def scan(self) -> Iterator[TextItem]:
        logger.info("Parsing KG text literals from %s", self.kg_path)
        graph = Graph()
        graph.parse(str(self.kg_path), format="turtle")

        counters: Dict[str, int] = {name: 0 for name in self.predicates}
        skipped: Dict[str, int] = {name: 0 for name in self.predicates}

        for predicate_name in self.predicates:
            predicate = TEXT_PREDICATES[predicate_name]
            for subject, obj in graph.subject_objects(predicate):
                if not isinstance(obj, Literal):
                    skipped[predicate_name] += 1
                    continue
                text = str(obj).strip()
                if not text:
                    skipped[predicate_name] += 1
                    continue

                movie_uri = self._resolve_movie_uri(graph, subject, predicate_name)
                if movie_uri is None:
                    skipped[predicate_name] += 1
                    continue
                entity_id = self._movie_id(movie_uri)
                if entity_id is None:
                    skipped[predicate_name] += 1
                    continue

                idx = counters[predicate_name]
                counters[predicate_name] += 1
                digest = hashlib.sha1(
                    f"{subject.n3()}|{predicate_name}|{obj.n3()}".encode("utf-8")
                ).hexdigest()[:12]
                filename = f"{entity_id}__{predicate_name}__{idx:06d}__{digest}.txt"

                yield TextItem(
                    entity_id=entity_id,
                    kg_uri=str(movie_uri),
                    source_url="",
                    modality="text",
                    filepath=f"text://{filename}",
                    filename=filename,
                    text=text,
                    predicate=predicate_name,
                    subject_uri=str(subject),
                )

        logger.info("Text rows extracted: %s", counters)
        logger.info("Text rows skipped: %s", skipped)

    @staticmethod
    def _movie_id(uri: URIRef) -> Optional[str]:
        m = TITLE_URI_RE.search(str(uri))
        return m.group(1) if m else None

    def _resolve_movie_uri(
        self,
        graph: Graph,
        subject,
        predicate_name: str,
    ) -> Optional[URIRef]:
        if isinstance(subject, URIRef) and self._is_movie(graph, subject):
            return subject

        # Reviews are usually blank nodes linked from the movie by schema:review.
        if predicate_name == "reviewBody":
            for movie in graph.subjects(SCHEMA.review, subject):
                if isinstance(movie, URIRef) and self._is_movie(graph, movie):
                    return movie
            for movie in graph.objects(subject, SCHEMA.itemReviewed):
                if isinstance(movie, URIRef) and self._is_movie(graph, movie):
                    return movie

        # Captions sit on ImageObject nodes linked from movies by schema:image.
        if predicate_name == "caption":
            for movie in graph.subjects(SCHEMA.image, subject):
                if isinstance(movie, URIRef) and self._is_movie(graph, movie):
                    return movie

        # Descriptions can occur on movies, trailers, or structured values such
        # as budgets. Follow the common inbound movie edges.
        if predicate_name == "description":
            inbound_edges = (
                SCHEMA.trailer,
                SCHEMA.video,
                SCHEMA.productionBudget,
                SCHEMA.aggregateRating,
            )
            for edge in inbound_edges:
                for movie in graph.subjects(edge, subject):
                    if isinstance(movie, URIRef) and self._is_movie(graph, movie):
                        return movie

        return None

    @staticmethod
    def _is_movie(graph: Graph, node: URIRef) -> bool:
        return (node, RDF.type, SCHEMA.Movie) in graph


def scan_text_items(
    kg_path: str | Path,
    predicates: Optional[Iterable[str]] = None,
) -> List[TextItem]:
    """Convenience wrapper returning all text items as a list."""

    return list(KGTextScanner(kg_path, predicates=predicates).scan())
