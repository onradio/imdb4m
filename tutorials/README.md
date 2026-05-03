# IMDB4M Tutorials

This directory contains the executable companion to the IMDB4M dataset
publication. The two notebooks form a self-contained guide to using the
released knowledge graph and the five embedding modalities that ship with
it. They are intended for readers of the publication who want to inspect
the resource in practice, reproduce the headline statistics from the
released artifacts, and exercise the multimodal embedding spaces on
concrete downstream tasks.

The notebooks are written so that every cell can be run end-to-end on a
single machine without any access to private services or unreleased data.
All file paths default to the on-disk release bundle; if an embedding
table is not yet present in the bundle, the notebooks transparently fall
back to the corresponding source-checkout artifact so that the workflow
remains complete.

## Notebooks

### `01_multimodal_retrieval.ipynb`

This notebook walks through the full multimodal retrieval workflow that
IMDB4M is designed to support. It loads the cleaned RDF graph, parses
movie display labels, and ingests the five released embedding tables:

- image vectors from CLIP ViT-L/14 (768 dimensions);
- video vectors from X-CLIP base patch-32 (512 dimensions);
- audio vectors from LAION CLAP (512 dimensions);
- text vectors from BGE-large-en-v1.5 (1024 dimensions), aggregated over
  the textual literals attached to each movie (abstracts, descriptions,
  reviews, and image captions);
- knowledge-graph vectors from RotatE trained on the pruned KG and
  exported as 512-dimensional real-valued vectors per entity.

For media and text rows the notebook applies the release-time pooling
recipe (L2-normalize each row, mean-pool by IMDb identifier,
L2-normalize the pooled vector). For the knowledge-graph modality each
movie is a single entity row and only the final L2 step is required.
The notebook then demonstrates nearest-neighbour retrieval for each
modality individually and a late-fusion combination over all five
modalities, with weights that emphasize visual evidence while retaining
a meaningful contribution from text and from the relational structure
of the graph.

### `02_kg_visualization_and_metrics.ipynb`

This notebook complements the retrieval workflow with a closer look at
the structure of the knowledge graph and at the quality of the released
embedding spaces. It performs four reproducible analyses:

1. **Bounded subgraph visualization.** Rather than attempting to render
   the full graph of approximately 1.8 million triples, the notebook
   extracts a movie-centred neighbourhood, restricts it to a configurable
   set of predicates, and renders it as an interactive `pyvis` graph
   (with a `matplotlib` fallback when `pyvis` is unavailable).
2. **Structural metrics.** Triple count, node and predicate counts,
   distribution over node kinds (URI, blank node, literal), degree
   statistics on the directed graph, connected-component statistics on
   the URI-only entity graph, density, average clustering on a
   deterministic node sample, and top-ranked predicates and RDF types
   are computed directly from the released Turtle file.
3. **Per-movie modality coverage.** Image, video, and audio coverage are
   read from the KG; text coverage combines KG text literals with the
   released text embeddings; KG coverage is read from the RotatE entity
   table. The notebook reports per-modality coverage and an
   "all-modalities" intersection over a metadata-rich seed population.
4. **Embedding-quality metrics.** For each modality and each
   KG-derived label (`decade`, `rating`, `genre`, `language`) the
   notebook reports leave-one-out nearest-class-centroid accuracy under
   cosine similarity, the cosine silhouette, and the adjusted Rand
   index between K-Means clusters and the ground-truth labels. For the
   knowledge-graph modality the held-out RotatE variant of the label is
   used so that the predicate that defines the evaluation label is
   never present in the training graph used to produce the KG features
   being scored.

## Knowledge-Graph Embeddings (RotatE)

The knowledge-graph modality is produced by training RotatE on the
pruned KG with PyKEEN. RotatE represents each relation as a rotation
in a complex vector space, so for a triple \((h, r, t)\) the model
encourages \(h \circ r \approx t\), where \(\circ\) denotes the
Hadamard product over complex-valued embeddings. The complex
embedding dimension is \(d = 256\); for storage and downstream
cosine-based use, real and imaginary parts are concatenated into a
single real-valued vector of dimension \(2d = 512\) and the vectors
are L2-normalized.

