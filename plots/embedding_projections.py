"""Produce multi-modal fusion projections, retrieval, and consistency
figures of IMDB4M media embeddings for the ESWC'26 paper appendix.

Outputs (in ``--out-dir``):

* ``fig_fusion_decade_umap.pdf`` / ``fig_fusion_decade_tsne.pdf``
    Panels: image / video / audio / KG / text average / fused, colored by release decade.
* ``fig_fusion_rating_umap.pdf`` / ``fig_fusion_rating_tsne.pdf``
    Same, colored by IMDb content rating (G / PG / PG-13 / R).
* ``fig_retrieval_grid.pdf``
    3 query movies (fixed seed) x modalities x top-5 nearest neighbors.
    Thumbnails are the first image in ``output/<tt>/images/``.
* ``fig_consistency_umap.pdf`` / ``fig_consistency_tsne.pdf``
    Individual poster embeddings of the top-5 movies by image count,
    showing intra-entity coherence (no KG labels needed).
* ``tab_fusion_metrics.tex``
    Modality/fusion rows x label columns (decade/rating/language).
    Each cell: NCC (nearest-centroid) top-1 acc / silhouette / ARI.
* ``metrics.json``, ``projections.npz``, ``retrieval_neighbors.json``
    Raw artifacts for reproducibility.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow.parquet as pq
from sklearn.cluster import KMeans, SpectralClustering
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import normalize

import umap  # umap-learn
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger("embproj")
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("fontTools").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

MODALITIES = ("image", "video", "audio", "kg", "text_avg")
MEDIA_MODALITIES = ("image", "video", "audio")
TEXT_PREDICATES = ("abstract", "description", "reviewBody", "caption")
TEXT_METRIC_KEYS = tuple(f"text_{p}" for p in TEXT_PREDICATES)
MODEL_LABEL = {
    "image": r"CLIP ViT-L/14",
    "video": r"X-CLIP base/32",
    "audio": r"CLAP",
    "kg": r"KG RotatE",
    "text_avg": r"Text avg (BGE)",
    "fused": r"Fused (late 2:1:1:1:1)",
}
RETRIEVAL_ROW_ORDER = ("image", "video", "audio", "kg", "text_avg", "fused")
PANEL_TITLE = {
    "image": "(a) Poster only",
    "video": "(b) Trailer only",
    "audio": "(c) Soundtrack only",
    "kg": "(d) Knowledge graph",
    "text_avg": "(e) Text average",
    "fused": "(f) Fused (image+video+audio+KG+text)",
}
FUSION_ORDER = ["image", "video", "audio", "kg", "text_avg", "fused"]

TOL_MUTED = [
    "#332288", "#88CCEE", "#44AA99", "#117733",
    "#999933", "#DDCC77", "#CC6677", "#AA4499", "#882255",
]
DECADE_COLORS = {
    "1980s": "#332288",
    "1990s": "#44AA99",
    "2000s": "#DDCC77",
    "2010s": "#CC6677",
    "2020s": "#AA4499",
}
RATING_ORDER = ["G", "PG", "PG-13", "R"]
RATING_COLORS = {
    "G":     "#44AA99",
    "PG":    "#DDCC77",
    "PG-13": "#CC6677",
    "R":     "#332288",
}

TARGET_GENRES = [
    "Drama", "Action", "Comedy", "Crime", "Thriller",
    "Sci-Fi", "Animation", "Horror", "Romance",
]


def save_fig(fig, out_pdf: Path) -> None:
    """Save both a PDF and a same-stem PNG (200 dpi) next to it."""
    out_pdf = Path(out_pdf)
    fig.savefig(out_pdf)
    png_path = out_pdf.with_suffix(".png")
    fig.savefig(png_path, dpi=200)
    log.info("Wrote %s (+ %s)", out_pdf.name, png_path.name)


def apply_paper_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Computer Modern Roman", "Times New Roman"],
            "mathtext.fontset": "cm",
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "text.usetex": False,
        }
    )


# ---------------------------------------------------------------------------
# KG parsing
# ---------------------------------------------------------------------------

_MOVIE_URI_RE = re.compile(r"^<(https?://www\.imdb\.com/title/(tt\d+)/?)>")
_GENRE_BLOCK_RE = re.compile(r"schema1:genre\s+(.+?)(?=\s;|\s\.)", re.DOTALL)
_QUOTED_RE = re.compile(r'"([^"]+)"')
_DATE_RE = re.compile(r'schema1:datePublished\s+"([^"]+)"')
_RATING_RE = re.compile(r'schema1:contentRating\s+"([^"]+)"')
_LANG_BLOCK_RE = re.compile(r"schema1:inLanguage\s+(.+?)(?=\s;|\s\.)", re.DOTALL)
_NAME_RE = re.compile(r'^    schema1:name\s+"([^"]+)"', re.MULTILINE)


def parse_movie_labels(kg_ttl: Path) -> Dict[str, Dict]:
    """Return ``tt_id -> {name, genres, year, decade, contentRating,
    languages}``.  Entries for the same tt id are merged so the "rich"
    record (no trailing slash) wins over the "stub" record (trailing slash).
    """
    log.info("Parsing KG at %s", kg_ttl)
    labels: Dict[str, Dict] = {}

    with open(kg_ttl, "r", encoding="utf-8") as f:
        current_tt: Optional[str] = None
        current_block: List[str] = []

        def flush():
            if current_tt is None:
                return
            txt = "".join(current_block)
            if "a schema1:Movie" not in txt:
                return
            rec: Dict = {}
            mn = _NAME_RE.search(txt)
            if mn:
                rec["name"] = mn.group(1)
            mg = _GENRE_BLOCK_RE.search(txt)
            if mg:
                genres = _QUOTED_RE.findall(mg.group(1))
                if genres:
                    rec["genres"] = genres
            md = _DATE_RE.search(txt)
            if md:
                year = md.group(1)[:4]
                if year.isdigit():
                    rec["year"] = int(year)
                    rec["decade"] = f"{(int(year)//10)*10}s"
            mr = _RATING_RE.search(txt)
            if mr:
                rec["contentRating"] = mr.group(1)
            ml = _LANG_BLOCK_RE.search(txt)
            if ml:
                langs = _QUOTED_RE.findall(ml.group(1))
                if langs:
                    rec["languages"] = langs
            existing = labels.get(current_tt, {})
            existing.update(rec)
            labels[current_tt] = existing

        for line in f:
            m = _MOVIE_URI_RE.match(line)
            if m:
                flush()
                current_tt = m.group(2)
                current_block = [line]
            else:
                current_block.append(line)
        flush()

    n_year = sum(1 for v in labels.values() if "year" in v)
    n_rating = sum(1 for v in labels.values() if "contentRating" in v)
    n_lang = sum(1 for v in labels.values() if "languages" in v)
    log.info(
        "Parsed %d movie records (year=%d rating=%d lang=%d)",
        len(labels), n_year, n_rating, n_lang,
    )
    return labels


# ---------------------------------------------------------------------------
# Embedding loading + aggregation
# ---------------------------------------------------------------------------

def load_parquet_embeddings(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(entity_ids, filenames, X)`` for all rows in a modality parquet."""
    log.info("Loading %s", path)
    tbl = pq.read_table(path, columns=["entity_id", "filename", "embedding"])
    entity_ids = np.asarray(tbl.column("entity_id").to_pylist(), dtype=object)
    filenames = np.asarray(tbl.column("filename").to_pylist(), dtype=object)
    X = np.asarray(tbl.column("embedding").to_pylist(), dtype=np.float32)
    log.info("  %d rows, dim=%d", X.shape[0], X.shape[1])
    return entity_ids, filenames, X


