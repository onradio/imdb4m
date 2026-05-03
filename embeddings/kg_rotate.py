#!/usr/bin/env python3
"""Train RotatE embeddings for the IMDB4M knowledge graph.

The script trains one or more PyKEEN RotatE models on the pruned KG, exports
all URIRef entity embeddings for release use, and writes an exhaustive dump of
every trained PyKEEN entity for reproducibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import numpy as np
from rdflib import BNode, Graph, Literal, URIRef

from .config import DEFAULT_EMBED_OUTPUT_DIR
from .kg_config import (
    ALL_TRAINING_VARIANTS,
    DEFAULT_KG_BATCH_SIZE,
    DEFAULT_KG_EMBED_DIM,
    DEFAULT_KG_EPOCHS,
    DEFAULT_KG_PATH,
    DEFAULT_KG_SEED,
    SCHEMA_NS,
    VARIANT_TO_HELDOUT,
    VARIANT_TO_MODALITY,
)
from .kg_storage import KGEmbeddingRecord, PyKEENEntityEmbeddingRecord, write_kg_embeddings, write_pykeen_entity_embeddings

logger = logging.getLogger(__name__)

TITLE_URI_RE = r"https?://www\.imdb\.com/title/(tt\d+)/?"
NAME_URI_RE = r"https?://www\.imdb\.com/name/(nm\d+)/?"
MEDIA_ID_RE = r"/((?:rm|vi)\d+)(?:[/?#]|$)"


class LossEarlyStoppingCallback:
    """Stop training when epoch loss converges and restore best-loss weights."""

    def __init__(
        self,
        patience: int = 20,
        min_relative_delta: float = 0.001,
        best_model_path: str | Path | None = None,
    ) -> None:
        self.patience = patience
        self.min_relative_delta = min_relative_delta
        self.best_model_path = Path(best_model_path) if best_model_path else None
        self._training_loop = None
        self.best_loss = float("inf")
        self.best_epoch = 0
        self.bad_epochs = 0
        self.stopped = False

    def register_training_loop(self, training_loop) -> None:
        self._training_loop = training_loop

    @property
    def training_loop(self):
        if self._training_loop is None:
            raise ValueError("Callback was never initialized")
        return self._training_loop

    def _save_best(self) -> None:
        if self.best_model_path is None:
            return
        import torch

        self.best_model_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.training_loop.model.state_dict(), self.best_model_path)

    def _load_best(self) -> None:
        if self.best_model_path is None or not self.best_model_path.exists():
            return
        import torch

        try:
            state_dict = torch.load(
                self.best_model_path,
                map_location=self.training_loop.model.device,
                weights_only=True,
            )
        except TypeError:
            state_dict = torch.load(self.best_model_path, map_location=self.training_loop.model.device)
        self.training_loop.model.load_state_dict(state_dict)

    def pre_batch(self, **kwargs) -> None:
        pass

    def on_batch(self, epoch: int, batch, batch_loss: float, **kwargs) -> None:
        pass

    def pre_step(self, **kwargs) -> None:
        pass

    def post_batch(self, epoch: int, batch, **kwargs) -> None:
        pass

    def post_epoch(self, epoch: int, epoch_loss: float, **kwargs) -> None:
        if not np.isfinite(epoch_loss):
            logger.warning("Non-finite epoch loss at epoch %d: %s", epoch, epoch_loss)
            self.bad_epochs += 1
        elif self.best_loss == float("inf"):
            self.best_loss = float(epoch_loss)
            self.best_epoch = epoch
            self.bad_epochs = 0
            self._save_best()
        else:
            relative_improvement = (self.best_loss - float(epoch_loss)) / max(abs(self.best_loss), 1e-12)
            if relative_improvement >= self.min_relative_delta:
                self.best_loss = float(epoch_loss)
                self.best_epoch = epoch
                self.bad_epochs = 0
                self._save_best()
            else:
                self.bad_epochs += 1

        if self.bad_epochs >= self.patience:
            logger.info(
                "Stopping on loss convergence at epoch %d; best loss %.6f at epoch %d",
                epoch,
                self.best_loss,
                self.best_epoch,
            )
            self._load_best()
            self.training_loop._should_stop = True
            self.stopped = True

    def post_train(self, losses: list[float], **kwargs) -> None:
        self._load_best()


@dataclass(frozen=True)
class ParsedKG:
    """String triples plus metadata for every parsed PyKEEN node label."""

    triples: List[tuple[str, str, str]]
    node_metadata: Dict[str, "NodeMetadata"]
    predicate_counts: Dict[str, int]


@dataclass
class KGTrainingResult:
    """Minimal training result used by the export pipeline."""

    model: object
    losses: List[float]
    metric_results: object = None


@dataclass(frozen=True)
class NodeMetadata:
    """Metadata preserved from an RDF node before conversion to PyKEEN labels."""

    node_kind: str
    pykeen_label: str
    kg_uri: str = ""
    datatype: str = ""
    language: str = ""


def _imdb_title_id(uri: str) -> str | None:
    m = re.search(TITLE_URI_RE, uri)
    return m.group(1) if m else None


def _imdb_name_id(uri: str) -> str | None:
    m = re.search(NAME_URI_RE, uri)
    return m.group(1) if m else None


def _imdb_media_id(uri: str) -> str | None:
    m = re.search(MEDIA_ID_RE, uri)
    return m.group(1) if m else None


def _literal_label(value: Literal) -> str:
    datatype = str(value.datatype) if value.datatype else ""
    language = value.language or ""
    payload = value.n3()
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"literal:{datatype}:{language}:{digest}"


def _node_label(node) -> str:
    if isinstance(node, URIRef):
        return str(node)
    if isinstance(node, Literal):
        return _literal_label(node)
    return f"bnode:{node}"


def _node_metadata(node) -> NodeMetadata:
    label = _node_label(node)
    if isinstance(node, URIRef):
        return NodeMetadata(node_kind="uri", pykeen_label=label, kg_uri=str(node))
    if isinstance(node, Literal):
        return NodeMetadata(
            node_kind="literal",
            pykeen_label=label,
            datatype=str(node.datatype) if node.datatype else "",
            language=node.language or "",
        )
    if isinstance(node, BNode):
        return NodeMetadata(node_kind="bnode", pykeen_label=label)
    return NodeMetadata(node_kind="bnode", pykeen_label=label)


def _stable_hash(text: str, length: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def _derive_uri_entity_id(uri: str) -> str:
    for extractor in (_imdb_media_id, _imdb_title_id, _imdb_name_id):
        value = extractor(uri)
        if value:
            return value
    return f"kg_{_stable_hash(uri)}"


def _derive_non_uri_entity_id(meta: NodeMetadata) -> str:
    prefix = "literal" if meta.node_kind == "literal" else "bnode"
    return f"{prefix}_{_stable_hash(meta.pykeen_label)}"


def _deduplicate_entity_ids(records: List[KGEmbeddingRecord]) -> List[KGEmbeddingRecord]:
    """Append a hash suffix if multiple URI resources derive the same ID."""

    counts: Dict[str, int] = {}
    for rec in records:
        counts[rec.entity_id] = counts.get(rec.entity_id, 0) + 1
    seen: Dict[str, int] = {}
    out: List[KGEmbeddingRecord] = []
    for rec in sorted(records, key=lambda r: (r.entity_id, r.kg_uri)):
        seen[rec.entity_id] = seen.get(rec.entity_id, 0) + 1
        entity_id = rec.entity_id
        if counts[rec.entity_id] > 1 and seen[rec.entity_id] > 1:
            entity_id = f"{rec.entity_id}_{_stable_hash(rec.kg_uri, length=8)}"
        out.append(
            KGEmbeddingRecord(
                entity_id=entity_id,
                kg_uri=rec.kg_uri,
                source_url=rec.source_url,
                filename=f"kg_entity:{entity_id}",
                embedding=rec.embedding,
            )
        )
    return out


def parse_kg(kg_path: Path, max_triples: int | None = None) -> ParsedKG:
    """Parse Turtle into PyKEEN-ready triples and collect node metadata."""

    logger.info("Parsing KG from %s", kg_path)
    graph = Graph()
    graph.parse(str(kg_path), format="turtle")

    triples: List[tuple[str, str, str]] = []
    predicate_counts: Dict[str, int] = {}
    node_metadata: Dict[str, NodeMetadata] = {}

    for subj, pred, obj in graph:
        p = str(pred)
        predicate_counts[p] = predicate_counts.get(p, 0) + 1

        s_label = _node_label(subj)
        o_label = _node_label(obj)
        node_metadata.setdefault(s_label, _node_metadata(subj))
        node_metadata.setdefault(o_label, _node_metadata(obj))

        triples.append((s_label, p, o_label))
        if max_triples is not None and len(triples) >= max_triples:
            logger.warning("Stopped after --max-triples=%d for smoke testing", max_triples)
            break

    logger.info(
        "Parsed %d triples, %d predicates, %d PyKEEN node labels",
        len(triples),
        len(predicate_counts),
        len(node_metadata),
    )
    return ParsedKG(
        triples=triples,
        node_metadata=node_metadata,
        predicate_counts=predicate_counts,
    )


def filter_triples(
    triples: Iterable[tuple[str, str, str]],
    heldout_predicates: frozenset[str],
) -> tuple[List[tuple[str, str, str]], int]:
    """Remove held-out predicates for leakage-controlled variants."""

    kept: List[tuple[str, str, str]] = []
    removed = 0
    for triple in triples:
        if triple[1] in heldout_predicates:
            removed += 1
            continue
        kept.append(triple)
    return kept, removed


def _set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _metric_results_to_dict(metric_results) -> dict:
    if metric_results is None:
        return {}
    for attr in ("to_dict", "to_flat_dict"):
        fn = getattr(metric_results, attr, None)
        if fn is None:
            continue
        try:
            return fn()
        except Exception:
            continue
    return {}


def _entity_embeddings_for_labels(
    model,
    entity_to_id: Dict[str, int],
    labels: Sequence[str],
) -> Dict[str, np.ndarray]:
    """Return exported real-valued vectors for PyKEEN entity labels."""

    import torch

    if not labels:
        return {}
    device = next(model.parameters()).device
    representation = model.entity_representations[0]
    indices = torch.as_tensor([entity_to_id[label] for label in labels], dtype=torch.long, device=device)
    with torch.no_grad():
        values = representation(indices=indices).detach().cpu().numpy()
    values = np.asarray(values)
    if np.iscomplexobj(values):
        values = np.concatenate([values.real, values.imag], axis=-1)
    values = values.reshape(values.shape[0], -1).astype(np.float32)
    return {label: values[i] for i, label in enumerate(labels)}


def _extract_uri_records(
    model,
    entity_to_id: Dict[str, int],
    node_metadata: Dict[str, NodeMetadata],
) -> List[KGEmbeddingRecord]:
    """Export one release-facing row for each trained URIRef entity."""

    labels = sorted(
        label
        for label, meta in node_metadata.items()
        if meta.node_kind == "uri" and label in entity_to_id
    )
    vectors = _entity_embeddings_for_labels(model, entity_to_id, labels)
    records = [
        KGEmbeddingRecord(
            entity_id=_derive_uri_entity_id(node_metadata[label].kg_uri),
            kg_uri=node_metadata[label].kg_uri,
            embedding=vectors[label],
        )
        for label in labels
    ]
    records = _deduplicate_entity_ids(records)
    logger.info("Exported %d URIRef KG entity embeddings", len(records))
    return records


def _deduplicate_pykeen_entity_ids(
    records: List[PyKEENEntityEmbeddingRecord],
) -> List[PyKEENEntityEmbeddingRecord]:
    counts: Dict[str, int] = {}
    for rec in records:
        counts[rec.entity_id] = counts.get(rec.entity_id, 0) + 1
    seen: Dict[str, int] = {}
    out: List[PyKEENEntityEmbeddingRecord] = []
    for rec in sorted(records, key=lambda r: (r.entity_id, r.pykeen_label)):
        seen[rec.entity_id] = seen.get(rec.entity_id, 0) + 1
        entity_id = rec.entity_id
        if counts[rec.entity_id] > 1 and seen[rec.entity_id] > 1:
            entity_id = f"{rec.entity_id}_{_stable_hash(rec.pykeen_label, length=8)}"
        out.append(
            PyKEENEntityEmbeddingRecord(
                entity_id=entity_id,
                kg_uri=rec.kg_uri,
                source_url=rec.source_url,
                filename=f"kg_entity:{entity_id}",
                embedding=rec.embedding,
                node_kind=rec.node_kind,
                pykeen_label=rec.pykeen_label,
            )
        )
    return out


def _extract_pykeen_entity_records(
    model,
    entity_to_id: Dict[str, int],
    node_metadata: Dict[str, NodeMetadata],
) -> List[PyKEENEntityEmbeddingRecord]:
    """Export every trained PyKEEN entity, including literals and blank nodes."""

    labels = sorted(entity_to_id)
    vectors = _entity_embeddings_for_labels(model, entity_to_id, labels)
    records: List[PyKEENEntityEmbeddingRecord] = []
    for label in labels:
        meta = node_metadata.get(label)
        if meta is None:
            meta = NodeMetadata(node_kind="unknown", pykeen_label=label)
        if meta.node_kind == "uri":
            entity_id = _derive_uri_entity_id(meta.kg_uri)
            kg_uri = meta.kg_uri
        else:
            entity_id = _derive_non_uri_entity_id(meta)
            kg_uri = ""
        records.append(
            PyKEENEntityEmbeddingRecord(
                entity_id=entity_id,
                kg_uri=kg_uri,
                embedding=vectors[label],
                node_kind=meta.node_kind,
                pykeen_label=label,
            )
        )
    records = _deduplicate_pykeen_entity_ids(records)
    logger.info("Exported %d exhaustive PyKEEN entity embeddings", len(records))
    return records


def _dependency_versions() -> dict:
    versions = {}
    for name in ("numpy", "rdflib", "torch", "pykeen"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            versions[name] = "not-installed"
    return versions


def _train_rotate_with_loss_convergence(
    training,
    dim: int,
    epochs: int,
    batch_size: int,
    device: str,
    seed: int,
    loss_callback: LossEarlyStoppingCallback,
) -> KGTrainingResult:
    """Train RotatE directly and stop on training-loss convergence."""

    import torch
    from pykeen.models import RotatE
    from pykeen.training import SLCWATrainingLoop

    model = RotatE(triples_factory=training, embedding_dim=dim, random_seed=seed)
    model = model.to(torch.device(device))
    optimizer = torch.optim.Adam(params=model.get_grad_params())
    training_loop = SLCWATrainingLoop(
        model=model,
        triples_factory=training,
        optimizer=optimizer,
    )
    losses = training_loop.train(
        triples_factory=training,
        num_epochs=epochs,
        batch_size=batch_size,
        callbacks=[loss_callback],
    )
    return KGTrainingResult(model=model, losses=losses or [])


def train_variant(
    parsed: ParsedKG,
    variant: str,
    output_dir: Path,
    dim: int,
    epochs: int,
    batch_size: int,
    seed: int,
    device: str,
    storage_format: str,
    save_model: bool,
    overwrite_hdf5_group: bool,
    early_stopping: bool,
    stopping_mode: str,
    loss_patience: int,
    loss_min_relative_delta: float,
    early_stopping_frequency: int,
    early_stopping_patience: int,
    early_stopping_relative_delta: float,
    early_stopping_metric: str,
    early_stopping_slice_size: int,
) -> dict:
    """Train one RotatE variant and write URIRef plus exhaustive exports."""

    try:
        from pykeen.pipeline import pipeline
        from pykeen.triples import TriplesFactory
    except ImportError as exc:
        raise RuntimeError(
            "PyKEEN is required for KG RotatE training. Install dependencies from requirements.txt."
        ) from exc

    _set_seeds(seed)
    modality = VARIANT_TO_MODALITY[variant]
    heldout = VARIANT_TO_HELDOUT[variant]
    triples, removed = filter_triples(parsed.triples, heldout)
    if not triples:
        raise ValueError(f"No triples remain for variant {variant}")

    logger.info(
        "Training %s (%s): %d triples, removed %d held-out triples",
        variant,
        modality,
        len(triples),
        removed,
    )

    triples_array = np.asarray(triples, dtype=str)
    factory = TriplesFactory.from_labeled_triples(triples_array, create_inverse_triples=False)
    validation = None
    testing = None
    if stopping_mode == "validation":
        try:
            training, validation, testing = factory.split([0.8, 0.1, 0.1], random_state=seed)
        except ValueError as exc:
            logger.warning("Falling back to train-only triples for %s: %s", variant, exc)
            training, validation, testing = factory, None, factory
    else:
        training = factory

    best_loss_path = output_dir / "kg_rotate_models" / variant / "best-loss-model.pt"
    loss_callback = None
    loss_stopping_used = stopping_mode == "loss"
    validation_stopping_used = bool(early_stopping and stopping_mode == "validation" and validation is not None)
    if loss_stopping_used:
        loss_callback = LossEarlyStoppingCallback(
            patience=loss_patience if early_stopping else epochs + 1,
            min_relative_delta=loss_min_relative_delta,
            best_model_path=best_loss_path,
        )
        result = _train_rotate_with_loss_convergence(
            training=training,
            dim=dim,
            epochs=epochs,
            batch_size=batch_size,
            device=device,
            seed=seed,
            loss_callback=loss_callback,
        )
    else:
        pipeline_kwargs = {
            "training": training,
            "validation": validation,
            "testing": testing or training,
            "model": "RotatE",
            "model_kwargs": {"embedding_dim": dim},
            "training_kwargs": {"num_epochs": epochs, "batch_size": batch_size},
            "random_seed": seed,
            "device": device,
            "use_testing_data": stopping_mode == "validation",
        }
        if validation_stopping_used:
            pipeline_kwargs.update(
                {
                    "stopper": "early",
                    "evaluation_kwargs": {"slice_size": early_stopping_slice_size},
                    "stopper_kwargs": {
                        "frequency": early_stopping_frequency,
                        "patience": early_stopping_patience,
                        "relative_delta": early_stopping_relative_delta,
                        "metric": early_stopping_metric,
                        "evaluation_slice_size": early_stopping_slice_size,
                    },
                }
            )
        elif early_stopping and stopping_mode == "validation":
            logger.warning("Validation early stopping requested for %s but no validation split is available", variant)
        result = pipeline(**pipeline_kwargs)

    if save_model:
        model_dir = output_dir / "kg_rotate_models" / variant
        model_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(result, "save_to_directory"):
            result.save_to_directory(model_dir)
        else:
            import torch

            torch.save(result.model.state_dict(), model_dir / "trained_model_state_dict.pt")
            (model_dir / "training_summary.json").write_text(
                json.dumps(
                    {
                        "variant": variant,
                        "model": "RotatE",
                        "dimension": dim,
                        "losses": [float(x) for x in getattr(result, "losses", [])],
                        "loss_best_epoch": loss_callback.best_epoch if loss_callback else None,
                        "loss_best": loss_callback.best_loss if loss_callback else None,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    else:
        model_dir = None

    uri_records = _extract_uri_records(result.model, factory.entity_to_id, parsed.node_metadata)
    pykeen_records = _extract_pykeen_entity_records(result.model, factory.entity_to_id, parsed.node_metadata)
    exported_dim = int(uri_records[0].embedding.shape[0]) if uri_records else 0
    model_id = f"pykeen/rotate/imdb4m-{variant}-d{dim}"
    uri_written = write_kg_embeddings(
        uri_records,
        output_dir=output_dir,
        modality=modality,
        model_id=model_id,
        storage_format=storage_format,
        overwrite_group=overwrite_hdf5_group,
    )
    pykeen_file_stem = f"{modality}_pykeen_entities"
    pykeen_written = write_pykeen_entity_embeddings(
        pykeen_records,
        output_dir=output_dir,
        file_stem=pykeen_file_stem,
        group_name=pykeen_file_stem,
        model_id=model_id,
        storage_format=storage_format,
        overwrite_group=overwrite_hdf5_group,
    )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "modality": modality,
        "model_id": model_id,
        "dimension": dim,
        "exported_embedding_dim": exported_dim,
        "epochs": epochs,
        "batch_size": batch_size,
        "early_stopping": {
            "requested": early_stopping,
            "mode": stopping_mode,
            "used": loss_stopping_used or validation_stopping_used,
            "loss_patience": loss_patience,
            "loss_min_relative_delta": loss_min_relative_delta,
            "loss_best_epoch": loss_callback.best_epoch if loss_callback else None,
            "loss_best": loss_callback.best_loss if loss_callback else None,
            "loss_stopped": loss_callback.stopped if loss_callback else None,
            "frequency": early_stopping_frequency,
            "patience": early_stopping_patience,
            "relative_delta": early_stopping_relative_delta,
            "metric": early_stopping_metric,
            "evaluation_slice_size": early_stopping_slice_size,
        },
        "seed": seed,
        "device": device,
        "final_link_prediction_evaluation": stopping_mode == "validation",
        "input_triples": len(parsed.triples),
        "training_variant_triples": len(triples),
        "removed_triples": removed,
        "heldout_predicates": sorted(heldout),
        "uri_entity_embeddings": len(uri_records),
        "pykeen_entity_embeddings": len(pykeen_records),
        "storage": uri_written,
        "pykeen_entity_storage": pykeen_written,
        "model_dir": str(model_dir) if model_dir else "",
        "losses": [float(x) for x in getattr(result, "losses", [])],
        "metrics": _metric_results_to_dict(getattr(result, "metric_results", None)),
        "dependency_versions": _dependency_versions(),
    }
    manifest_path = output_dir / f"kg_rotate_{variant.replace('-', '_')}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Wrote manifest to %s", manifest_path)
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg", default=DEFAULT_KG_PATH, help="Path to the pruned KG Turtle file.")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_EMBED_OUTPUT_DIR)
    parser.add_argument(
        "--variant",
        choices=("all",) + ALL_TRAINING_VARIANTS,
        default="full",
        help="'all' trains full, per-label heldout, and all-labels variants.",
    )
    parser.add_argument("--dim", type=int, default=DEFAULT_KG_EMBED_DIM)
    parser.add_argument("--epochs", type=int, default=DEFAULT_KG_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_KG_BATCH_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_KG_SEED)
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--format", choices=("parquet", "hdf5", "all"), default="all")
    parser.add_argument("--max-triples", type=int, default=None, help="Smoke-test on the first N triples only.")
    parser.add_argument("--quick", action="store_true", help="Smoke-test defaults: 5 epochs and dim capped at 64.")
    parser.add_argument("--no-early-stopping", action="store_true", help="Train for the fixed --epochs count.")
    parser.add_argument("--stopping-mode", choices=("loss", "validation"), default="loss",
                        help="Use training-loss convergence or validation ranking for early stopping.")
    parser.add_argument("--loss-patience", type=int, default=20,
                        help="Stop after this many epochs without sufficient training-loss improvement.")
    parser.add_argument("--loss-min-relative-delta", type=float, default=0.001,
                        help="Minimum relative training-loss improvement required to reset patience.")
    parser.add_argument("--early-stopping-frequency", type=int, default=10,
                        help="Evaluate validation metrics every N epochs for validation early stopping.")
    parser.add_argument("--early-stopping-patience", type=int, default=20,
                        help="Stop after this many validation checks without sufficient improvement.")
    parser.add_argument("--early-stopping-relative-delta", type=float, default=0.002,
                        help="Minimum relative validation metric improvement required to reset patience.")
    parser.add_argument("--early-stopping-metric", default="mean_reciprocal_rank",
                        help="PyKEEN validation metric monitored by early stopping.")
    parser.add_argument("--early-stopping-slice-size", type=int, default=2048,
                        help="Entity slice size for validation ranking during early stopping.")
    parser.add_argument("--no-save-model", action="store_true", help="Skip saving PyKEEN result directories.")
    parser.add_argument(
        "--no-overwrite-hdf5-group",
        action="store_true",
        help="Fail if the target HDF5 group already exists.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
    )

    if args.device == "cuda":
        try:
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        except ImportError as exc:
            raise RuntimeError("CUDA was requested but torch is not installed") from exc

    dim = min(args.dim, 64) if args.quick else args.dim
    epochs = 5 if args.quick else args.epochs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = ALL_TRAINING_VARIANTS if args.variant == "all" else (args.variant,)

    parsed = parse_kg(Path(args.kg), max_triples=args.max_triples)
    manifests = []
    for variant in variants:
        manifests.append(
            train_variant(
                parsed=parsed,
                variant=variant,
                output_dir=output_dir,
                dim=dim,
                epochs=epochs,
                batch_size=args.batch_size,
                seed=args.seed,
                device=args.device,
                storage_format=args.format,
                save_model=not args.no_save_model,
                overwrite_hdf5_group=not args.no_overwrite_hdf5_group,
                early_stopping=not args.no_early_stopping,
                stopping_mode=args.stopping_mode,
                loss_patience=args.loss_patience,
                loss_min_relative_delta=args.loss_min_relative_delta,
                early_stopping_frequency=args.early_stopping_frequency,
                early_stopping_patience=args.early_stopping_patience,
                early_stopping_relative_delta=args.early_stopping_relative_delta,
                early_stopping_metric=args.early_stopping_metric,
                early_stopping_slice_size=args.early_stopping_slice_size,
            )
        )

    index_path = output_dir / "kg_rotate_runs.json"
    index_path.write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    logger.info("Done. Wrote %d KG RotatE run(s)", len(manifests))


if __name__ == "__main__":
    main()
