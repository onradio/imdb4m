# IMDB4M — Knowledge Graph + Media Embeddings (v1)

IMDB4M is a multi-modal knowledge graph that links IMDB movies and
people to their still images, trailer/clip videos, and soundtrack audio
tracks, together with pre-computed CLIP-family embeddings for every
media file.

This release contains the **cleaned, disk-aligned** version of the KG
and the vectors that match it one-for-one.

---

## 1. What's in this bundle

```
imdb4m-release-v1/
├── kg/
│   ├── imdb_kg_cleaned.pruned.ttl    Main KG (Turtle).  ~1.80 M triples.
│   └── imdb_kg_failed_media.ttl      Side graph: every triple removed
│                                     during clean-up (provenance trail).
├── embeddings/
│   ├── image_embeddings.parquet      33,247 × 768  (CLIP ViT-L/14)
│   ├── video_embeddings.parquet      4,350 × 512   (X-CLIP base-32)
│   ├── audio_embeddings.parquet      4,034 × 512   (LAION CLAP)
│   ├── text_embeddings.parquet       KG literal text × 1024 (BGE large EN)
│   ├── embeddings.h5                 Same vectors + metadata, gzipped HDF5
│   ├── embedding_metadata.ttl        RDF pointers from KG subjects into
│   │                                 the parquet / HDF5 rows
│   └── embeddings_card.json          Machine-readable summary of the
│                                     vectors, models, and revisions
├── alignment_report.json             Audit showing 100 % image/video
│                                     alignment and 3 audio entities with
│                                     no downloadable soundtrack
├── MANIFEST.sha256                   SHA-256 of every file above
├── README.md                         This file
└── LICENSE.md                        Usage terms
```

---

## 2. The knowledge graph

