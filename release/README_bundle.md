# IMDB4M — Knowledge Graph + Pre-computed Multi-Modal Embeddings (v1)

IMDB4M is a multi-modal knowledge graph that links IMDB movies and
people to their still images, trailer/clip videos, and soundtrack audio
tracks, together with pre-computed CLIP-family embeddings for every
media file, BGE text embeddings for KG literals, and RotatE knowledge-
graph embeddings (full model + five held-out variants for evaluation).

This release ships in **two complementary parts**:

1. **GitHub bundle** (this archive) — code, the cleaned/disk-aligned
   knowledge graph, the alignment report, and an empty
   ``embeddings_output/`` directory.
2. **Zenodo deposit**
   [10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840) —
   the pre-computed embedding tables, the master HDF5 file, the RDF
   pointers from KG subjects to vector rows, and the per-variant
   training manifests.

After unpacking the GitHub bundle, drop the Zenodo files into
``embeddings_output/`` and the rest of the project picks them up
automatically.

---

## 1. What's in this bundle

```
imdb4m-release-v1/
├── kg/
│   ├── imdb_kg_cleaned.ttl           Main KG (Turtle).  ~1.80 M triples.
│   │                                 Already pruned: every media triple
│   │                                 corresponds to a file on disk and a
│   │                                 row in the embeddings on Zenodo.
│   └── imdb_kg_failed_media.ttl      Side graph: every triple removed
│                                     during clean-up (provenance trail).
├── embeddings_output/                Empty directory.  Drop the files
│   └── README.md                     downloaded from Zenodo here.
├── alignment_report.json             Audit showing 100 % image/video
│                                     alignment and 3 audio entities with
│                                     no downloadable soundtrack.
├── MANIFEST.sha256                   SHA-256 of every file above.
├── README.md                         This file.
└── LICENSE.md                        Usage terms.
```

---

## 2. What's on Zenodo (DOI 10.5281/zenodo.20057840)

```
embeddings_output/
├── image_embeddings.parquet              33,247 × 768   (CLIP ViT-L/14)
├── video_embeddings.parquet               4,350 × 512   (X-CLIP base-32)
├── audio_embeddings.parquet               4,034 × 512   (LAION CLAP)
├── text_embeddings.parquet                4,216 × 1,024 (BGE-large-EN, KG literals)
├── kg_embeddings.parquet                139,465 × 512   (RotatE, full graph)
├── kg_heldout_genre_embeddings.parquet  139,465 × 512   (RotatE, genre triples held out)
├── kg_heldout_rating_embeddings.parquet 139,465 × 512   (RotatE, contentRating held out)
├── kg_heldout_decade_embeddings.parquet 139,465 × 512   (RotatE, datePublished held out)
├── kg_heldout_language_embeddings.parquet 139,465 × 512 (RotatE, inLanguage held out)
├── kg_heldout_all_labels_embeddings.parquet 139,465 × 512 (RotatE, all four held out)
├── kg_pykeen_entities.parquet           ~656k × 512    Full PyKEEN node table for the
│                                                       full RotatE model (URIRef +
│                                                       literals + relations + bnodes).
├── kg_heldout_*_pykeen_entities.parquet One per held-out variant; same shape.
├── kg_rotate_*_manifest.json            Per-variant training provenance (epochs,
│                                        loss curve, dependency versions, etc.).
├── kg_rotate_runs.json                  Combined log across all variants.
├── embeddings.h5                        Master HDF5 mirror of every parquet,
│                                        gzip-4 compressed (~11 GB).
├── embedding_metadata.ttl               RDF pointers from KG subjects into the
│                                        media parquet / HDF5 rows.
└── embed_progress.json                  Checkpoint file used by the embedding pipeline.
```

---

## 3. Installing the embeddings

### 3.1 With the project source tree

```bash
git clone https://github.com/onradio/imdb4m.git
cd imdb4m

# Download every file from the Zenodo deposit
pip install zenodo_get
zenodo_get 10.5281/zenodo.20057840 -o embeddings_output/
```

After the download completes, the project root must look like this:

