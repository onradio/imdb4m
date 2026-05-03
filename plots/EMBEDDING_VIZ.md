# Embedding Quality and Multimodal Fusion Visualisations

This section describes the pipeline implemented in
`plots/embedding_projections.py`, which produces the figures, tables, and
metric files that document embedding quality for IMDB4M. The pipeline operates
on the released per-modality vectors (image, video, audio, knowledge-graph,
text) and reports both quantitative cluster/retrieval metrics and qualitative
two-dimensional projections.

## Outputs

All artifacts are written to `plots/out/`.

| Artifact | Contents |
|---|---|
| `fig_fusion_{decade,rating,genre}_{umap,tsne}.pdf/.png` | Six-panel projection figures (image, video, audio, KG, text average, fused), coloured by the corresponding KG-derived label. |
| `fig_retrieval_grid.pdf/.png` | Qualitative top-five nearest-neighbour grid for three random queries, with one row per modality and one row for the fused similarity. |
| `fig_consistency_{umap,tsne}.pdf/.png` | Per-image projection for the five movies with the largest number of stills, used to illustrate intra-entity coherence of the image encoder. |
| `tab_fusion_metrics.tex` | Cross-product of modalities and fusion strategies against KG-derived labels. |
| `metrics.json` | Same numbers as the LaTeX table in machine-readable form, plus per-fold details for supervised late fusion. |
| `projections.npz` | Two-dimensional UMAP and t-SNE coordinates used by the figures. |
| `retrieval_neighbors.json` | Top-five neighbours and cosine similarities for every query and modality. |

## Reproduction

```bash
python plots/embedding_projections.py \
    --kg data/kg/imdb_kg_cleaned.ttl \
    --embed-dir embeddings_output \
    --media-dir output \
    --out-dir plots/out \
    --pca-dim 256 --seed 0
```

The script is fully deterministic given the seed.

## Data Sources

- **Knowledge graph.** `data/kg/imdb_kg_cleaned.ttl` is parsed with a
  lightweight regex reader (`parse_movie_labels`) that extracts movie-level
  metadata (`schema:name`, `schema:genre`, `schema:datePublished`,
  `schema:contentRating`, `schema:inLanguage`). Top-level `schema:name`
  literals are matched only at the four-space indentation level so that nested
  `schema:MusicComposition` titles never leak into movie names. Records that
  share a `tt` identifier are merged so that the rich record dominates the
  stub variant.
- **Per-modality embeddings.** The pipeline consumes the parquet tables
  released alongside IMDB4M:
  - `image_embeddings.parquet` (CLIP ViT-L/14, \(d = 768\))
  - `video_embeddings.parquet` (X-CLIP base/32, \(d = 512\))
  - `audio_embeddings.parquet` (CLAP, \(d = 512\))
  - `text_embeddings.parquet` (BGE-large-EN v1.5, \(d = 1024\); covers
    `schema:abstract`, `schema:description`, `schema:reviewBody`, and
    `schema:caption`).
  - `kg_embeddings.parquet` (RotatE, \(2d = 512\) real-valued from \(d = 256\)
    complex; full model, used for retrieval and projection).
  - Four held-out RotatE tables
    (`kg_heldout_{genre,rating,decade,language}_embeddings.parquet`) used in
    the classification metrics, see *Held-Out KG Variants* below.
- **Thumbnails.** Original poster and still images under
  `output/<tt_id>/images/` are read for the retrieval grid only.

## Per-Entity Aggregation

Every embedding parquet stores one row per media file or per text literal.
The visualisations require one vector per movie, which is produced by the
following procedure:

1. L2-normalise each row vector.
2. Average all rows that share the same entity identifier.
3. L2-normalise the averaged vector.

This *L2 then mean then L2* convention preserves angular geometry, so cosine
similarity remains a dot product.

Text is aggregated in two stages. Rows are first pooled per predicate,
yielding one movie vector per predicate (`text_abstract`, `text_description`,
`text_reviewBody`, `text_caption`). The balanced average `text_avg` is then
formed by averaging the available per-predicate vectors with equal predicate
weight, followed by a final L2 normalisation. This prevents predicates with
high row counts (such as reviews and captions) from dominating the text
modality.

## Multimodal Pool

The fusion pool is the intersection of the five movie-level modality sets:
image, video, audio, full-KG, and `text_avg`. In the cleaned KG this
intersection contains 352 movies. All projections, retrieval queries, and
fusion metrics operate on this common pool so that single-modality and fused
results are directly comparable on identical entity sets. Per-predicate text
metrics use each predicate's own native coverage, so individual predicate
performance remains visible alongside the balanced average.

## Fusion Strategies

Two complementary families of fusion are reported, because they differ in
whether they alter the embedding *geometry* (early fusion) or only the
*similarity surface* used downstream (late fusion). A third strategy tunes
late-fusion weights by cross-validation as a supervised reference.

