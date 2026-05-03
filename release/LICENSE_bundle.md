# IMDB4M Release — Licence and Use

> **Note.** This is a *stub* prepared by the release-bundling pipeline.
> Please replace the text below with the final legal text you intend to
> publish alongside the dataset.  The exact wording matters and should
> be reviewed by your institution before dissemination.

## 1. Knowledge graph and embedding vectors

The RDF files (`kg/*.ttl`, `embeddings/embedding_metadata.ttl`) and the
numerical embedding tables (`embeddings/*.parquet`, `embeddings/*.h5`)
are released for **non-commercial research use** under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

If you redistribute, modify, or build derivative works:

* Attribute IMDB4M (see `README.md § Citation`).
* Propagate the same licence to derivative works.
* Do not use for commercial purposes without prior written consent.

## 2. IMDB metadata

Textual metadata (titles, person names, credits, ratings …) is sourced
from IMDB and remains subject to
[IMDB's Conditions of Use](https://www.imdb.com/conditions).  The
present bundle contains only fragments sufficient to reproduce the
research KG; consult IMDB for authoritative records.

## 3. Media content

**Original images, video files, and audio clips are not redistributed
in this bundle.**  Only URLs, filenames, and derived embedding vectors
are shipped.  The underlying media remain the property of their
respective rights-holders (studios, artists, IMDB, YouTube uploaders,
etc.).  Any attempt to reconstruct or redistribute the media should
observe the upstream licences and local copyright law.

## 4. Pre-trained models

The embedding vectors were produced with third-party pre-trained
models (CLIP, X-CLIP, CLAP).  Each model has its own licence; consult
the HuggingFace model cards:

* [`openai/clip-vit-large-patch14`](https://huggingface.co/openai/clip-vit-large-patch14)
* [`microsoft/xclip-base-patch32`](https://huggingface.co/microsoft/xclip-base-patch32)
* [`laion/larger_clap_music_and_speech`](https://huggingface.co/laion/larger_clap_music_and_speech)

## 5. No warranty

THE DATASET IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED.  THE AUTHORS SHALL NOT BE LIABLE FOR ANY CLAIM, DAMAGE, OR
OTHER LIABILITY ARISING FROM THE USE OF THE DATASET.