```
imdb4m/
├── data/kg/imdb_kg_cleaned.ttl     # already in this bundle
├── embeddings/                      # generator code (read-only)
└── embeddings_output/               # populated from Zenodo
    ├── image_embeddings.parquet
    ├── video_embeddings.parquet
    ├── audio_embeddings.parquet
    ├── text_embeddings.parquet
    ├── kg_embeddings.parquet
    ├── kg_heldout_*_embeddings.parquet
    ├── kg_pykeen_entities.parquet
    ├── kg_heldout_*_pykeen_entities.parquet
    ├── kg_rotate_*_manifest.json
    ├── kg_rotate_runs.json
    ├── embedding_metadata.ttl
    ├── embeddings.h5
    └── embed_progress.json
```

### 3.2 With this release archive only

If you are using *this* archive (without cloning the repo), the
``embeddings_output/`` directory is shipped empty. Place the Zenodo
files directly inside it.

---

## 4. The knowledge graph

* Vocabulary: **schema.org** (``http://schema.org/``), extended with
  ``imdb4m:`` (``http://imdb4m.org/embedding/``) for embedding
  pointers.
* Core node types: ``schema:Movie``, ``schema:Person``, ``schema:ImageObject``,
  ``schema:VideoObject``, ``schema:MusicRecording``, ``schema:MusicComposition``.
* Core edges: ``schema:image``, ``schema:thumbnail``, ``schema:trailer``,
  ``schema:video``, ``schema:audio``, ``schema:byArtist``,
  ``schema:recordingOf``, ``schema:composer``, ``schema:actor``,
  ``schema:director``, ``schema:productionCompany``, etc.

`imdb_kg_cleaned.ttl` is the output of the `kg_cleanup` pipeline (see
`kg_cleanup/README.md` in the source distribution): every media triple
it asserts corresponds to a file that actually exists on disk (and
therefore has an embedding in the Zenodo deposit). Every triple that
was removed during clean-up is preserved verbatim in
`kg/imdb_kg_failed_media.ttl` so the provenance of the dataset is
fully auditable.

---

## 5. Embedding files (on Zenodo)

Parquet files (one per modality) and one master HDF5 file carry
identical content in two formats. Use whichever suits your toolchain.

### 5.1 Parquet schema (same for every modality)

| column       | type                     | notes |
|--------------|--------------------------|-------|
| `entity_id`  | string                   | e.g. `nm0000138`, `tt0120338` |
| `kg_uri`     | string                   | Full schema.org URI of the entity |
| `source_url` | string                   | CDN / IMDB / YouTube URL of the media; empty for KG text literals |
| `filename`   | string                   | Basename on disk, or stable text row id containing the predicate |
| `model_id`   | string                   | HuggingFace model id |
| `embedding`  | FixedSizeList[float32]   | 768 (image), 512 (video/audio), 1024 (text) |

Parquet-level compression: **zstd**. Row order inside each file is
stable; the HDF5 group for the same modality uses the same row
indices, so `parquet_row == hdf5_index`.

### 5.2 HDF5 layout

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
/video/                          (4350, 512)
/audio/                          (4034, 512)
/text/                           (4216, 1024)
/kg/                          (139465, 512)   RotatE, full graph
/kg_heldout_genre/            (139465, 512)
/kg_heldout_rating/           (139465, 512)
/kg_heldout_decade/           (139465, 512)
/kg_heldout_language/         (139465, 512)
/kg_heldout_all_labels/       (139465, 512)
/kg_pykeen_entities/         (~656003, 512)   Full PyKEEN node table
/kg_heldout_*_pykeen_entities/ (~656k, 512)   One per held-out variant
attrs (top level): provenance_pruned_kg, provenance_failed_kg,
                   regenerated_ttl, enhanced_at, toolchain_version
```

### 5.3 Linking vectors back to KG subjects

`embedding_metadata.ttl` (on Zenodo) emits one
`imdb4m:hasEmbedding` record per parquet row, attached to the source
media's natural KG subject (CDN URL for images, IMDB embed URL for
videos, YouTube URL for audio, movie URI for KG text literals). Each
record names the parquet file, parquet row, HDF5 group, and HDF5 row
index — so you can go from SPARQL results straight to the right slice
of the vector table.

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

## 6. Models

| Modality                        | Model                                       | Output dim |
|---------------------------------|---------------------------------------------|:----------:|
| image                           | `openai/clip-vit-large-patch14`             | 768        |
| video                           | `microsoft/xclip-base-patch32`              | 512        |
| audio                           | `laion/larger_clap_music_and_speech`        | 512        |
| text                            | `BAAI/bge-large-en-v1.5`                    | 1024       |
| kg (full)                       | `pykeen/rotate/imdb4m-full-d256`            | 512 *      |
| kg_heldout_genre                | `pykeen/rotate/imdb4m-genre-d256`           | 512 *      |
| kg_heldout_rating               | `pykeen/rotate/imdb4m-rating-d256`          | 512 *      |
| kg_heldout_decade               | `pykeen/rotate/imdb4m-decade-d256`          | 512 *      |
| kg_heldout_language             | `pykeen/rotate/imdb4m-language-d256`        | 512 *      |
| kg_heldout_all_labels           | `pykeen/rotate/imdb4m-all-labels-d256`      | 512 *      |

\* RotatE is trained at complex dimension 256; entries are exported as
real-valued 512-d concatenations of the real / imaginary parts.

All vectors are **L2-normalised** (`‖v‖₂ = 1`). Cosine similarity is
equivalent to the dot product. FP16 inference was used at media
embedding time; stored vectors are FP32. Model revision is recorded
per modality in the HDF5 group attrs and in the per-variant
`kg_rotate_*_manifest.json` files distributed on Zenodo.

The held-out RotatE variants train on a copy of the KG with the named
predicate(s) removed — they exist so downstream evaluations can fairly
predict the held-out attribute from the multi-modal vectors without
the KG embedding having seen the answer. Each variant ships with its
own `kg_rotate_*_manifest.json` file recording the training
hyper-parameters and full loss curve.

---

## 7. Alignment guarantee (as of this release)

`alignment_report.json` was generated by diffing the pruned KG against
every parquet row.

| modality | parquet rows | KG references | orphans | missing |
|----------|-------------:|--------------:|--------:|--------:|
| image    |       33,247 |        33,247 |       0 |       0 |
| video    |        4,350 |         4,350 |       0 |       0 |
| audio    |        4,034 |           357 entities |  0 |  3 entities* |

\* 3 movies assert ≥1 soundtrack track in the KG but the track lacks a
resolvable YouTube URL and was therefore never downloaded. Those
entities are listed in the alignment report.

---

## 8. Quick start

### Python (Parquet)

```python
import pyarrow.parquet as pq
import numpy as np

t = pq.read_table("embeddings_output/image_embeddings.parquet")
df = t.to_pandas()
X = np.stack(df["embedding"].to_numpy())          # (33247, 768)
ids = df["entity_id"].to_numpy()
```

### Python (HDF5)

```python
import h5py
with h5py.File("embeddings_output/embeddings.h5", "r") as hf:
    X   = hf["/image/embeddings"][:]              # (33247, 768) float32
    ids = hf["/image/entity_id"][:]               # (33247,) bytes
    assert hf["/image"].attrs["normalized"]
```

### SPARQL (KG + embedding metadata loaded together)

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

## 9. Citation

If you use IMDB4M in a publication, please cite the accompanying paper
(title / venue TBD) and the Zenodo deposit.

```bibtex
@dataset{imdb4m_embeddings_2026,
  title  = {{IMDB4M} Multi-Modal and KG Embeddings (v1)},
  author = {Reklos, Ioannis and de Berardinis, Jacopo and Simperl, Elena and Mero{\~n}o-Pe{\~n}uela, Albert},
  year   = {2026},
  doi    = {10.5281/zenodo.20057840}
}
```

---

## 10. Licensing

See `LICENSE.md`. The Knowledge Graph structure and the derived
embeddings are released under a research-friendly licence; the
underlying images, videos, and audio belong to their original
rights-holders and are *not* redistributed in this bundle or on Zenodo.