def aggregate_per_entity(
    entity_ids: np.ndarray, X: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """L2-norm rows -> mean per entity -> L2-norm the means."""
    X = normalize(X.astype(np.float32), norm="l2")
    bucket_sum: Dict[str, np.ndarray] = {}
    bucket_n: Dict[str, int] = defaultdict(int)
    for eid, v in zip(entity_ids, X):
        if eid in bucket_sum:
            bucket_sum[eid] += v
        else:
            bucket_sum[eid] = v.copy()
        bucket_n[eid] += 1
    ids = np.array(sorted(bucket_sum.keys()))
    X_mean = np.vstack([bucket_sum[i] / bucket_n[i] for i in ids])
    X_mean = normalize(X_mean, norm="l2")
    return ids, X_mean


def filter_movies(ids: np.ndarray, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mask = np.array([i.startswith("tt") for i in ids])
    return ids[mask], X[mask]


def text_predicate_from_filename(filename: str) -> Optional[str]:
    """Extract predicate tag from ``tt...__predicate__...txt`` filenames."""

    parts = str(filename).split("__")
    if len(parts) < 3:
        return None
    pred = parts[1]
    return pred if pred in TEXT_PREDICATES else None


def aggregate_text_by_predicate(
    entity_ids: np.ndarray,
    filenames: np.ndarray,
    X: np.ndarray,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Return one movie vector per predicate using L2 -> mean -> L2."""

    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for predicate in TEXT_PREDICATES:
        mask = np.array([text_predicate_from_filename(fn) == predicate for fn in filenames])
        if not mask.any():
            continue
        ids_pred, X_pred = aggregate_per_entity(entity_ids[mask], X[mask])
        out[f"text_{predicate}"] = filter_movies(ids_pred, X_pred)
    return out


def build_text_average(
    predicate_vectors: Dict[str, Tuple[np.ndarray, np.ndarray]]
) -> Tuple[np.ndarray, np.ndarray]:
    """Balanced movie-level average over available text predicate vectors."""

    sums: Dict[str, np.ndarray] = {}
    counts: Dict[str, int] = defaultdict(int)
    for _, (ids, X) in predicate_vectors.items():
        X = normalize(X.astype(np.float32), norm="l2")
        for eid, vec in zip(ids, X):
            if eid in sums:
                sums[eid] += vec
            else:
                sums[eid] = vec.copy()
            counts[eid] += 1
    ids = np.array(sorted(sums.keys()))
    if len(ids) == 0:
        return ids, np.empty((0, 0), dtype=np.float32)
    X_avg = np.vstack([sums[eid] / counts[eid] for eid in ids])
    X_avg = normalize(X_avg, norm="l2").astype(np.float32)
    return ids, X_avg


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def pca_l2(X: np.ndarray, pca_dim: int, seed: int = 0) -> np.ndarray:
    dim = min(pca_dim, X.shape[0] - 1, X.shape[1])
    Z = PCA(n_components=dim, random_state=seed).fit_transform(X)
    return normalize(Z, norm="l2").astype(np.float32)


def concatenate_fusion(
    restricted_mats: Dict[str, np.ndarray],
    pca_dim: int = 128,
    seed: int = 0,
    modalities: Sequence[str] = MODALITIES,
) -> np.ndarray:
    projected = [pca_l2(restricted_mats[m], pca_dim=pca_dim, seed=seed) for m in modalities]
    return normalize(np.hstack(projected), norm="l2").astype(np.float32)


def restrict_to_ids(ids: np.ndarray, X: np.ndarray, target_ids: Sequence[str]) -> np.ndarray:
    pos = {i: k for k, i in enumerate(ids)}
    rows = [pos[i] for i in target_ids]
    return X[rows]


def build_fusion(
    modalities: Dict[str, Tuple[np.ndarray, np.ndarray]],
    pca_dim: int = 128,
    seed: int = 0,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Intersect entity ids across modalities, project each modality to ``pca_dim``,
    L2-norm, and concatenate.

    Returns ``(fusion_ids, per_modality_restricted)`` where
    ``per_modality_restricted[m]`` is the restricted-to-intersection matrix for
    single-modality panels (same row order as ``fusion_ids``), plus an extra
    ``"fused"`` key with the concatenated modality matrix.
    """
    if not modalities:
        raise ValueError("At least one modality is required for fusion")

    common_sets = [set(ids) for ids, _ in modalities.values()]
    common = sorted(set.intersection(*common_sets))
    counts = " ".join(f"{m}={len(ids)}" for m, (ids, _) in modalities.items())
    log.info("Fusion intersection: %s -> common=%d", counts, len(common))

    restricted = {
        m: restrict_to_ids(ids, X, common)
        for m, (ids, X) in modalities.items()
    }
    restricted["fused"] = concatenate_fusion(restricted, pca_dim=pca_dim, seed=seed, modalities=tuple(modalities))
    return np.array(common), restricted


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------

def project_pca_umap(X: np.ndarray, seed: int = 0) -> np.ndarray:
    n = X.shape[0]
    pca_dim = min(50, n - 1, X.shape[1])
    X_pca = PCA(n_components=pca_dim, random_state=seed).fit_transform(X)
    reducer = umap.UMAP(
        n_components=2,
        metric="cosine",
        n_neighbors=min(15, n - 1),
        min_dist=0.1,
        random_state=seed,
    )
    return reducer.fit_transform(X_pca)


def project_pca_tsne(X: np.ndarray, seed: int = 0) -> np.ndarray:
    n = X.shape[0]
    pca_dim = min(50, n - 1, X.shape[1])
    X_pca = PCA(n_components=pca_dim, random_state=seed).fit_transform(X)
    perplexity = max(5.0, min(30.0, n / 5.0))
    tsne = TSNE(
        n_components=2,
        metric="cosine",
        perplexity=perplexity,
        learning_rate="auto",
        init="pca",
        random_state=seed,
    )
    return tsne.fit_transform(X_pca)


# ---------------------------------------------------------------------------
# Label builders (restricted to a given set of tt ids)
# ---------------------------------------------------------------------------

def decade_labels(
    tt_ids: Sequence[str], movie_labels: Dict[str, Dict]
) -> Tuple[np.ndarray, np.ndarray]:
    """Keep only ids that have a known decade; return (mask, y)."""
    y = []
    keep = []
    for tt in tt_ids:
        rec = movie_labels.get(tt, {})
        if "decade" in rec:
            y.append(rec["decade"])
            keep.append(True)
        else:
            keep.append(False)
    return np.array(keep), np.array(y)


def rating_labels(
    tt_ids: Sequence[str], movie_labels: Dict[str, Dict],
    allowed: Sequence[str] = ("G", "PG", "PG-13", "R"),
) -> Tuple[np.ndarray, np.ndarray]:
    y = []
    keep = []
    allowed_set = set(allowed)
    for tt in tt_ids:
        rec = movie_labels.get(tt, {})
        r = rec.get("contentRating")
        if r in allowed_set:
            y.append(r)
            keep.append(True)
        else:
            keep.append(False)
    return np.array(keep), np.array(y)


def genre_labels(
    tt_ids: Sequence[str], movie_labels: Dict[str, Dict],
    target_genres: Sequence[str] = TARGET_GENRES,
) -> Tuple[np.ndarray, np.ndarray]:
    """Assign each movie its rarest target genre (within this subset)."""
    freq = {g: 0 for g in target_genres}
    for tt in tt_ids:
        for g in movie_labels.get(tt, {}).get("genres", []):
            if g in freq:
                freq[g] += 1
    y: List[str] = []
    keep: List[bool] = []
    for tt in tt_ids:
        genres = movie_labels.get(tt, {}).get("genres", [])
        candidates = [(freq[g], g) for g in genres if g in freq and freq[g] > 0]
        if not candidates:
            keep.append(False)
            continue
        candidates.sort()
        keep.append(True)
        y.append(candidates[0][1])
    return np.array(keep), np.array(y)


def language_labels(
    tt_ids: Sequence[str], movie_labels: Dict[str, Dict], top_k: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    # primary language = first in list
    first_lang = []
    for tt in tt_ids:
        rec = movie_labels.get(tt, {})
        langs = rec.get("languages", [])
        first_lang.append(langs[0] if langs else None)
    # pick top-k, rest -> "Other"
    from collections import Counter
    cnt = Counter(l for l in first_lang if l is not None)
    top = [l for l, _ in cnt.most_common(top_k)]
    y = []
    keep = []
    for l in first_lang:
        if l is None:
            keep.append(False)
            continue
        keep.append(True)
        y.append(l if l in top else "Other")
    return np.array(keep), np.array(y)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def ncc_sim_loo_accuracy(S: np.ndarray, y: np.ndarray) -> float:
    """Leave-one-out kernel Nearest Centroid Classifier accuracy.

    For each query ``i`` and each class ``c``, the score is the *mean*
    precomputed similarity between ``i`` and every other member of ``c``
    (i.e. self is excluded). The query is assigned to the class with the
    highest mean similarity. This is the kernelized / cosine equivalent of
    ``sklearn.neighbors.NearestCentroid`` and works identically for raw
    features (via ``S = X @ X.T`` on L2-normed rows) and for late-fusion
    similarity matrices.
    """
    n = len(y)
    if n <= 2 or len(np.unique(y)) < 2:
        return float("nan")
    y = np.asarray(y)
    classes = np.unique(y)
    # class_masks[c] is a boolean vector over rows
    class_masks = {c: (y == c) for c in classes}
    class_counts = {c: int(m.sum()) for c, m in class_masks.items()}
    correct = 0
    for i in range(n):
        yi = y[i]
        best_c, best_score = None, -np.inf
        for c in classes:
            m = class_masks[c]
            denom = class_counts[c] - (1 if c == yi else 0)
            if denom <= 0:
                continue
            total = float(S[i, m].sum())
            if c == yi:
                total -= float(S[i, i])  # exclude self
            score = total / denom
            if score > best_score:
                best_score = score
                best_c = c
        if best_c == yi:
            correct += 1
    return correct / n


def compute_metrics(X: np.ndarray, y: np.ndarray, seed: int = 0) -> Dict:
    n_classes = len(np.unique(y))
    if len(y) < 3 or n_classes < 2:
        return {"n": int(len(y)), "n_classes": int(n_classes)}
    S = (X @ X.T).astype(np.float32)
    acc = ncc_sim_loo_accuracy(S, y)
    sil = float(silhouette_score(X, y, metric="cosine"))
    km = KMeans(n_clusters=n_classes, n_init=10, random_state=seed).fit(X)
    ari = float(adjusted_rand_score(y, km.labels_))
    return {
        "n": int(len(y)),
        "n_classes": int(n_classes),
        "ncc_acc": acc,
        "ncc_baseline": 1.0 / n_classes,
        "silhouette_cosine": sil,
        "ari_kmeans": ari,
    }


def compute_late_fusion_metrics(
    Xs: Sequence[np.ndarray], y: np.ndarray, seed: int = 0,
    weights: Optional[Sequence[float]] = None,
) -> Dict:
    """Late-fusion metrics: weighted mean cosine similarity across modalities.

    ``Xs`` is the list of modality matrices, each with rows already L2-normed
    and in the same entity order. We form ``S = sum_m w_m (X_m X_m^T) / sum(w)``
    and use ``D = 1 - S`` for silhouette, ``S`` for SpectralClustering ARI,
    and the mean-similarity kernel NCC for classification accuracy.
    """
    n_classes = len(np.unique(y))
    if len(y) < 3 or n_classes < 2:
        return {"n": int(len(y)), "n_classes": int(n_classes)}
    if weights is None:
        weights = [1.0] * len(Xs)
    w = np.asarray(weights, dtype=np.float32)
    w = w / float(w.sum())
    S = np.zeros((len(y), len(y)), dtype=np.float32)
    for wi, X in zip(w, Xs):
        S += wi * (X @ X.T).astype(np.float32)
    np.fill_diagonal(S, 1.0)
    D = np.clip(1.0 - S, 0.0, 2.0)
    np.fill_diagonal(D, 0.0)

    acc = ncc_sim_loo_accuracy(S, y)
    sil = float(silhouette_score(D, y, metric="precomputed"))

    A = np.clip(S, 0.0, 1.0)
    try:
        sc = SpectralClustering(
            n_clusters=n_classes, affinity="precomputed",
            random_state=seed, assign_labels="kmeans",
        )
        labels_pred = sc.fit_predict(A)
        ari = float(adjusted_rand_score(y, labels_pred))
    except Exception as e:
        log.warning("SpectralClustering failed for late fusion: %s", e)
        ari = float("nan")

    return {
        "n": int(len(y)),
        "n_classes": int(n_classes),
        "ncc_acc": acc,
        "ncc_baseline": 1.0 / n_classes,
        "silhouette_cosine": sil,
        "ari_kmeans": ari,
    }


def _simplex_weight_grid(n_modalities: int, step: float = 0.25) -> np.ndarray:
    """Enumerate non-negative, sum-to-one weights on a coarse simplex grid."""

    units = int(round(1.0 / step))
    weights: List[List[float]] = []

    def rec(prefix: List[int], remaining: int, slots: int) -> None:
        if slots == 1:
            weights.append(prefix + [remaining])
            return
        for value in range(remaining + 1):
            rec(prefix + [value], remaining - value, slots - 1)

    rec([], units, n_modalities)
    return np.asarray(weights, dtype=np.float32) / float(units)


def _weighted_similarity(sim_mats: Sequence[np.ndarray], weights: Sequence[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float32)
    w = w / float(w.sum())
    S = np.zeros_like(sim_mats[0], dtype=np.float32)
    for wi, S_m in zip(w, sim_mats):
        S += wi * S_m.astype(np.float32)
    np.fill_diagonal(S, 1.0)
    return S


def _ncc_train_test_accuracy(S: np.ndarray, y: np.ndarray, train_idx: np.ndarray, test_idx: np.ndarray) -> float:
    """Kernel NCC: class centroids are training members only, scored on test rows."""

    y = np.asarray(y)
    classes = np.unique(y[train_idx])
    if len(test_idx) == 0 or len(classes) < 2:
        return float("nan")
    correct = 0
    scored = 0
    for i in test_idx:
        best_c, best_score = None, -np.inf
        for c in classes:
            members = train_idx[y[train_idx] == c]
            if len(members) == 0:
                continue
            score = float(S[i, members].mean())
            if score > best_score:
                best_c = c
                best_score = score
        if best_c is None:
            continue
        correct += int(best_c == y[i])
        scored += 1
    return correct / scored if scored else float("nan")


def _safe_stratified_folds(y: np.ndarray, requested: int) -> int:
    _, counts = np.unique(y, return_counts=True)
    if len(counts) < 2:
        return 0
    return int(max(0, min(requested, counts.min())))


def tune_weights_cv_ncc(
    sim_mats_train: Sequence[np.ndarray],
    y_train: np.ndarray,
    weight_grid: np.ndarray,
    seed: int,
    inner_folds: int = 3,
) -> np.ndarray:
    """Select simplex weights by inner-CV NCC on the training fold."""

    n_splits = _safe_stratified_folds(y_train, inner_folds)
    if n_splits < 2:
        return np.ones(len(sim_mats_train), dtype=np.float32) / len(sim_mats_train)

    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    best_score = -np.inf
    best_weight = weight_grid[0]
    for weights in weight_grid:
        scores = []
        S = _weighted_similarity(sim_mats_train, weights)
        for inner_train, inner_val in splitter.split(np.zeros(len(y_train)), y_train):
            acc = _ncc_train_test_accuracy(S, y_train, inner_train, inner_val)
            if np.isfinite(acc):
                scores.append(acc)
        score = float(np.mean(scores)) if scores else -np.inf
        if score > best_score:
            best_score = score
            best_weight = weights
    return np.asarray(best_weight, dtype=np.float32)


def compute_supervised_late_fusion_cv_metrics(
    Xs: Sequence[np.ndarray],
    y: np.ndarray,
    modality_names: Sequence[str],
    seed: int = 0,
    outer_folds: int = 5,
    inner_folds: int = 3,
    weight_step: float = 0.25,
) -> Dict:
    """Nested-CV supervised late fusion with non-negative simplex weights.

    The outer folds estimate performance.  The inner folds choose the weights
    using only the outer training fold, which keeps the reported NCC defensible
    as a supervised downstream fusion score rather than an in-sample optimum.
    """

    y = np.asarray(y)
    n_classes = len(np.unique(y))
    if len(y) < 3 or n_classes < 2:
        return {"n": int(len(y)), "n_classes": int(n_classes)}
    n_splits = _safe_stratified_folds(y, outer_folds)
    if n_splits < 2:
        return {"n": int(len(y)), "n_classes": int(n_classes)}

    sim_mats = [(normalize(X.astype(np.float32), norm="l2") @ normalize(X.astype(np.float32), norm="l2").T).astype(np.float32) for X in Xs]
    weight_grid = _simplex_weight_grid(len(sim_mats), step=weight_step)
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)

    fold_acc: List[float] = []
    fold_weights: List[np.ndarray] = []
    for fold_no, (train_idx, test_idx) in enumerate(splitter.split(np.zeros(len(y)), y)):
        train_sims = [S[np.ix_(train_idx, train_idx)] for S in sim_mats]
        weights = tune_weights_cv_ncc(
            train_sims,
            y[train_idx],
            weight_grid=weight_grid,
            seed=seed + fold_no,
            inner_folds=inner_folds,
        )
        S_full = _weighted_similarity(sim_mats, weights)
        acc = _ncc_train_test_accuracy(S_full, y, train_idx, test_idx)
        if np.isfinite(acc):
            fold_acc.append(acc)
            fold_weights.append(weights)

    if not fold_acc:
        return {"n": int(len(y)), "n_classes": int(n_classes)}
    weights_mean = np.vstack(fold_weights).mean(axis=0)
    weights_std = np.vstack(fold_weights).std(axis=0)
    return {
        "n": int(len(y)),
        "n_classes": int(n_classes),
        "ncc_acc": float(np.mean(fold_acc)),
        "ncc_acc_std": float(np.std(fold_acc)),
        "ncc_baseline": 1.0 / n_classes,
        "outer_folds": int(n_splits),
        "inner_folds": int(inner_folds),
        "weight_step": float(weight_step),
        "modalities": list(modality_names),
        "weights_mean": {m: float(w) for m, w in zip(modality_names, weights_mean)},
        "weights_std": {m: float(w) for m, w in zip(modality_names, weights_std)},
        "fold_ncc_acc": [float(v) for v in fold_acc],
    }


# ---------------------------------------------------------------------------
# Plotting: four-panel fusion figure
# ---------------------------------------------------------------------------

def _categorical_palette(labels: Sequence[str], ordered: Optional[List[str]] = None) -> Dict[str, str]:
    if ordered is None:
        ordered = sorted(set(labels))
    return {l: TOL_MUTED[i % len(TOL_MUTED)] for i, l in enumerate(ordered)}


def _ordinal_palette(ordered: List[str]) -> Dict[str, str]:
    return {v: RATING_COLORS[v] for v in ordered}


def plot_fusion_grid(
    panels: Dict[str, Dict],          # modality -> {coords, labels}
    out_pdf: Path,
    method_name: str,
    palette: Dict,
    label_order: List[str],
    ordinal: bool = False,
) -> None:
    """One-row grid: native modalities plus fused."""
    apply_paper_style()
    n_panels = len(FUSION_ORDER)
    fig, axes = plt.subplots(1, n_panels, figsize=(3.5 * n_panels, 3.8))
    axes = np.atleast_1d(axes)

    for ax, modality in zip(axes, FUSION_ORDER):
        if modality not in panels:
            ax.set_visible(False)
            continue
        coords = panels[modality]["coords"]
        y = panels[modality]["labels"]
        n = len(y)

        counts = {l: int(np.sum(y == l)) for l in label_order}
        draw_order = sorted(label_order, key=lambda l: -counts[l])
        for lab in draw_order:
            mask = y == lab
            if not mask.any():
                continue
            is_bg = lab == draw_order[0] and counts[lab] > 2 * (counts[draw_order[1]] if len(draw_order) > 1 else 1)
            ax.scatter(
                coords[mask, 0], coords[mask, 1],
                s=10 if is_bg else 16,
                alpha=0.35 if is_bg else 0.90,
                c=[palette[lab]], edgecolors="none",
                zorder=1 if is_bg else 2,
            )
        title = PANEL_TITLE.get(modality, modality)
        subtitle = MODEL_LABEL.get(modality, "") if modality != "fused" else "CLIP + X-CLIP + CLAP + RotatE + BGE"
        ax.set_title(f"{title}\n{subtitle}  (N={n})", fontsize=9)
        ax.set_xlabel(f"{method_name}-1")
        ax.set_ylabel(f"{method_name}-2")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_linewidth(0.5)

    handles = [
        Line2D([0], [0], marker="o", linestyle="", markersize=6,
               color=palette[l], label=l)
        for l in label_order
    ]
    fig.legend(
        handles=handles, loc="lower center",
        ncol=min(len(handles), 9), frameon=False,
        bbox_to_anchor=(0.5, -0.01),
        handletextpad=0.4, columnspacing=1.0,
    )
    fig.subplots_adjust(wspace=0.12, bottom=0.22, top=0.86)

    save_fig(fig, out_pdf)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Retrieval figure
# ---------------------------------------------------------------------------

def find_thumbnail(media_dir: Path, tt_id: str) -> Optional[Path]:
    """Return the first .jpg in output/<tt>/images/ (or None)."""
    d = media_dir / tt_id / "images"
    if not d.is_dir():
        return None
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            return p
    return None


def top_k_neighbors(
    query_vec: np.ndarray, ids: np.ndarray, X: np.ndarray, k: int,
    exclude_id: str,
) -> List[Tuple[str, float]]:
    sims = X @ query_vec
    order = np.argsort(-sims)
    out = []
    for idx in order:
        if ids[idx] == exclude_id:
            continue
        out.append((str(ids[idx]), float(sims[idx])))
        if len(out) >= k:
            break
    return out


def _load_thumbnail(path: Optional[Path], size: int = 150) -> Optional[np.ndarray]:
    if path is None or not path.exists():
        return None
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((size, size * 3), Image.LANCZOS)
        return np.asarray(im)
    except Exception as e:
        log.warning("Failed to load %s: %s", path, e)
        return None


def plot_retrieval_grid(
    queries: List[str],
    neighbors: Dict[str, Dict[str, List[Tuple[str, float]]]],
    movie_labels: Dict[str, Dict],
    media_dir: Path,
    out_pdf: Path,
    top_k: int = 5,
    row_order: Sequence[str] = RETRIEVAL_ROW_ORDER,
) -> None:
    """Rows = (query x retrieval-type); cols = [query, nb1..nbK]."""
    apply_paper_style()
    n_per_query = len(row_order)
    n_rows = len(queries) * n_per_query
    n_cols = top_k + 1
    fig = plt.figure(figsize=(n_cols * 1.4 + 1.0, n_rows * 1.4 + 0.4))
    gs = GridSpec(
        n_rows, n_cols, figure=fig,
        wspace=0.08, hspace=0.55,
        left=0.14, right=0.99, top=0.96, bottom=0.02,
    )

    for qi, qtt in enumerate(queries):
        q_name = movie_labels.get(qtt, {}).get("name", qtt)
        q_thumb = _load_thumbnail(find_thumbnail(media_dir, qtt))
        for mi, modality in enumerate(row_order):
            row = qi * n_per_query + mi
            # Column 0: query
            ax = fig.add_subplot(gs[row, 0])
            if q_thumb is not None:
                ax.imshow(q_thumb)
            ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values():
                s.set_linewidth(1.2); s.set_edgecolor("#333333")
            ax.set_ylabel(
                f"{MODEL_LABEL[modality]}",
                fontsize=7, rotation=0, ha="right", va="center", labelpad=8,
            )
            if mi == 0:
                title = q_name if len(q_name) < 30 else q_name[:28] + "..."
                ax.set_title(f"Query: {title}", fontsize=8, loc="left")

            # Neighbor columns
            nbs = neighbors[qtt][modality]
            for k, (nb_tt, sim) in enumerate(nbs[:top_k]):
                axk = fig.add_subplot(gs[row, k + 1])
                thumb = _load_thumbnail(find_thumbnail(media_dir, nb_tt))
                if thumb is not None:
                    axk.imshow(thumb)
                axk.set_xticks([]); axk.set_yticks([])
                for s in axk.spines.values():
                    s.set_linewidth(0.4); s.set_edgecolor("#888888")
                name = movie_labels.get(nb_tt, {}).get("name", nb_tt)
                short = name if len(name) < 22 else name[:20] + "..."
                axk.set_title(f"{short}\ncos={sim:.2f}", fontsize=6.5)

    save_fig(fig, out_pdf)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Intra-movie consistency figure
# ---------------------------------------------------------------------------

def plot_consistency(
    entity_ids_raw: np.ndarray, X_raw: np.ndarray,
    top_n_movies: int,
    movie_labels: Dict[str, Dict],
    out_pdf_umap: Path, out_pdf_tsne: Path,
    seed: int = 0,
) -> None:
    # count per movie
    from collections import Counter
    counts = Counter(entity_ids_raw.tolist())
    movie_ids_with_counts = [
        (tt, c) for tt, c in counts.items()
        if tt.startswith("tt") and c >= 5
    ]
    movie_ids_with_counts.sort(key=lambda x: -x[1])
    picked = [tt for tt, _ in movie_ids_with_counts[:top_n_movies]]
    log.info("Consistency figure: %d movies (%s)",
             len(picked), ", ".join(f"{t}({c})" for t, c in movie_ids_with_counts[:top_n_movies]))

    mask = np.array([i in set(picked) for i in entity_ids_raw])
    ids_sub = entity_ids_raw[mask]
    X_sub = normalize(X_raw[mask], norm="l2")
    log.info("  N points: %d", len(ids_sub))

    for method, projector, out_path in (
        ("UMAP", project_pca_umap, out_pdf_umap),
        ("t-SNE", project_pca_tsne, out_pdf_tsne),
    ):
        coords = projector(X_sub, seed=seed)
        apply_paper_style()
        fig, ax = plt.subplots(figsize=(6.5, 5.2))
        palette = _categorical_palette(picked, ordered=picked)
        for tt in picked:
            mk = ids_sub == tt
            name = movie_labels.get(tt, {}).get("name", tt)
            n = int(mk.sum())
            ax.scatter(
                coords[mk, 0], coords[mk, 1],
                s=18, alpha=0.8, c=[palette[tt]], edgecolors="none",
                label=f"{name} (N={n})",
            )
        ax.set_xlabel(f"{method}-1"); ax.set_ylabel(f"{method}-2")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.5)
        ax.set_title(
            f"Individual poster embeddings -- {method}\n"
            "Each point is one image; same-movie points share a color.",
            fontsize=9,
        )
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                  fontsize=8, frameon=False, borderpad=0.3, handletextpad=0.4)
        fig.tight_layout()
        save_fig(fig, out_path)
        plt.close(fig)


# ---------------------------------------------------------------------------
# LaTeX table: modality x label cross product
# ---------------------------------------------------------------------------

TABLE_ROW_ORDER = [
    "image", "video", "audio", "kg",
    "text_abstract", "text_description", "text_reviewBody", "text_caption", "text_avg",
    "fused", "fused_late", "fused_late_wp", "fused_late_cv",
]
TABLE_DISPLAY_NAME = {
    "image": r"Poster (CLIP)",
    "video": r"Trailer (X-CLIP)",
    "audio": r"Soundtrack (CLAP)",
    "kg": r"KG (RotatE, held-out labels)",
    "text_abstract": r"Text -- abstract (BGE)",
    "text_description": r"Text -- description (BGE)",
    "text_reviewBody": r"Text -- review body (BGE)",
    "text_caption": r"Text -- caption (BGE)",
    "text_avg": r"Text -- balanced avg. (BGE)",
    "fused": r"Fused -- concat. (early, +KG+text)",
    "fused_late": r"Fused -- mean sim.\ (late, 1:1:1:1:1)",
    "fused_late_wp": r"\textbf{Fused -- late, poster-weighted (2:1:1:1:1)}",
    "fused_late_cv": r"\textbf{Fused -- supervised CV late}",
}


def write_fusion_metrics_table(
    metrics: Dict[str, Dict[str, Dict]],
    out_tex: Path,
    labels: Sequence[str] = ("decade", "rating", "genre", "language"),
) -> None:
    label_header = {
        "decade": "Decade",
        "rating": "Rating",
        "genre": "Genre",
        "language": "Language",
    }

    cols_spec = "l" + "c" * (len(labels) * 4)
    head_top = (
        " & " +
        " & ".join(
            "\\multicolumn{4}{c}{%s}" % label_header[l] for l in labels
        ) + " \\\\"
    )
    head_mid = " & " + " & ".join(
        "$N$ & NCC acc & silh. & ARI" for _ in labels
    ) + " \\\\"

    baseline_row_cells = []
    for l in labels:
        m = None
        for mod in TABLE_ROW_ORDER:
            m = metrics.get(mod, {}).get(l)
            if m and "ncc_baseline" in m:
                break
        if m and "ncc_baseline" in m:
            baseline_row_cells.append(
                "-- & %.1f\\%% & -- & 0.000" % (100 * m["ncc_baseline"])
            )
        else:
            baseline_row_cells.append("-- & -- & -- & --")
    baseline_row = "Random baseline & " + " & ".join(baseline_row_cells) + " \\\\"

    rows = []
    for mod in TABLE_ROW_ORDER:
        row = [TABLE_DISPLAY_NAME[mod]]
        for l in labels:
            m = metrics.get(mod, {}).get(l, {})
            if "ncc_acc" in m:
                ncc = f"{100*m['ncc_acc']:.1f}\\%"
                if "ncc_acc_std" in m:
                    ncc = f"{100*m['ncc_acc']:.1f}\\% $\\pm$ {100*m['ncc_acc_std']:.1f}"
                row.append(f"{m['n']}")
                row.append(ncc)
                row.append(f"{m['silhouette_cosine']:+.3f}" if "silhouette_cosine" in m else "--")
                row.append(f"{m['ari_kmeans']:.3f}" if "ari_kmeans" in m else "--")
            else:
                row.append("--"); row.append("--"); row.append("--"); row.append("--")
        rows.append(" & ".join(row) + " \\\\")

    n_early = TABLE_ROW_ORDER.index("fused") + 1  # native/text rows + early-concat fusion
    tex = (
        "% Auto-generated by plots/embedding_projections.py\n"
        "\\begin{tabular}{" + cols_spec + "}\n"
        "\\toprule\n"
        + head_top + "\n"
        + head_mid + "\n"
        "\\midrule\n"
        + "\n".join(rows[:n_early]) + "\n"
        "\\midrule\n"
        + "\n".join(rows[n_early:]) + "\n"
        "\\midrule\n"
        + baseline_row + "\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
    )
    out_tex.write_text(tex, encoding="utf-8")
    log.info("Wrote %s", out_tex)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed-dir", default="embeddings_output")
    ap.add_argument("--kg", default="data/kg/imdb_kg_cleaned.pruned.ttl")
    ap.add_argument("--kg-embeddings", default=None,
                    help="Full RotatE KG embeddings parquet; defaults to <embed-dir>/kg_embeddings.parquet.")
    ap.add_argument("--kg-embedding-for-genre", default=None,
                    help="Held-out-genre RotatE parquet for clean genre metrics.")
    ap.add_argument("--kg-embedding-for-rating", default=None,
                    help="Held-out-rating RotatE parquet for clean rating metrics.")
    ap.add_argument("--kg-embedding-for-decade", default=None,
                    help="Held-out-date RotatE parquet for clean decade metrics.")
    ap.add_argument("--kg-embedding-for-language", default=None,
                    help="Held-out-language RotatE parquet for clean language metrics.")
    ap.add_argument("--media-dir", default="output")
    ap.add_argument("--out-dir", default="plots/out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pca-dim", type=int, default=256)
    ap.add_argument("--consistency-top-n", type=int, default=5)
    ap.add_argument("--retrieval-n-queries", type=int, default=3)
    args = ap.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    embed_dir = Path(args.embed_dir); media_dir = Path(args.media_dir)

    random.seed(args.seed); np.random.seed(args.seed)

    # --- 1. Labels from KG -------------------------------------------------
    movie_labels = parse_movie_labels(Path(args.kg))

    # --- 2. Load + aggregate each modality --------------------------------
    raw: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    agg: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    kg_full_path = Path(args.kg_embeddings) if args.kg_embeddings else embed_dir / "kg_embeddings.parquet"
    modality_paths = {
        **{m: embed_dir / f"{m}_embeddings.parquet" for m in MEDIA_MODALITIES},
        "kg": kg_full_path,
    }
    for modality in (*MEDIA_MODALITIES, "kg"):
        pqp = modality_paths[modality]
        ids_raw, fnames, X_raw = load_parquet_embeddings(pqp)
        raw[modality] = (ids_raw, fnames, X_raw)
        ids_agg, X_agg = aggregate_per_entity(ids_raw, X_raw)
        ids_agg, X_agg = filter_movies(ids_agg, X_agg)  # tt only
        agg[modality] = (ids_agg, X_agg)
        log.info("  %s aggregated: %d movies", modality, len(ids_agg))

    text_path = embed_dir / "text_embeddings.parquet"
    ids_text_raw, fnames_text, X_text_raw = load_parquet_embeddings(text_path)
    raw["text"] = (ids_text_raw, fnames_text, X_text_raw)
    text_predicate_agg = aggregate_text_by_predicate(ids_text_raw, fnames_text, X_text_raw)
    for key, (ids_pred, X_pred) in text_predicate_agg.items():
        log.info("  %s aggregated: %d movies", key, len(ids_pred))
    agg["text_avg"] = build_text_average(text_predicate_agg)
    log.info("  text_avg aggregated: %d movies", len(agg["text_avg"][0]))

    # --- 3. Fusion subset --------------------------------------------------
    fusion_ids, fused_mats = build_fusion({m: agg[m] for m in MODALITIES}, pca_dim=args.pca_dim, seed=args.seed)

    # Label-classification metrics involving KG use label-specific held-out
    # RotatE models.  Visual projections, retrieval, and qualitative fusion use
    # the full KG model loaded above.
    heldout_defaults = {
        "genre": embed_dir / "kg_heldout_genre_embeddings.parquet",
        "rating": embed_dir / "kg_heldout_rating_embeddings.parquet",
        "decade": embed_dir / "kg_heldout_decade_embeddings.parquet",
        "language": embed_dir / "kg_heldout_language_embeddings.parquet",
    }
    heldout_overrides = {
        "genre": args.kg_embedding_for_genre,
        "rating": args.kg_embedding_for_rating,
        "decade": args.kg_embedding_for_decade,
        "language": args.kg_embedding_for_language,
    }
    kg_metric_mats: Dict[str, np.ndarray] = {}
    for lname, default_path in heldout_defaults.items():
        path = Path(heldout_overrides[lname]) if heldout_overrides[lname] else default_path
        ids_raw, _, X_raw = load_parquet_embeddings(path)
        ids_agg, X_agg = aggregate_per_entity(ids_raw, X_raw)
        ids_agg, X_agg = filter_movies(ids_agg, X_agg)
        kg_metric_mats[lname] = restrict_to_ids(ids_agg, X_agg, fusion_ids)

    supervised_id_sets = [set(fusion_ids)]
    supervised_id_sets.extend(set(ids) for ids, _ in text_predicate_agg.values())
    supervised_ids = np.array(sorted(set.intersection(*supervised_id_sets)))
    log.info(
        "Supervised late-fusion common pool: fusion=%d all-text-predicates=%d",
        len(fusion_ids),
        len(supervised_ids),
    )

    # --- 4. Build label subsets, project, plot ----------------------------
    #   (a) decade  (categorical)
    #   (b) rating  (ordinal)

    projections = {"umap": {}, "tsne": {}}
    for modality in FUSION_ORDER:
        X = fused_mats[modality]
        log.info("Projecting %s (N=%d, D=%d) with UMAP/t-SNE ...",
                 modality, X.shape[0], X.shape[1])
        projections["umap"][modality] = project_pca_umap(X, seed=args.seed)
        projections["tsne"][modality] = project_pca_tsne(X, seed=args.seed)

    def subset_by_label(label_fn, **kwargs):
        keep, y = label_fn(fusion_ids, movie_labels, **kwargs)
        idx = np.where(keep)[0]
        return idx, y

    label_specs = [
        ("decade", decade_labels, {}, False),
        ("rating", rating_labels, {}, False),
        ("genre", genre_labels, {}, False),
    ]

    for lname, lfn, kwargs, ordinal in label_specs:
        idx, y = subset_by_label(lfn, **kwargs)
        if lname == "decade":
            present = [d for d in ["1980s", "1990s", "2000s", "2010s", "2020s"] if d in set(y)]
            palette = {d: DECADE_COLORS[d] for d in present}
            label_order = present
        elif lname == "rating":
            present = [r for r in RATING_ORDER if r in set(y)]
            palette = _ordinal_palette(present)
            label_order = present
        else:  # genre
            present = [g for g in TARGET_GENRES if g in set(y)]
            present += sorted(set(y) - set(present))
            palette = _categorical_palette(present, ordered=present)
            label_order = present

        for method in ("umap", "tsne"):
            panels = {}
            for modality in FUSION_ORDER:
                coords = projections[method][modality][idx]
                panels[modality] = {"coords": coords, "labels": y}
            out_pdf = out_dir / f"fig_fusion_{lname}_{method}.pdf"
            plot_fusion_grid(panels, out_pdf, "UMAP" if method == "umap" else "t-SNE",
                             palette, label_order, ordinal=ordinal)

    # --- 5. Metrics cross-product table -----------------------------------
    all_label_specs = label_specs + [("language", language_labels, {}, False)]
    late_keys = ["fused_late", "fused_late_wp"]
    supervised_late_key = "fused_late_cv"
    late_weight_map = {
        "fused_late": (1.0, 1.0, 1.0, 1.0, 1.0),
        "fused_late_wp": (2.0, 1.0, 1.0, 1.0, 1.0),
    }
    metrics: Dict[str, Dict[str, Dict]] = {
        m: {} for m in list(FUSION_ORDER) + list(TEXT_METRIC_KEYS) + late_keys + [supervised_late_key]
    }
    for modality in FUSION_ORDER:
        for lname, lfn, kwargs, _ in all_label_specs:
            keep, y = lfn(fusion_ids, movie_labels, **kwargs)
            if keep.sum() < 5:
                continue
            if modality == "kg":
                X = kg_metric_mats[lname]
            elif modality == "fused":
                label_mats = {m: fused_mats[m] for m in (*MEDIA_MODALITIES, "text_avg")}
                label_mats["kg"] = kg_metric_mats[lname]
                X = concatenate_fusion(label_mats, pca_dim=args.pca_dim, seed=args.seed, modalities=MODALITIES)
            else:
                X = fused_mats[modality]
            sub = X[np.where(keep)[0]]
            metrics[modality][lname] = compute_metrics(sub, y, seed=args.seed)

    # Per-predicate text metrics use each predicate's native coverage so the
    # table shows both individual predicate performance and the balanced average.
    for text_key, (ids_text, X_text) in text_predicate_agg.items():
        for lname, lfn, kwargs, _ in all_label_specs:
            keep, y = lfn(ids_text, movie_labels, **kwargs)
            if keep.sum() < 5:
                continue
            metrics[text_key][lname] = compute_metrics(X_text[np.where(keep)[0]], y, seed=args.seed)

    for lname, lfn, kwargs, _ in all_label_specs:
        keep, y = lfn(fusion_ids, movie_labels, **kwargs)
        if keep.sum() < 5:
            continue
        idx = np.where(keep)[0]
        label_mats = {m: fused_mats[m] for m in (*MEDIA_MODALITIES, "text_avg")}
        label_mats["kg"] = kg_metric_mats[lname]
        Xs = [label_mats[m][idx] for m in MODALITIES]
        for key in late_keys:
            metrics[key][lname] = compute_late_fusion_metrics(
                Xs, y, seed=args.seed, weights=late_weight_map[key],
            )

        keep_supervised, y_supervised = lfn(supervised_ids, movie_labels, **kwargs)
        if keep_supervised.sum() < 5:
            continue
        sidx = np.where(keep_supervised)[0]
        supervised_names = list(MEDIA_MODALITIES) + ["kg"] + list(TEXT_METRIC_KEYS)
        supervised_mats = [
            restrict_to_ids(fusion_ids, fused_mats[m], supervised_ids)[sidx]
            for m in MEDIA_MODALITIES
        ]
        supervised_mats.append(restrict_to_ids(fusion_ids, kg_metric_mats[lname], supervised_ids)[sidx])
        for text_key in TEXT_METRIC_KEYS:
            ids_text, X_text = text_predicate_agg[text_key]
            supervised_mats.append(restrict_to_ids(ids_text, X_text, supervised_ids)[sidx])
        metrics[supervised_late_key][lname] = compute_supervised_late_fusion_cv_metrics(
            supervised_mats,
            y_supervised,
            modality_names=supervised_names,
            seed=args.seed,
            outer_folds=5,
            inner_folds=3,
            weight_step=0.25,
        )

    write_fusion_metrics_table(metrics, out_dir / "tab_fusion_metrics.tex")

    # --- 6. Retrieval figure ----------------------------------------------
    # Pick random queries with all modalities + a readable name.
    eligible = [tt for tt in fusion_ids
                if "name" in movie_labels.get(tt, {}) and tt.startswith("tt")]
    eligible.sort()  # stable before sampling
    rng = random.Random(args.seed)
    query_ids = rng.sample(eligible, k=args.retrieval_n_queries)
    log.info("Retrieval queries: %s", query_ids)

    # Symmetric retrieval pool: movies that have all modalities.
    # Each modality's row is scored by cosine similarity on its own L2-normed
    # native-dim embeddings; the "fused" row is scored by poster-weighted
    # late fusion (2:1:1:1:1) of those same similarities.
    pool_ids = fusion_ids
    id_to_pool = {i: k for k, i in enumerate(pool_ids)}
    S_per_mod = {m: fused_mats[m] @ fused_mats[m].T for m in MODALITIES}
    w_fused = np.array([2.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    w_fused /= w_fused.sum()
    S_fused = sum(wi * S_per_mod[m] for wi, m in zip(w_fused, MODALITIES))

    def topk_from_sim(S_full: np.ndarray, qi: int, k: int) -> List[Tuple[str, float]]:
        sims = S_full[qi].copy()
        sims[qi] = -np.inf
        order = np.argsort(-sims)[:k]
        return [(str(pool_ids[j]), float(sims[j])) for j in order]

    neighbors: Dict[str, Dict[str, List[Tuple[str, float]]]] = {q: {} for q in query_ids}
    for q in query_ids:
        if q not in id_to_pool:
            for m in RETRIEVAL_ROW_ORDER:
                neighbors[q][m] = []
            continue
        qi = id_to_pool[q]
        for modality in MODALITIES:
            neighbors[q][modality] = topk_from_sim(S_per_mod[modality], qi, k=5)
        neighbors[q]["fused"] = topk_from_sim(S_fused, qi, k=5)

    plot_retrieval_grid(
        queries=query_ids,
        neighbors=neighbors,
        movie_labels=movie_labels,
        media_dir=media_dir,
        out_pdf=out_dir / "fig_retrieval_grid.pdf",
        top_k=5,
    )

    (out_dir / "retrieval_neighbors.json").write_text(
        json.dumps(
            {
                q: {
                    m: [{"tt": tt, "cos": s,
                         "name": movie_labels.get(tt, {}).get("name", "")}
                        for tt, s in neighbors[q][m]]
                    for m in RETRIEVAL_ROW_ORDER
                }
                for q in query_ids
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # --- 7. Consistency figure --------------------------------------------
    ids_img_raw, _, X_img_raw = raw["image"]
    plot_consistency(
        entity_ids_raw=ids_img_raw,
        X_raw=X_img_raw,
        top_n_movies=args.consistency_top_n,
        movie_labels=movie_labels,
        out_pdf_umap=out_dir / "fig_consistency_umap.pdf",
        out_pdf_tsne=out_dir / "fig_consistency_tsne.pdf",
        seed=args.seed,
    )

    # --- 8. Save raw metrics + projections --------------------------------
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    npz_kwargs = {}
    for method in ("umap", "tsne"):
        for modality in FUSION_ORDER:
            npz_kwargs[f"{method}_{modality}"] = projections[method][modality]
    npz_kwargs["fusion_ids"] = fusion_ids
    np.savez(out_dir / "projections.npz", **npz_kwargs)

    log.info("Done. Outputs in %s", out_dir)


if __name__ == "__main__":
    main()
