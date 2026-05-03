# Knowledge Graph Embeddings

This section describes the procedure used to learn dense vector representations
for the entities in the IMDB4M knowledge graph. The embeddings are released as
a fourth modality alongside the image, video, and audio representations and
are used both for entity retrieval and as input to multimodal fusion
experiments.

## Model

We train RotatE embeddings on the pruned IMDB4M knowledge graph, which
comprises approximately 1.8M RDF triples. RotatE represents each relation as
a rotation in a complex vector space, so that for a triple
\((h, r, t)\) the model encourages \(h \circ r \approx t\), where \(\circ\)
denotes the Hadamard (element-wise) product over complex-valued embeddings.

The embedding dimensionality is set to \(d = 256\) complex components per
entity. For storage and downstream cosine-based use, real and imaginary parts
are concatenated into a single real-valued vector of dimension \(2d = 512\).
All exported entity vectors are L2-normalized.

## Training Variants

To support both retrieval and label-clean classification evaluation, we train
six variants of the model. The full variant retains every triple in the
pruned KG. Each held-out variant additionally removes one or more predicates
from the training graph so that the embeddings cannot directly memorize the
edge that defines the corresponding evaluation label.

| Variant | Predicates removed | Purpose |
|---|---|---|
| `full` | none | KG retrieval, projections, KG-inclusive multimodal fusion |
| `genre` | `schema:genre` | label-clean genre classification |
| `rating` | `schema:contentRating` | label-clean rating classification |
| `decade` | `schema:datePublished` | label-clean decade classification |
| `language` | `schema:inLanguage` | label-clean language classification |
| `all-labels` | all four predicates above | strict robustness setting |

The `decade` variant removes `schema:datePublished` because decade labels are
derived from the publication year; the KG contains no explicit decade
predicate.

## Rationale for Held-Out Variants

The classification labels used in evaluation are derived from KG predicates:
genre from `schema:genre`, rating from `schema:contentRating`, decade from
`schema:datePublished`, and language from `schema:inLanguage`. A KG embedding
model trained with these predicates retained may encode the label edge
itself, which would inflate nearest-centroid classification metrics that are
intended to measure semantic structure rather than direct edge recall. We
therefore use the `full` model for retrieval, projection, and KG-inclusive
fusion, but report classification metrics using the corresponding held-out
variant for each label. The `all-labels` variant provides a stricter setting
in which all evaluation predicates are removed simultaneously.

## RDF Preparation

The Turtle KG is parsed with `rdflib` and converted into the labeled-triple
format expected by the embedding library. RDF nodes are mapped as follows:

- URI subjects and objects are kept as their full URI string.
- Literal objects are converted to deterministic synthetic node identifiers
  of the form `literal:<datatype>:<language>:<sha1-of-n3-literal>`. This
  preserves the structural contribution of literal-valued facts (such as
  ratings, dates, names, and languages) during training while keeping the
  vocabulary stable across runs.
- Blank nodes are mapped to stable string labels prefixed with `bnode:`.

For held-out variants, the relevant predicates are filtered from the triple
set before this conversion, so neither the label edges nor their literal
targets contribute to training. After conversion the triple set is split
into training, validation, and test subsets.

## Training Procedure

Each variant is trained for a maximum of 300 epochs with a batch size of
4096, an embedding dimension of \(d = 256\), and a fixed random seed. We use
loss-based early stopping: training halts when the per-epoch training loss
has not improved by at least a fixed relative threshold over a patience
window of 20 epochs, and the best-loss model weights are restored before
embeddings are exported. The same maximum epoch budget and convergence
criterion are applied to every variant so that runs are directly comparable.

## Entity Identifier Derivation

Each released embedding row is keyed by a stable `entity_id` derived from URI
structure where possible, so that downstream tools can join KG embeddings to
existing media records without ambiguity:

| URI kind | Entity ID rule |
|---|---|
| IMDb title URI | extract the `tt...` identifier |
| IMDb name URI | extract the `nm...` identifier |
| IMDb media URI | extract `rm...` or `vi...` from the URI path |
| Other URI | `kg_<sha1(uri)[:16]>` |

When two distinct URI resources would derive the same identifier, the first
deterministic occurrence keeps the base identifier and subsequent collisions
receive a short hash suffix. Distinct URI resources are never merged or
averaged: each retains its own row.

## Released Tables

For each variant, two embedding tables are released:

- A URIRef-only table containing one row per trained URI entity. This is the
  primary table consumed by retrieval, visualization, and fusion pipelines.
  Movie-level use cases filter rows whose `entity_id` begins with `tt`.
- An exhaustive table containing every trained entity in the model
  vocabulary, including URI nodes, minted literal nodes, and blank-node
  labels. This table is provided for reproducibility and inspection. It adds
  two metadata columns: `node_kind` (one of `uri`, `literal`, `bnode`) and
  the original entity label used during training.

Both tables share the column contract used by the image, video, and audio
embedding releases: `entity_id`, `kg_uri`, `source_url`, `filename`,
`model_id`, and a fixed-size float32 `embedding` vector. Each variant is
also distributed in HDF5 form, with one group per variant and per table type
sharing a common schema across modalities. A per-run manifest records the
variant identifier, the requested complex embedding dimension, the exported
real-valued dimension, and the training configuration used to produce the
files.

## Integration With Multimodal Evaluation

The KG embeddings are treated as a fourth modality alongside image, video,
and audio in all downstream analyses. For entity retrieval, projection, and
qualitative inspection, the `full` model is used. For each label-specific
classification metric, the corresponding held-out KG model is used, so that
no evaluation predicate is present in the training graph used to produce the
KG features being scored.

Early multimodal fusion intersects the four modalities to a common entity
set, applies PCA to each modality, L2-normalizes the per-modality vectors,
concatenates them, and L2-normalizes the resulting fused vector. Late fusion
combines per-modality cosine similarity matrices using either a uniform
1:1:1:1 weighting across image, video, audio, and KG, or a poster-weighted
2:1:1:1 weighting that emphasizes the visual modality. As with classification
metrics, the KG component of any label-specific fusion result is taken from
the held-out model for that label, while fusion used for retrieval and
visualization uses the `full` model.
