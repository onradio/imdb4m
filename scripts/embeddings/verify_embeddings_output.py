"""Verify completeness and integrity of files in embeddings_output/.

Checks performed:
- Parquet files: schema, row counts, embedding shape, no NaN/Inf, L2-normalised,
  uniqueness of entity_id (where expected).
- HDF5 master file: groups, dataset shapes, parallel-array lengths, alignment
  with parquet (entity_id), normalisation, group attrs.
- Progress JSON: per-modality counts vs parquet row counts.
- kg_rotate manifests: entity counts vs parquet row counts.
- embedding_metadata.ttl: imdb4m:hasEmbedding records per modality match
  parquet row counts (counted with regex, no rdflib parse to keep it fast).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import h5py
import numpy as np
import pyarrow.parquet as pq

from scripts.paths import EMBEDDINGS_OUTPUT

OUT = EMBEDDINGS_OUTPUT
TOL_NORM = 5e-3

EXPECTED_MODALITIES: Dict[str, Tuple[int, int]] = {
    "image": (33_247, 768),
    "video": (4_350, 512),
    "audio": (4_034, 512),
    "text":  (4_216, 1024),
}
KG_EXPECTED_DIM = 512
KG_FULL_EXPECTED = 139_465
KG_PYKEEN_FULL_EXPECTED = 656_003

HELDOUT_VARIANTS = ["all_labels", "decade", "genre", "language", "rating"]


def _ok(label: str, msg: str = "") -> None:
    print(f"  [OK]   {label}" + (f"  {msg}" if msg else ""))

def _warn(label: str, msg: str) -> None:
    print(f"  [WARN] {label}  {msg}")

def _fail(label: str, msg: str) -> None:
    print(f"  [FAIL] {label}  {msg}")


def check_parquet_embeddings(
    path: Path,
    *,
    expected_rows: Optional[int],
    expected_dim: int,
    require_kg_uri_nonempty: bool,
    extra_columns: Tuple[str, ...] = (),
) -> Tuple[bool, int, np.ndarray]:
    """Returns (ok, rows, entity_id_array)."""
    print(f"\n{path.name}")
    if not path.exists():
        _fail(path.name, "missing")
        return False, 0, np.array([])

    try:
        t = pq.read_table(path)
    except Exception as exc:
        _fail("open", repr(exc))
        return False, 0, np.array([])

    n = t.num_rows
    cols = set(t.column_names)
    _ok("rows", f"= {n:,}")
    if expected_rows is not None and n != expected_rows:
        _warn("rows", f"expected {expected_rows:,}, got {n:,}")

    required = {"entity_id", "kg_uri", "source_url", "filename", "model_id", "embedding"} | set(extra_columns)
    missing = required - cols
    if missing:
        _fail("schema", f"missing columns: {sorted(missing)}")
        return False, n, np.array([])
    _ok("schema", f"columns = {sorted(cols)}")

    df = t.to_pandas()
    emb = np.stack(df["embedding"].to_numpy()).astype(np.float32, copy=False)
    if emb.shape != (n, expected_dim):
        _fail("embedding shape", f"expected ({n},{expected_dim}), got {emb.shape}")
        return False, n, df["entity_id"].to_numpy()
    _ok("embedding shape", f"= {emb.shape}, dtype={emb.dtype}")

    n_nan = int(np.isnan(emb).sum())
    n_inf = int(np.isinf(emb).sum())
    if n_nan or n_inf:
        _fail("finite values", f"NaN={n_nan}, Inf={n_inf}")
    else:
        _ok("finite values", "no NaN / no Inf")

    norms = np.linalg.norm(emb, axis=1)
    n_zero = int((norms == 0.0).sum())
    if n_zero:
        _warn("zero-norm rows", f"{n_zero}")
    nz = norms[norms > 0]
    if nz.size:
        max_dev = float(np.max(np.abs(nz - 1.0)))
        if max_dev > TOL_NORM:
            _fail("L2-normalised", f"max |‖x‖-1| = {max_dev:.3e} (tol {TOL_NORM:.0e})")
        else:
            _ok("L2-normalised", f"max |‖x‖-1| = {max_dev:.3e}")

    entity_ids = df["entity_id"].to_numpy()
    n_empty_id = int((entity_ids == "").sum())
    if n_empty_id:
        _fail("entity_id non-empty", f"{n_empty_id} empty")
    else:
        _ok("entity_id non-empty", f"all {n} populated")

    n_unique = int(np.unique(entity_ids).size)
    if n_unique != n:
        # The PyKEEN entity dump can have duplicate entity_id across (node_kind, label),
        # so this is informational for that file.
        _warn("entity_id uniqueness", f"{n - n_unique} duplicates ({n_unique} unique)")
    else:
        _ok("entity_id uniqueness", "all unique")

    if require_kg_uri_nonempty:
        kg_uris = df["kg_uri"].to_numpy()
        n_empty_uri = int((kg_uris == "").sum())
        if n_empty_uri:
            _warn("kg_uri non-empty", f"{n_empty_uri} empty rows")
        else:
            _ok("kg_uri non-empty", f"all {n} populated")

    return True, n, entity_ids


def check_hdf5(
    h5_path: Path,
    parquet_ids: Dict[str, np.ndarray],
    parquet_dims: Dict[str, int],
) -> bool:
    print(f"\n{h5_path.name}")
    if not h5_path.exists():
        _fail("file", "missing")
        return False
    all_ok = True
    try:
        hf = h5py.File(h5_path, "r")
    except Exception as exc:
        _fail("open", repr(exc))
        return False

    with hf:
        groups = sorted(hf.keys())
        _ok("groups", f"= {groups}")

        for grp_name, ids in parquet_ids.items():
            if grp_name not in hf:
                _fail(f"/{grp_name}", "group missing")
                all_ok = False
                continue
            g = hf[grp_name]
            datasets = set(g.keys())
            required = {"embeddings", "entity_id", "kg_uri", "source_url", "filename"}
            missing = required - datasets
            if missing:
                _fail(f"/{grp_name} datasets", f"missing {sorted(missing)}")
                all_ok = False
                continue

            emb = g["embeddings"]
            n_h5 = emb.shape[0]
            d_h5 = emb.shape[1] if emb.ndim == 2 else None
            n_parq = len(ids)
            d_parq = parquet_dims[grp_name]

            if n_h5 != n_parq:
                _fail(f"/{grp_name} rows", f"hdf5={n_h5} != parquet={n_parq}")
                all_ok = False
            else:
                _ok(f"/{grp_name} rows", f"= {n_h5:,}")

            if d_h5 != d_parq:
                _fail(f"/{grp_name} dim", f"hdf5={d_h5} != parquet={d_parq}")
                all_ok = False
            else:
                _ok(f"/{grp_name} dim", f"= {d_h5}")

            sample = emb[: min(2048, n_h5)]
            n_nan = int(np.isnan(sample).sum())
            n_inf = int(np.isinf(sample).sum())
            if n_nan or n_inf:
                _fail(f"/{grp_name} finite", f"NaN={n_nan}, Inf={n_inf} in first {sample.shape[0]} rows")
                all_ok = False
            else:
                norms = np.linalg.norm(sample, axis=1)
                nz = norms[norms > 0]
                if nz.size and float(np.max(np.abs(nz - 1.0))) > TOL_NORM:
                    _fail(f"/{grp_name} norms", f"max |‖x‖-1|={float(np.max(np.abs(nz-1.0))):.3e}")
                    all_ok = False
                else:
                    _ok(f"/{grp_name} sample finite + normed", f"first {sample.shape[0]} rows OK")

            # Parallel array length check
            for col in ("entity_id", "kg_uri", "source_url", "filename"):
                arr_n = g[col].shape[0]
                if arr_n != n_h5:
                    _fail(f"/{grp_name} {col} length", f"{arr_n} != {n_h5}")
                    all_ok = False
            else:
                _ok(f"/{grp_name} parallel arrays", "lengths match embeddings")

            # Spot-check alignment with parquet (first/last entity_id)
            id_h5_first = g["entity_id"][0].decode("utf-8") if isinstance(g["entity_id"][0], bytes) else str(g["entity_id"][0])
            id_h5_last  = g["entity_id"][-1].decode("utf-8") if isinstance(g["entity_id"][-1], bytes) else str(g["entity_id"][-1])
            if n_parq > 0:
                if id_h5_first != ids[0] or id_h5_last != ids[-1]:
                    _fail(
                        f"/{grp_name} alignment",
                        f"first/last mismatch hdf5=({id_h5_first!r},{id_h5_last!r}) parquet=({ids[0]!r},{ids[-1]!r})",
                    )
                    all_ok = False
                else:
                    _ok(f"/{grp_name} alignment", f"first/last entity_id match parquet")

            attrs = dict(g.attrs)
            for k in ("model_id", "embed_dim", "count"):
                if k not in attrs:
                    _warn(f"/{grp_name} attrs", f"missing '{k}'")
                else:
                    if k == "count" and int(attrs["count"]) != n_h5:
                        _warn(f"/{grp_name} attrs", f"count attr={int(attrs['count'])} != rows={n_h5}")

    return all_ok


def check_progress(parquet_counts: Dict[str, int]) -> None:
    print("\nembed_progress.json")
    p = OUT / "embed_progress.json"
    if not p.exists():
        _fail("file", "missing")
        return
    d = json.loads(p.read_text())
    for m in ("image", "video", "audio", "text"):
        if m not in d:
            _fail(m, "key missing")
            continue
        n_prog = len(d[m])
        n_parq = parquet_counts.get(m, -1)
        if n_prog != n_parq:
            _warn(m, f"progress={n_prog:,} vs parquet={n_parq:,}")
        else:
            _ok(m, f"progress={n_prog:,} matches parquet")


def check_manifests(uri_counts: Dict[str, int], pykeen_counts: Dict[str, int]) -> None:
    print("\nkg_rotate manifests")

    variant_to_files = {
        "full": ("kg_embeddings", "kg_pykeen_entities"),
        "all_labels": ("kg_heldout_all_labels_embeddings", "kg_heldout_all_labels_pykeen_entities"),
        "decade": ("kg_heldout_decade_embeddings", "kg_heldout_decade_pykeen_entities"),
        "genre": ("kg_heldout_genre_embeddings", "kg_heldout_genre_pykeen_entities"),
        "language": ("kg_heldout_language_embeddings", "kg_heldout_language_pykeen_entities"),
        "rating": ("kg_heldout_rating_embeddings", "kg_heldout_rating_pykeen_entities"),
    }

    for variant, (uri_stem, pyk_stem) in variant_to_files.items():
        manifest = OUT / f"kg_rotate_{variant}_manifest.json"
        if not manifest.exists():
            _fail(manifest.name, "missing")
            continue
        m = json.loads(manifest.read_text())
        n_uri = m.get("uri_entity_embeddings")
        n_pyk = m.get("pykeen_entity_embeddings")
        d = m.get("exported_embedding_dim")

        n_uri_parq = uri_counts.get(uri_stem)
        n_pyk_parq = pykeen_counts.get(pyk_stem)

        label = f"{variant} (dim={d})"
        if n_uri == n_uri_parq:
            _ok(label, f"URI={n_uri:,} matches parquet")
        else:
            _fail(label, f"URI manifest={n_uri:,} vs parquet={n_uri_parq}")

        if n_pyk == n_pyk_parq:
            _ok(label + " pykeen", f"{n_pyk:,} matches parquet")
        else:
            _fail(label + " pykeen", f"manifest={n_pyk:,} vs parquet={n_pyk_parq}")

        if d != KG_EXPECTED_DIM:
            _warn(label, f"exported_embedding_dim={d} != {KG_EXPECTED_DIM}")

        if "early_stopping" in m and m["early_stopping"].get("loss_stopped"):
            _ok(label + " early_stop",
                f"loss best={m['early_stopping'].get('loss_best'):.4g} @ epoch {m['early_stopping'].get('loss_best_epoch')}")


def check_metadata_ttl(parquet_counts: Dict[str, int]) -> None:
    print("\nembedding_metadata.ttl")
    p = OUT / "embedding_metadata.ttl"
    if not p.exists():
        _fail("file", "missing")
        return
    text = p.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r'imdb4m:modality\s+"([^"]+)"')
    counts: Dict[str, int] = {}
    for m in pat.finditer(text):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    _ok("modalities seen", f"= {sorted(counts)}")
    for m, n in sorted(counts.items()):
        n_parq = parquet_counts.get(m, -1)
        if n_parq < 0:
            _warn(m, f"ttl has {n:,} but no parquet to compare")
        elif n != n_parq:
            _warn(m, f"ttl={n:,} vs parquet={n_parq:,}")
        else:
            _ok(m, f"ttl={n:,} matches parquet")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print(f"Verifying contents of {OUT.resolve()}")
    print("=" * 72)

    parquet_counts: Dict[str, int] = {}
    parquet_dims: Dict[str, int] = {}
    parquet_ids: Dict[str, np.ndarray] = {}

    print("\n--- Media modality parquet files ---")
    for modality, (n_exp, d_exp) in EXPECTED_MODALITIES.items():
        ok, n, ids = check_parquet_embeddings(
            OUT / f"{modality}_embeddings.parquet",
            expected_rows=n_exp,
            expected_dim=d_exp,
            require_kg_uri_nonempty=(modality != "text"),  # text rows can have empty source_url
        )
        if ok:
            parquet_counts[modality] = n
            parquet_dims[modality] = d_exp
            parquet_ids[modality] = ids

    print("\n--- KG full + heldout URIRef parquet files (HDF5-mirrored) ---")
    kg_uri_files = {
        "kg_embeddings": ("kg", KG_FULL_EXPECTED),
        "kg_heldout_all_labels_embeddings": ("kg_heldout_all_labels", None),
        "kg_heldout_decade_embeddings": ("kg_heldout_decade", None),
        "kg_heldout_genre_embeddings": ("kg_heldout_genre", None),
        "kg_heldout_language_embeddings": ("kg_heldout_language", None),
        "kg_heldout_rating_embeddings": ("kg_heldout_rating", None),
    }
    kg_parquet_uri_counts: Dict[str, int] = {}
    for stem, (group_name, n_exp) in kg_uri_files.items():
        ok, n, ids = check_parquet_embeddings(
            OUT / f"{stem}.parquet",
            expected_rows=n_exp,
            expected_dim=KG_EXPECTED_DIM,
            require_kg_uri_nonempty=True,
        )
        if ok:
            kg_parquet_uri_counts[stem] = n
            parquet_counts[group_name] = n
            parquet_dims[group_name] = KG_EXPECTED_DIM
            parquet_ids[group_name] = ids

    print("\n--- KG exhaustive PyKEEN entity parquet files (parquet-only) ---")
    kg_pykeen_files = {
        "kg_pykeen_entities": KG_PYKEEN_FULL_EXPECTED,
        "kg_heldout_all_labels_pykeen_entities": None,
        "kg_heldout_decade_pykeen_entities": None,
        "kg_heldout_genre_pykeen_entities": None,
        "kg_heldout_language_pykeen_entities": None,
        "kg_heldout_rating_pykeen_entities": None,
    }
    pykeen_counts: Dict[str, int] = {}
    for stem, n_exp in kg_pykeen_files.items():
        ok, n, _ = check_parquet_embeddings(
            OUT / f"{stem}.parquet",
            expected_rows=n_exp,
            expected_dim=KG_EXPECTED_DIM,
            require_kg_uri_nonempty=False,
            extra_columns=("node_kind", "pykeen_label"),
        )
        if ok:
            pykeen_counts[stem] = n

    print("\n--- HDF5 master file ---")
    check_hdf5(OUT / "embeddings.h5", parquet_ids, parquet_dims)

    check_progress(parquet_counts)
    check_manifests(kg_parquet_uri_counts, pykeen_counts)
    check_metadata_ttl(parquet_counts)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