Six variants are released. The `full` variant retains every triple in
the pruned KG and is used for retrieval, projection, and KG-inclusive
multimodal fusion. Four held-out variants additionally remove a single
label-defining predicate from the training graph (`schema:genre`,
`schema:contentRating`, `schema:datePublished`, and `schema:inLanguage`,
respectively). A stricter `all-labels` variant simultaneously removes
every label predicate. The held-out variants are intended exclusively
for label-clean classification metrics, so that the KG embeddings used
to predict a given label have not been exposed to the corresponding
predicate during training. The retrieval tutorial uses the `full`
variant; the metrics tutorial automatically selects the appropriate
held-out variant for each evaluated label.

## Text Embeddings

The text modality is computed by the BAAI/`bge-large-en-v1.5` sentence
encoder. Text payloads are extracted from KG literals attached to four
schema.org predicates: `schema:abstract`, `schema:description`,
`schema:reviewBody`, and `schema:caption`. Each text item is resolved
to its owning movie (directly when the literal is attached to the
movie node, or indirectly through `schema:review`,
`schema:itemReviewed`, `schema:image`, `schema:trailer`,
`schema:video`, `schema:productionBudget`, or
`schema:aggregateRating` for non-movie subjects). Long texts are
chunked with overlap and the chunk vectors are mean-pooled. All
vectors are L2-normalized at storage time.

## Data Layout

The notebooks default to the local release bundle:

```text
release_output/imdb4m-release-v1/
├── kg/
│   └── imdb_kg_cleaned.pruned.ttl
├── embeddings/
│   ├── image_embeddings.parquet
│   ├── video_embeddings.parquet
│   ├── audio_embeddings.parquet
│   ├── text_embeddings.parquet
│   ├── kg_embeddings.parquet
│   ├── kg_heldout_genre_embeddings.parquet
│   ├── kg_heldout_rating_embeddings.parquet
│   ├── kg_heldout_decade_embeddings.parquet
│   ├── kg_heldout_language_embeddings.parquet
│   ├── kg_heldout_all_labels_embeddings.parquet
│   ├── embeddings.h5
│   ├── embedding_metadata.ttl
│   └── embeddings_card.json
└── alignment_report.json
```

If the release bundle is unpacked elsewhere, set `DATA_ROOT` in the
first setup cell of each notebook to the path of the
`imdb4m-release-v1` directory. When an artifact (for example a text
or RotatE embedding table) is not yet present in the release bundle,
`resolve_paths` automatically falls back to the source-checkout
`embeddings_output/` directory so that the notebooks remain runnable.

All Parquet files share the same schema:

| column       | type                       | description                                          |
| ------------ | -------------------------- | ---------------------------------------------------- |
| `entity_id`  | string                     | IMDb identifier (`tt...`, `nm...`) or KG-derived id  |
| `kg_uri`     | string                     | Full KG URI of the entity                            |
| `source_url` | string                     | Source URL of the underlying media (when applicable) |
| `filename`   | string                     | Basename on disk or stable text identifier           |
| `model_id`   | string                     | Identifier of the model that produced the vector     |
| `embedding`  | `FixedSizeList[float32]`   | L2-normalized vector of fixed dimension              |

## Setup

Install the main project requirements first, then the notebook extras:

```bash
pip install -r requirements.txt
pip install -r tutorials/requirements.txt
jupyter lab tutorials/
```

`pyvis`, `plotly`, `ipywidgets`, and `umap-learn` are optional in the
sense that the notebooks include fallbacks, but installing them gives
the best interactive experience.

## Runtime Notes

- Loading the release KG parses approximately 1.8 million RDF triples
  and can take a few minutes depending on hardware.
- The full KG is never visualized directly; the visualization notebook
  always extracts a bounded one- or two-hop subgraph around a selected
  movie.
- Raw images, videos, and audio files are not redistributed by IMDB4M.
  The notebooks operate on external URIs, KG metadata, and the released
  embeddings. If local thumbnails are present under
  `output/<tt_id>/images/`, the retrieval notebook can display them;
  otherwise it falls back to neighbour tables.
- The structural-metrics cell can compute exact average clustering on a
  deterministic node sample (default 5,000 nodes) so that the notebook
  remains responsive on the full release graph.

## Reproducibility Of The Reported Numbers

Every number printed by the notebooks is computed at runtime from the
exact files loaded by `resolve_paths`. Each cell that depends on the
RDF build is therefore release-derived: rerunning the notebooks on a
different build will produce values consistent with that build rather
than with any pre-computed table.