* Vocabulary: **schema.org** (``http://schema.org/``), extended with
  ``imdb4m:`` (``http://imdb4m.org/embedding/``) for embedding
  pointers.
* Core node types: ``schema:Movie``, ``schema:Person``, ``schema:ImageObject``,
  ``schema:VideoObject``, ``schema:MusicRecording``, ``schema:MusicComposition``.
* Core edges: ``schema:image``, ``schema:thumbnail``, ``schema:trailer``,
  ``schema:video``, ``schema:audio``, ``schema:byArtist``,
  ``schema:recordingOf``, ``schema:composer``, ``schema:actor``,
  ``schema:director``, ``schema:productionCompany``, etc.

The `.pruned.ttl` file is the output of the `kg_cleanup` pipeline
(see `kg_cleanup/README.md` in the source distribution): every
media triple it asserts corresponds to a file that actually exists
on disk (and therefore has an embedding in this bundle).  Every
triple that was removed during clean-up is preserved verbatim in
`kg/imdb_kg_failed_media.ttl` so the provenance of the dataset is
fully auditable.

---

## 3. Embedding files

Parquet files (one per modality) and one master HDF5 file carry
identical content in two formats.  Use whichever suits your toolchain.

### 3.1 Parquet schema (same for every modality)

| column       | type                     | notes |
|--------------|--------------------------|-------|
| `entity_id`  | string                   | e.g. `nm0000138`, `tt0120338` |
| `kg_uri`     | string                   | Full schema.org URI of the entity |
| `source_url` | string                   | CDN / IMDB / YouTube URL of the media; empty for KG text literals |
| `filename`   | string                   | Basename on disk, or stable text row id containing the predicate |
| `model_id`   | string                   | HuggingFace model id |
| `embedding`  | FixedSizeList[float32]   | 768 (image), 512 (video/audio), 1024 (text) |

Parquet-level compression: **zstd**.  Row order inside each file is
stable; the HDF5 group for the same modality uses the same row
indices, so `parquet_row == hdf5_index`.

### 3.2 HDF5 layout

```
/image/
    embeddings   (33247, 768) float32, gzip-4
    entity_id    (33247,)     utf-8
    kg_uri       (33247,)     utf-8
    source_url   (33247,)     utf-8
    filename     (33247,)     utf-8
  attrs: model_id, model_revision, embed_dim, count,
         normalized=true, similarity_metric="cosine",
         vector_dtype="float32", created_at
/video/  ...    (4350, 512)
/audio/  ...    (4034, 512)
/text/   ...    (N, 1024)
attrs (top level): provenance_pruned_kg, provenance_failed_kg,
                   regenerated_ttl, enhanced_at, toolchain_version
```

### 3.3 Linking vectors back to KG subjects

`embedding_metadata.ttl` emits one
`imdb4m:hasEmbedding` record per parquet row, attached to the source
media's natural KG subject (CDN URL for images, IMDB embed URL for
videos, YouTube URL for audio, movie URI for KG text literals).  Each record names the parquet file,
parquet row, HDF5 group, and HDF5 row index — so you can go from
SPARQL results straight to the right slice of the vector table.

Example triple block (real data):

```turtle
<https://m.media-amazon.com/images/M/MV5BMTY...jpg>
    imdb4m:hasEmbedding [
        imdb4m:modality         "image" ;
        imdb4m:model            "openai/clip-vit-large-patch14" ;
        imdb4m:modelRevision    "main" ;
        imdb4m:embeddingDim     768 ;
        imdb4m:embeddingsNormalized true ;
        imdb4m:entityId         "nm0000138" ;
        imdb4m:parquetFile      "image_embeddings.parquet" ;
        imdb4m:parquetRow       42 ;
        imdb4m:hdf5File         "embeddings.h5" ;
        imdb4m:hdf5Group        "/image" ;
        imdb4m:hdf5Index        42 ;
        imdb4m:sourceFile       "MV5BMTY...jpg"
    ] .
```

---

## 4. Models + reproducibility

| Modality | Model                                 | Output dim |
|----------|---------------------------------------|:----------:|
| image    | `openai/clip-vit-large-patch14`       | 768        |
| video    | `microsoft/xclip-base-patch32`        | 512        |
| audio    | `laion/larger_clap_music_and_speech`  | 512        |

All vectors are **L2-normalised** (`‖v‖₂ = 1`).  Cosine similarity is
equivalent to the dot product.  FP16 inference was used at embedding
time; stored vectors are FP32.  Model revision is recorded per
modality in the HDF5 group attrs and in `embeddings_card.json`.

---

## 5. Alignment guarantee (as of this release)

`alignment_report.json` was generated by diffing the pruned KG against
every parquet row.

| modality | parquet rows | KG references | orphans | missing |
|----------|-------------:|--------------:|--------:|--------:|
| image    |       33,247 |        33,247 |       0 |       0 |
| video    |        4,350 |         4,350 |       0 |       0 |
| audio    |        4,034 |           357 entities |  0 |  3 entities* |

\* 3 movies assert ≥1 soundtrack track in the KG but the track lacks a
resolvable YouTube URL and was therefore never downloaded.  Those
entities are listed in the alignment report.

---

## 6. Quick start

### Python (Parquet)

```python
import pyarrow.parquet as pq
import numpy as np

t = pq.read_table("embeddings/image_embeddings.parquet")
df = t.to_pandas()
# embedding column is a list of floats; stack into a matrix
X = np.stack(df["embedding"].to_numpy())          # (33247, 768)
ids = df["entity_id"].to_numpy()
```

### Python (HDF5)

```python
import h5py
with h5py.File("embeddings/embeddings.h5", "r") as hf:
    X   = hf["/image/embeddings"][:]              # (33247, 768) float32
    ids = hf["/image/entity_id"][:]               # (33247,) bytes
    assert hf["/image"].attrs["normalized"]
```

### SPARQL

```sparql
PREFIX schema: <http://schema.org/>
PREFIX imdb4m: <http://imdb4m.org/embedding/>

SELECT ?movie ?poster ?row WHERE {
  ?movie a schema:Movie ;
         schema:image ?poster .
  ?poster imdb4m:hasEmbedding [
    imdb4m:modality "image" ;
    imdb4m:parquetRow ?row
  ] .
}
```

---

## 7. Citation

If you use IMDB4M in a publication, please cite the accompanying
paper (title / venue TBD).  A `CITATION.cff` file will be added once
the paper is public.

---

## 8. Licensing

See `LICENSE.md`.  The Knowledge Graph structure and the derived
embeddings are released under a research-friendly licence; the
underlying images, videos, and audio belong to their original
rights-holders and are *not* redistributed in this bundle.