### Early Fusion (Concatenation)

For each modality:

1. Take the aggregated, L2-normalised movie vectors restricted to the
   intersection pool.
2. Apply PCA to a fixed dimensionality of \(\min(\texttt{pca\_dim}, N - 1)\),
   with `pca_dim = 256`.
3. L2-normalise the PCA output.

The reduced per-modality matrices are then concatenated horizontally into a
single fused vector and L2-normalised once more. The rationale for
per-modality PCA before concatenation is twofold. First, the encoders use
different native dimensionalities (768, 512, 512, 512, 1024); reducing each to
the same size gives every modality equal geometric weight at concatenation
time. Second, PCA acts as a denoising step that retains the directions of
maximum variance and discards the tail. Early fusion produces a single
coherent vector space that can be projected (UMAP, t-SNE) alongside the
single-modality panels.

### Late Fusion (Cosine-Similarity Combination)

Let \(S_m = X_m X_m^{\top}\) be the cosine-similarity matrix obtained from the
L2-normalised per-movie vectors of modality \(m\). Late fusion combines these
matrices linearly:

\[
S_{\text{fused}} = \sum_{m} w_m S_m \, , \quad \sum_m w_m = 1 .
\]

Two preset weight schemes are reported:

- **Uniform** (`fused_late`): \(w = (1, 1, 1, 1, 1) / 5\) over image, video,
  audio, KG, and `text_avg`.
- **Poster-weighted** (`fused_late_wp`): \(w \propto (2, 1, 1, 1, 1)\),
  reflecting the empirical observation that the poster modality carries the
  strongest single-modality signal in this corpus while the remaining
  modalities provide complementary lift.

Late fusion does not distort the native modality geometries, so retrieval and
metric scores under any single modality and under late fusion are computed
through the same kernel pipeline and remain directly comparable. No
two-dimensional projection is drawn for late fusion since there is no single
vector space to project.

### Supervised Late Fusion (Cross-Validated)

A third late-fusion variant (`fused_late_cv`) tunes the modality weights by
nested cross-validation. The outer five-fold split estimates the held-out
classification score; an inner three-fold split selects non-negative
simplex weights from a coarse grid using the same nearest-centroid
classifier described below. Modality weights are constrained to lie on the
simplex (non-negative, sum to one) with a step of \(0.25\). This setting
serves as a supervised reference for what fusion can achieve when modality
contributions are tuned to the label of interest. The supervised pool
intersects the multimodal pool with the row sets of all four text
predicates so that every modality slot is populated for every fold.

## Two-Dimensional Projections

For every scatter figure the input vectors are L2-normalised and reduced
through a two-step pipeline with the random seed fixed for reproducibility:

1. PCA to the lesser of fifty components or \(N - 1\) (denoising step).
2. Either:
   - **UMAP** with `n_neighbors = 15`, `min_dist = 0.10`, and the cosine
     metric. UMAP is used in the main figures.
   - **t-SNE** with perplexity \(\min(30, N/5)\), `init='pca'`, and the cosine
     metric. t-SNE is used in the supplementary figures.

Each fusion figure contains six panels in one row — image, video, audio, KG,
text average, and fused — sharing the same label colouring so that cluster
structure can be compared across modalities at a glance.

UMAP is preferred for the main figures because it preserves both local
neighbourhoods and global topology reasonably well, giving faithful
at-a-glance separability for ordinal labels such as decade and rating. t-SNE
is reported as a robustness check: it emphasises local structure more
aggressively at the cost of distorting between-cluster distances, and the
agreement between the two projections demonstrates that the qualitative
conclusions are not artefacts of the projector choice.

## Labels

Four label columns are derived from the KG for the multimodal pool.

| Label | Derivation | Classes in pool |
|---|---|---|
| Decade | \(\lfloor \text{year}/10 \rfloor \times 10\) from `schema:datePublished` | 5 |
| Rating | `schema:contentRating` restricted to {G, PG, PG-13, R} | 4 |
| Genre | Rarest of the movie's genres among the nine target genres | up to 9 |
| Language | First `schema:inLanguage` value, with rare languages collapsed to "Other" | up to 6 |

For genre the *rarest* film genre among the target set is selected rather
than the first-listed one, because the IMDb listing order is correlated with
genre popularity and would otherwise collapse most films to Drama. The target
genre set is {Drama, Action, Comedy, Crime, Thriller, Sci-Fi, Animation,
Horror, Romance}.

Colour palettes are drawn from the Paul-Tol muted, colour-blind safe family.
For ordinal labels the largest class is rendered first with reduced opacity
so that minority classes remain visible.

The language label is reported in the metrics table for completeness but is
not used as a headline result, because the multimodal pool is overwhelmingly
English-language and the minority centroids are statistically unreliable.

## Quantitative Metrics

### Nearest-Centroid Classifier (Leave-One-Out)

