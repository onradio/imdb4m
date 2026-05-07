# embeddings_output/

This directory is intentionally empty in the IMDB4M git repository.

The pre-computed embedding tables, the master HDF5 file
(`embeddings.h5`), the RDF pointer file (`embedding_metadata.ttl`),
and the per-variant RotatE training manifests are too large to
distribute via git/GitHub Releases and are archived on Zenodo:

- **DOI**: [10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840)
- **Record**: <https://zenodo.org/records/20057840>

After cloning this repository, download every file from the Zenodo
record and place it directly inside this `embeddings_output/`
directory. The IMDB4M project code reads from `embeddings_output/`
by default (see `embeddings/config.py`), so no further configuration
is needed once the Zenodo files are in place.

## Quick download

Using `zenodo_get`:

```bash
pip install zenodo_get
zenodo_get 10.5281/zenodo.20057840 -o embeddings_output/
```

Or browse and download files manually from the Zenodo landing page.

## Expected layout

After the download completes, this directory should contain:

```
embeddings_output/
├── README.md                                  (this file, kept by git)
├── image_embeddings.parquet                   33,247 × 768   (CLIP ViT-L/14)
├── video_embeddings.parquet                    4,350 × 512   (X-CLIP)
├── audio_embeddings.parquet                    4,034 × 512   (CLAP)
├── text_embeddings.parquet                     4,216 × 1,024 (BGE-large-EN)
├── kg_embeddings.parquet                     139,465 × 512   (RotatE, full)
├── kg_heldout_genre_embeddings.parquet        139,465 × 512
├── kg_heldout_rating_embeddings.parquet       139,465 × 512
├── kg_heldout_decade_embeddings.parquet       139,465 × 512
├── kg_heldout_language_embeddings.parquet     139,465 × 512
├── kg_heldout_all_labels_embeddings.parquet   139,465 × 512
├── kg_pykeen_entities.parquet                 ~656k × 512    (full PyKEEN node table)
├── kg_heldout_*_pykeen_entities.parquet       ~656k × 512    (one per held-out variant)
├── kg_rotate_*_manifest.json                  per-variant training provenance
├── kg_rotate_runs.json                        combined run log
├── embedding_metadata.ttl                     RDF pointers from KG → vector rows
├── embeddings.h5                              master HDF5 mirror (~11 GB, gzip-4)
└── embed_progress.json                        embedding-pipeline checkpoint
```

You can sanity-check the layout with:

```bash
python verify_embeddings_output.py
```

## Why these files are not in git

They total roughly 20 GB uncompressed (and 17 GB even as a single zip),
which is far above what GitHub recommends for source distribution.
Hosting them on Zenodo also gives the embedding bundle its own
permanent DOI, makes it independently citable, and keeps the IMDB4M
codebase lightweight to clone.

## Citation

```bibtex
@dataset{imdb4m_embeddings_2026,
  title  = {{IMDB4M} Multi-Modal and KG Embeddings (v1)},
  author = {Reklos, Ioannis and de Berardinis, Jacopo and Simperl, Elena and Mero{\~n}o-Pe{\~n}uela, Albert},
  year   = {2026},
  doi    = {10.5281/zenodo.20057840}
}
```