For a similarity matrix \(S\) and a label vector \(y\), the leave-one-out
nearest-centroid score is computed as follows. For each query \(i\) and each
class \(c\), the score is the mean similarity between \(i\) and every other
member of \(c\) (the query itself is excluded from any centroid it would
otherwise belong to). The query is then assigned to the class with the
highest mean similarity, and accuracy is the fraction of correctly assigned
queries. For single-modality and early-fused vectors \(S = X X^{\top}\); for
late fusion \(S\) is the pre-computed weighted combination of per-modality
matrices. The same classifier is therefore evaluated identically across all
modality and fusion settings.

The nearest-centroid classifier is preferred over k-nearest-neighbours in
this setting for three reasons. First, averaging over an entire class
reflects how tightly that class sits in the embedding space, whereas k-NN
with small \(k\) is dominated by nearest-neighbour noise. Second, the
formulation uses cosine similarities only, which lets late fusion be scored
through exactly the same code path as a single modality by pre-computing the
appropriate \(S\). Third, under k-NN, late fusion can be brittle because
blending similarities can promote a noisy near-neighbour to the top, whereas
the centroid average in NCC absorbs that noise so the expected fusion lift is
visible.

### Silhouette (Cosine)

The silhouette score is computed with `metric='cosine'` for single-modality
and early-fused vectors. For late fusion the similarity matrix is converted
to a distance matrix \(D = 1 - S\) and passed with `metric='precomputed'`.
Positive values indicate that class members are closer to their own class
than to other classes on average.

### Adjusted Rand Index

For single-modality and early-fused vectors, K-Means is run with
\(n_{\text{clusters}}\) equal to the number of label classes and the seeded
random state, and the resulting cluster assignment is compared with the
ground-truth labels via the Adjusted Rand Index. For late-fusion similarity
matrices, spectral clustering with `affinity='precomputed'` is used in place
of K-Means so that the kernelised similarity is consumed directly. ARI
complements the supervised NCC score with an unsupervised cluster-purity
measure.

## Held-Out KG Variants for Classification

The classification labels used above are derived from KG predicates that the
RotatE model could otherwise memorise during training. To prevent this
inflation, classification metrics that include the KG modality use the
corresponding held-out RotatE variant for each label, as documented in
[`embeddings/KG_ROTATE.md`](../embeddings/KG_ROTATE.md):

| Label | KG variant used in metric |
|---|---|
| Decade | `kg_heldout_decade_embeddings.parquet` (no `schema:datePublished`) |
| Rating | `kg_heldout_rating_embeddings.parquet` (no `schema:contentRating`) |
| Genre | `kg_heldout_genre_embeddings.parquet` (no `schema:genre`) |
| Language | `kg_heldout_language_embeddings.parquet` (no `schema:inLanguage`) |

Visual projections, the qualitative retrieval grid, and any non-classification
artifact use the `full` RotatE variant, which retains every triple in the
pruned KG.

## Qualitative Figures

### Retrieval Grid

`fig_retrieval_grid.pdf` shows three random query films, sampled with a fixed
seed and stable sort over the multimodal pool. For each query, six rows are
drawn — one per modality (image, video, audio, KG, text average) and one for
the poster-weighted late fusion (\(2:1:1:1:1\)). All six rows search the
*same* multimodal pool so that the comparison between modalities is strictly
apples-to-apples; the top-five neighbours are selected by cosine similarity
with the query itself excluded. Each cell shows the first available
thumbnail under `output/<tt_id>/images/`, the movie title, and the cosine
similarity to the query.

### Intra-Movie Consistency

`fig_consistency_*.pdf` selects the five movies with the largest number of
image embeddings (at least five each) and projects their individual,
non-pooled image vectors with UMAP (main) and t-SNE (supplementary). Tight
per-movie clusters demonstrate that the image encoder is internally
consistent within a single title, supporting the use of a single
mean-pooled vector per movie elsewhere in the pipeline.

## Summary of Design Choices

Visualisations are computed on the intersection of all five modalities
(\(N = 352\)) so that single-modality and fused panels are directly
comparable on identical entity sets. Aggregation follows the
*L2-then-mean-then-L2* convention to preserve cosine geometry. Fusion is
reported in three complementary forms: early fusion for joint vector-space
visualisation, uniform and poster-weighted late fusion for retrieval and
quantitative metrics on equal footing with single modalities, and supervised
cross-validated late fusion as an upper-bound reference. Two-dimensional
projections use UMAP as the primary projector and t-SNE as a robustness
check. Quantitative scores are reported under the leave-one-out
nearest-centroid classifier, which measures global class compactness and
generalises uniformly across raw vectors and late-fusion similarity matrices.
Labels are chosen to probe distinct axes of similarity: *decade* targets
temporal and poster-style drift, *rating* targets target-audience and visual
tone, *genre* targets semantic content, and *language* serves as a sanity
check that is reported with an explicit imbalance caveat.
