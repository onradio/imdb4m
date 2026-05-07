<div align="center">

<img src="docs/logo.jpg" alt="IMDB4M Logo" width="400">

# 🎬 IMDB4M

### A Large-Scale Quad-Modal Knowledge Graph of Movies

[![Under Review](https://img.shields.io/badge/Under-Review-blueviolet?style=for-the-badge)]()
[![RDF](https://img.shields.io/badge/RDF-Turtle-00ADD8?style=for-the-badge&logo=semantic-web)](https://www.w3.org/TR/turtle/)
[![Schema.org](https://img.shields.io/badge/Schema.org-Vocabulary-red?style=for-the-badge)](https://schema.org/)
[![CC-BY-NC](https://img.shields.io/badge/License-CC--BY--NC-lightgrey?style=for-the-badge)](https://creativecommons.org/licenses/by-nc/4.0/)
[![1.80M Triples](https://img.shields.io/badge/Triples-1.80M-green?style=for-the-badge)]()
[![Embeddings on Zenodo](https://img.shields.io/badge/Embeddings-Zenodo-1682D4?style=for-the-badge&logo=zenodo&logoColor=white)](https://doi.org/10.5281/zenodo.20057840)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20057840-1682D4?style=for-the-badge&logo=zenodo&logoColor=white)](https://doi.org/10.5281/zenodo.20057840)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

<p align="center">
  <strong>A multi-modal RDF knowledge graph of movies with pre-computed image, video, audio, text, and KG embeddings (released on Zenodo)</strong>
</p>

[Overview](#-overview) •
[Features](#-features) •
[Schema](#-knowledge-graph-schema) •
[Installation](#-installation) •
[Usage](#-usage) •
[Media Downloader](#media-downloader) •
[Embeddings](#-embeddings) •
[Embedding Quality](#-embedding-quality) •
[KG Analysis](#-knowledge-graph-analysis) •
[Validation](#-validation--evaluation) •
[Citation](#-citation)

</div>

---

## 📖 Overview

**IMDB4M** is a large-scale, **quad-modal** knowledge graph for the movie domain that overcomes the bimodal bottleneck of existing multimodal knowledge graphs.

IMDB4M comprehensively harmonises symbolic metadata of movies and actors and integrates them with **four distinct modalities**: text (plots, comments, reviews), images (posters, stills), video (trailers), and audio (soundtracks). Unlike prior resources often constructed with ad-hoc vocabularies, IMDB4M is engineered on **schema.org** to ensure semantic interoperability, discoverability, and structural quality.

The knowledge graph integrates:
- 🎥 **Movie Metadata**: Titles, plots, genres, ratings, release dates, budgets, revenues, production companies
- 🎭 **Cast & Crew**: 5,484 actors, directors, writers with complete filmographies using `schema:PerformanceRole`
- 🎵 **Soundtracks**: Music recordings and compositions with performers, composers, lyricists (94.95% of seed movies, avg. 12.02 `schema:audio` triples per seed movie in the KG)
- 📹 **Videos**: Movie trailers with thumbnails, duration, and upload dates (99.20% coverage)
- 🖼️ **Images**: Movie stills and promotional images with captions and entity links (avg. 7.91 image triples per seed movie incl. `schema:image` and `schema:thumbnail`; 34,039 distinct `schema:ImageObject` instances across the whole KG)
- ⭐ **Reviews & Ratings**: User reviews, aggregate ratings, Metacritic scores, AI-generated summaries
- 🔗 **External Links**: Wikidata entity alignments via `owl:sameAs` mappings (4,284 actors and 376 movies)
- 🧠 **Pre-computed Embeddings (Zenodo)**: Image (CLIP ViT-L/14, 768-d), video (X-CLIP, 512-d), audio (CLAP, 512-d), text (BGE-large-EN, 1024-d), and KG (RotatE 256-d complex / 512-d real) — all L2-normalised

**Key Design Principles:**
- **Linking over Hosting**: Stores external URIs to legitimate platforms (IMDb, YouTube) rather than raw media to respect copyright
- **Schema.org Vocabulary**: Ensures semantic interoperability and Web-scale discoverability
- **First-class Multimodal Objects**: Modalities are typed semantic objects, not flat attributes
- **Disk-aligned KG with Embedding Pointers**: The released `data/kg/imdb_kg_cleaned.ttl` is one-for-one aligned with the embedding rows on Zenodo via `imdb4m:hasEmbedding` records

---

## ✨ Features

### 🗃️ Quad-Modal Data Integration
| Modality | Description | Schema.org Types | Coverage on seed movies (KG-derived) |
|----------|-------------|------------------|------------|
| **Text** | Plots, reviews, keywords, captions, character/job names | `schema:name`, `schema:abstract`, `schema:description`, `schema:reviewBody`, `schema:caption`, `schema:keywords`, `schema:genre`, `schema:inLanguage`, `schema:contentRating`, `schema:alternateName`, `schema:characterName`, `schema:jobTitle`, `schema:currency`, `schema:unitCode` | 100.00% coverage, 70.44 text triples / seed movie |
| **Image** | Stills, posters with captions & entity links | `schema:ImageObject` | 100.00% coverage, 7.91 image triples / seed movie (`schema:image` + `schema:thumbnail`) |
| **Video** | Trailers with thumbnails, duration, upload dates | `schema:VideoObject` | 99.20% coverage, 0.99 `schema:trailer` triples / seed movie |
| **Audio** | Soundtracks with performers, composers, lyricists | `schema:MusicRecording`, `schema:MusicComposition` | 94.95% coverage, 12.02 `schema:audio` triples / seed movie |

> All numbers in this table are **derived directly from `data/kg/imdb_kg_cleaned.ttl`**, not from the per-entity TTL corpus. The cleaned KG is the disk-aligned subset that was kept after pruning movies whose media could not be downloaded or whose modality files could not be reconciled with the on-disk layout, so per-movie figures here are slightly lower than what the raw per-entity TTL files would suggest.

### 📊 Knowledge Graph Statistics

| Metric | Value |
|--------|-------|
| **RDF Triples** | 1,800,490 |
| **Unique RDF Nodes** (URIs + literals + bnodes) | 656,121 |
| **URIRef Entities** (released as KG embeddings) | 139,465 |
| **Distinct Predicates** | 58 |
| **Seed Movies (fully annotated)** | 376 |
| **Total Movies (`schema:Movie` instances)** | 50,756 |
| **Artists Analyzed (actors, directors, composers)** | 5,484 |
| **`schema:PerformanceRole` instances** | 232,492 |
| **`schema:ImageObject` instances** | 34,039 |
| **`schema:VideoObject` instances** | 3,981 |
| **`schema:Person` instances** | 16,994 |
| **`schema:MusicRecording` instances** | 4,521 |
| **`schema:MusicComposition` instances** | 3,970 |
| **`schema:AggregateRating` instances** | 734 |
| **`schema:Review` instances** | 563 |
| **Wikidata Alignments** | 4,284 actors + 376 movies (4,660 `owl:sameAs` triples) |

> The companion `void.ttl` reports `void:entities = 392,778` (URIs + blank nodes only), per the [VoID vocabulary](https://www.w3.org/TR/void/) where literals are values *of* entities rather than entities themselves. The 656,121 figure above includes literals, which is the more useful number when sizing the KG for loading. See the [Embeddings](#-embeddings) section for the separate **656,003** PyKEEN entity-table count and why it differs by 118 from the rdflib node count.

### 📈 Modality Coverage (Seed Movies, KG-derived)

All values below are computed directly from `data/kg/imdb_kg_cleaned.ttl` by `modality_count_from_cleaned_kg.py` and match the paper's Table 5 verbatim. "Coverage" is the number of seed movies (those carrying at least one `schema:abstract` literal) that also assert at least one triple of the corresponding modality. "Avg. per movie" is the per-modality element count obtained by traversing seed-movie URIs together with the directly attached blank nodes and media objects (reviews, performance roles, recordings, image/video objects); the cleaned KG contains both `https://www.imdb.com/title/tt…` and `…/tt…/` URI variants for some movies, which are unioned by `tt` ID to avoid double-counting.

| Modality | Coverage | Avg. per Seed Movie | Seed-set Total |
|----------|----------|--------------------:|---------------:|
| Text (14 predicates: name, abstract, description, reviewBody, caption, keywords, genre, inLanguage, contentRating, alternateName, characterName, jobTitle, currency, unitCode) | 100.00% (376/376) | 70.44 | 26,486 |
| Images (`schema:image` + `schema:thumbnail`) | 100.00% (376/376) | 7.91 | 2,975 |
| Video (`schema:trailer`) | 99.20% (373/376) | 0.99 | 373 |
| Audio (`schema:audio`) | 94.95% (357/376) | 12.02 | 4,521 |

**355 / 376 (94.41%)** of seed movies have all four modalities simultaneously in the KG.

### 👥 Actor-side Totals (5,484 Actors, KG-derived)

| Predicate | Total triples in KG |
|-----------|--------------------:|
| `schema:performerIn` | 240,607 |
| `schema:actor` | 471,741 |
| `schema:characterName` | 232,492 |
| `schema:jobTitle` | 11,467 |

### 🔗 External Linkage
- **Wikidata Integration**: 4,284 actor `owl:sameAs` mappings + 376 movie `owl:sameAs` mappings (`data/kg/sameas_mappings.ttl`)
- **YouTube Links**: 4,211 soundtrack-to-video links (3,883 unique videos) across 357 movies, produced by the neuro-symbolic RAG pipeline (87.16% accuracy on the validation sample); these resolve to the 4,521 `schema:audio` triples in the cleaned KG

---

## 🏗️ Knowledge Graph Schema

IMDB4M uses [Schema.org](https://schema.org/) vocabulary as its primary ontology, chosen for:
1. **Coverage**: Provides primitives for movies, creative works, media objects, ratings, monetary values
2. **Expressiveness**: Rich typed representations via `schema:ImageObject`, `schema:VideoObject`, `schema:MusicRecording`
3. **Interoperability**: Widely adopted across the Web of Data, natively used by IMDb and YouTube

A small auxiliary namespace `imdb4m: <http://imdb4m.org/embedding/>` is used by the Zenodo embedding release to attach `imdb4m:hasEmbedding` records to KG subjects, pointing back to specific Parquet/HDF5 rows of the released vectors (see [Embeddings](#-embeddings) below).

<div align="center">
<img src="docs/imdb_example.png" alt="IMDB4M Knowledge Graph Schema" width="800">
</div>

### Schema Design Principles

- **PerformanceRole Pattern**: Actor participation uses `schema:PerformanceRole` to capture actor, movie, and `schema:characterName` together
- **N-ary Structures**: Typed blank nodes with `xsd:date`, `xsd:dateTime`, `xsd:duration`, `xsd:integer`, `xsd:decimal`
- **Two-level Audio**: `schema:MusicRecording` for performed audio, `schema:MusicComposition` for underlying work

### Key Properties

| Property | Domain | Range | Description |
|----------|--------|-------|-------------|
| `schema:actor` | Movie | PerformanceRole | Cast member with character |
| `schema:characterName` | PerformanceRole | Text | Character played by actor |
| `schema:director` | Movie | Person | Film director |
| `schema:creator` | Movie | Person | Writer/creator |
| `schema:trailer` | Movie | VideoObject | Movie trailer |
| `schema:audio` | Movie | MusicRecording | Soundtrack entry |
| `schema:image` | Movie | ImageObject | Movie still/poster |
| `schema:aggregateRating` | Movie | AggregateRating | IMDb/Metacritic score |
| `schema:review` | Movie | Review | User review |
| `schema:byArtist` | MusicRecording | Person | Performer |
| `schema:recordingOf` | MusicRecording | MusicComposition | Underlying musical work |
| `schema:composer` | MusicComposition | Person | Music composer |
| `schema:lyricist` | MusicComposition | Person | Lyrics writer |
| `schema:caption` | ImageObject | Text | Image description |
| `schema:mainEntity` | ImageObject | Person | Cast members in image |
| `schema:embedUrl` | VideoObject | URL | Trailer embed URL |
| `schema:thumbnailUrl` | VideoObject | URL | Trailer thumbnail |
| `schema:duration` | VideoObject | Duration | Video length (xsd:duration) |
| `schema:performerIn` | Person | Movie | Actor filmography |
| `owl:sameAs` | Entity | WikidataURI | External link |
| `imdb4m:hasEmbedding` | KG entity | EmbeddingRecord | Pointer to the Parquet / HDF5 row in the Zenodo embedding release |

---

## 📁 Repository Structure

```
imdb4m/
├── 📂 data/
│   ├── 📂 movies/                   # Movie data organized by IMDb ID
│   │   └── 📂 tt0120338/            # Example: Titanic
│   │       ├── 📂 movie_html/       # Parsed movie metadata (.ttl)
│   │       └── 📂 movie_soundtrack/ # Soundtrack metadata (.ttl, .json)
│   ├── 📂 kg/                       # Consolidated knowledge graph
│   │   ├── imdb_kg_cleaned.ttl      # Main KG file (disk-aligned)
│   │   └── sameas_mappings.ttl     # Wikidata alignments
│   └── 📂 sample/                   # Sample subset for testing
│
├── 📂 embeddings/                   # Embedding-pipeline source code, kept
│   ├── embed_all.py                #   for transparency / model attribution.
│   ├── image_embedder.py           #   The released vectors live on Zenodo
│   ├── video_embedder.py           #   (DOI 10.5281/zenodo.20057840) — the
│   ├── audio_embedder.py           #   pipeline is not re-runnable without
│   ├── text_embedder.py            #   the source media, which we do not
│   ├── kg_rotate.py                #   redistribute (Linking over Hosting).
│   └── KG_ROTATE.md                # KG embedding documentation
│
├── 📂 embeddings_output/            # Empty by default. Drop the Zenodo
│   └── README.md                   #   files here so the project picks them up.
│
├── 📂 kg_cleanup/                   # Disk-alignment pipeline that produces
│   └── README.md                   #   the released `imdb_kg_cleaned.ttl`
│
├── 📂 plots/                        # Embedding-quality figures and metrics
│   ├── embedding_projections.py
│   └── EMBEDDING_VIZ.md
│
├── 📂 linker/                       # Music Linker module (RAG)
│   ├── models.py
│   ├── youtube_client.py
│   ├── gemini_matcher.py
│   └── music_linker.py
│
├── 📂 media_downloader/             # Media Download module
│   ├── kg_parser.py                # KG parser for media URLs
│   ├── image_downloader.py         # Image download from Amazon CDN
│   ├── video_downloader.py         # Video download from IMDb
│   ├── audio_downloader.py         # Audio download from YouTube
│   ├── download_entity.py          # Single entity downloader
│   └── download_all.py             # Batch downloader with resume
│
├── 📂 extractor/                    # Data collection scripts
│   ├── download_imdb_movie.py      # Movie page extractor
│   ├── download_imdb_actor.py      # Actor page extractor
│   └── 📂 movie_seeds/             # Movie selection criteria
│
├── 📂 QA/                           # Competency questions, gold answers, and
│                                    # the QA evaluator (see Validation below)
│
├── 📜 parse_imdb_movie.py          # HTML → RDF parser (movies)
├── 📜 parse_imdb_actor.py          # HTML → RDF parser (actors)
├── 📜 parse_soundtrack_to_ttl.py   # Soundtrack → RDF parser
├── 📜 analyze_kg.py                # KG statistics & analysis
├── 📜 count_kg_properties.py       # Predicate / type frequency report
├── 📜 modality_count_movies.py     # Per-movie modality coverage
├── 📜 modality_count_actors.py     # Per-actor modality coverage
├── 📜 count_youtube_links.py       # Soundtrack ↔ YouTube link counter
├── 📜 create_sameas_mappings.py    # Wikidata linking
└── 📜 requirements.txt             # Python dependencies
```

> **Note:** the `embeddings_output/` directory ships empty in this repository — the project code reads from it, but the actual vectors are too large to distribute via git. Download them from Zenodo ([10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840)) and drop the files directly into `embeddings_output/`. See the [Embeddings](#-embeddings) section below for full instructions.

---

## 🔧 Construction Methodology

IMDB4M follows a four-stage pipeline:

### 1. Seeding Strategy
- Sampled **N=100 movies per decade** (1980-2020) for temporal diversity
- Resulted in **376 distinct seed movies** after deduplication
- Each seed enriched with top 20 cast, trailers, images, reviews

### 2. Recursive Expansion
- Extracted **5,484 unique artists** from seed movies
- Retrieved complete filmographies to extend neighbourhood structure
- Captured latent connections through shared collaborators

### 3. Pruning and Disk Alignment
- Removed leaf-node movies connected to only one artist
- Reconciled the KG against the actually downloaded media (`kg_cleanup/` pipeline) so every media triple in `data/kg/imdb_kg_cleaned.ttl` corresponds to a file that exists on disk
- Yielded a refined core of **50,756 movies**, **5,484 artists**, **656,121 unique RDF nodes** (139,465 distinct URIRefs), and **1,800,490 triples** across **58 distinct predicates**

### 4. External Linking
- **Wikidata Alignment**: Query SPARQL endpoint via IMDb ID property P345 → 4,284 actor + 376 movie `owl:sameAs` mappings
- **YouTube Linking**: RAG pipeline with Gemini verification → 4,211 soundtrack-to-YouTube links across 357 movies (asserted as 4,521 `schema:audio` triples in the cleaned KG)

### 5. Embedding
- **Media + text vectors** were produced from the downloaded media files with CLIP ViT-L/14 (images), X-CLIP base-32 (videos), LAION CLAP (audio), and BGE-large-EN (KG text literals)
- **KG vectors** were trained with PyKEEN's `RotatE` on the full KG plus four held-out variants (decade / rating / genre / language) and a stricter `all-labels` variant — see [embeddings/KG_ROTATE.md](embeddings/KG_ROTATE.md) for the full pipeline write-up
- The trained vectors are archived on Zenodo at [10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840) and referenced from the KG via `imdb4m:hasEmbedding` (see [Embeddings](#-embeddings))
- The original images, videos, and audio files are **not redistributed** with this project, in line with IMDb / YouTube terms of use; only the URLs and the derived vectors are shared.

### Data Extraction
The extraction pipeline leverages:
- **JSON-LD blocks** from IMDb pages (primary source for schema.org metadata)
- **Next.js data payloads** for deeply nested structures (credits, filmographies, reviews)
- **DOM traversal fallback** for alternate titles, budgets, gallery references

---

## 🚀 Installation

### Prerequisites
- Python 3.10 or higher
- pip package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/onradio/imdb4m.git
cd imdb4m

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### API Keys (Optional - for Music Linker)

For soundtrack-to-YouTube linking functionality:

1. **YouTube Data API v3**: [Google Cloud Console](https://console.cloud.google.com/)
2. **Google Gemini API**: [Google AI Studio](https://aistudio.google.com/app/apikey)

```bash
# Create .env file with your keys
cp .env.template .env
# Edit .env with your API keys
```

---

## 📚 Usage

### Loading the Knowledge Graph

`data/kg/imdb_kg_cleaned.ttl` is the disk-aligned KG: every media triple it asserts corresponds to a downloadable image, video, or audio file, and one-for-one to a row in the embeddings released on Zenodo.

```python
from rdflib import Graph

g = Graph()
g.parse("data/kg/imdb_kg_cleaned.ttl", format="turtle")

print(f"Loaded {len(g)} triples")
```

### SPARQL Queries

```python
# Find all movies with their directors
query = """
PREFIX schema: <http://schema.org/>

SELECT ?movie ?title ?director ?directorName
WHERE {
    ?movie a schema:Movie ;
           schema:name ?title ;
           schema:director ?director .
    ?director schema:name ?directorName .
}
LIMIT 10
"""

for row in g.query(query):
    print(f"{row.title} - Directed by {row.directorName}")
```

### Query Videos/Trailers

```python
# Find all movies with trailers
query = """
PREFIX schema: <http://schema.org/>

SELECT ?movie ?title ?trailerName ?embedUrl ?duration
WHERE {
    ?movie a schema:Movie ;
           schema:name ?title ;
           schema:trailer ?trailer .
    ?trailer a schema:VideoObject ;
             schema:name ?trailerName ;
             schema:embedUrl ?embedUrl .
    OPTIONAL { ?trailer schema:duration ?duration }
}
LIMIT 10
"""

for row in g.query(query):
    print(f"{row.title}: {row.trailerName} - {row.embedUrl}")
```

### Parsing New Movies

```bash
# Parse a movie HTML file
python parse_imdb_movie.py path/to/movie.html -o output.ttl

# Parse soundtrack data
python parse_soundtrack_to_ttl.py path/to/soundtrack.html
```

### Neuro-Symbolic Audio Linker

The Music Linker uses a **Retrieval-Augmented Generation (RAG)** pipeline to link soundtrack entities to YouTube videos:

1. **Stage 1 - Retrieval**: Query YouTube Data API v3 using soundtrack metadata (title, artist, movie) with progressive relaxation
2. **Stage 2 - Verification**: Use Gemini 2.5 Flash as a neuro-symbolic reasoner to verify candidates and disambiguate between official releases vs covers

```python
from linker import MusicLinker, SoundtrackParser, Config

# Initialize
config = Config()
linker = MusicLinker(
    youtube_api_key=config.youtube_api_key,
    gemini_api_key=config.gemini_api_key
)

# Parse soundtrack from TTL
soundtracks = SoundtrackParser.parse_soundtrack_ttl(
    subset_root="data/sample",
    imdb_id="tt0120338"  # Titanic
)

# Find YouTube matches (87.16% accuracy)
results = linker.find_matches_batch(soundtracks)

for result in results:
    if result.best_match:
        print(f"🎵 {result.soundtrack.title}: {result.best_match.url}")
```

### Media Downloader

The **Media Downloader** module allows you to download actual media files (images, videos, audio) referenced in the Knowledge Graph. It respects rate limits and supports resumable batch downloads.

#### Download Media for a Single Entity

```bash
# Download all media for a movie (images, trailer, soundtrack audio)
python -m media_downloader.download_entity tt0120338

# Download all media for an actor
python -m media_downloader.download_entity nm0000138

# Download only images
python -m media_downloader.download_entity tt0120338 --images-only

# Download only videos (trailers)
python -m media_downloader.download_entity tt0120338 --videos-only

# Download only audio (from YouTube soundtracks)
python -m media_downloader.download_entity tt0120338 --audio-only
```

#### Batch Download All Entities

```bash
# Download media for all entities in the KG
python -m media_downloader.download_all

# Only movies, only images
python -m media_downloader.download_all --movies-only --images-only

# Only persons (actors, directors)
python -m media_downloader.download_all --persons-only

# Custom rate limiting (slower for sensitive servers)
python -m media_downloader.download_all --delay 5 --entity-delay 10 --batch-delay 120

# Test with limited entities
python -m media_downloader.download_all --max-entities 100
```

#### Output Structure

```
output/
├── tt0120338/              # Titanic
│   ├── images/             # Movie stills and posters
│   ├── videos/             # Trailers (MP4)
│   └── audio/              # Soundtrack tracks (from YouTube)
├── nm0000138/              # Leonardo DiCaprio
│   ├── images/             # Actor photos
│   └── videos/             # Actor-related videos
└── download_progress.json  # Resume tracking
```

#### Features

| Feature | Description |
|---------|-------------|
| **Resume Support** | Progress saved to JSON; interrupted downloads resume automatically |
| **Rate Limiting** | Configurable delays between downloads to avoid anti-bot measures |
| **Batch Processing** | Process all KG entities with automatic breaks |
| **Selective Download** | Filter by entity type (movie/person) or media type (image/video/audio) |

#### Rate Limiting Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `--delay` | 2.0s | Delay between individual media downloads |
| `--entity-delay` | 5.0s | Delay between entities |
| `--batch-size` | 10 | Entities per batch before longer break |
| `--batch-delay` | 30s | Break duration between batches |

---

## 📹 Video Representation

IMDB4M captures movie trailers as `schema:VideoObject` entities:

```turtle
<https://www.imdb.com/title/tt0120338> schema:trailer <https://www.imdb.com/video/vi1740686617> .

<https://www.imdb.com/video/vi1740686617> a schema:VideoObject ;
    schema:name "Official Trailer" ;
    schema:description "A seventeen-year-old aristocrat falls in love..." ;
    schema:duration "PT1M37S"^^xsd:duration ;
    schema:embedUrl <https://www.imdb.com/video/vi1740686617/> ;
    schema:thumbnailUrl <https://m.media-amazon.com/images/M/...jpg> ;
    schema:uploadDate "2023-01-10T18:08:38.447000+00:00"^^xsd:dateTime .
```

---

## 🎵 Soundtrack Representation

Detailed soundtrack modeling with performers, composers, and compositions:

```turtle
<https://www.imdb.com/title/tt0120338/> schema:audio [
    a schema:MusicRecording ;
    schema:name "My Heart Will Go On" ;
    schema:byArtist <https://www.imdb.com/name/nm0001144/> ;  # Céline Dion
    schema:producer <https://www.imdb.com/name/nm0000035/> ;  # James Horner
    schema:recordingOf [
        a schema:MusicComposition ;
        schema:name "My Heart Will Go On" ;
        schema:composer <https://www.imdb.com/name/nm0000035/> ;  # James Horner
        schema:lyricist <https://www.imdb.com/name/nm0421263/>   # Will Jennings
    ]
] .
```

---

## 🖼️ Image Representation

Movie stills with captions, dimensions, and entity links:

```turtle
<https://www.imdb.com/title/tt0120338/mediaviewer/rm4035688192/> a schema:ImageObject ;
    schema:caption "Leonardo DiCaprio and Kate Winslet in Titanic (1997)" ;
    schema:width 2048 ;
    schema:height 1385 ;
    schema:url <https://m.media-amazon.com/images/M/...jpg> ;
    schema:mainEntity <https://www.imdb.com/name/nm0000138/>,  # Leonardo DiCaprio
                      <https://www.imdb.com/name/nm0000701/> . # Kate Winslet
```

---

## 🔗 Wikidata Integration

IMDB4M includes `owl:sameAs` mappings to Wikidata for enhanced interoperability (4,284 actor mappings + 376 movie mappings, 4,660 `owl:sameAs` triples in total):

```turtle
<https://www.imdb.com/title/tt0120338> owl:sameAs <http://www.wikidata.org/entity/Q44578> .
<https://www.imdb.com/name/nm0000138> owl:sameAs <http://www.wikidata.org/entity/Q38111> .
```

Generate mappings:
```bash
python create_sameas_mappings.py
```

---

## 🧠 Embeddings

IMDB4M ships pre-computed embeddings for **every released modality** (image, video, audio, text) plus **knowledge-graph embeddings** trained with PyKEEN's RotatE on `data/kg/imdb_kg_cleaned.ttl`. All vectors are L2-normalised (cosine similarity equals dot product) and aligned one-for-one to the KG via `imdb4m:hasEmbedding` records.

> **Where to get them:** the embedding files are **not stored in this git repository**. They are released as a Zenodo deposit at [10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840). After cloning this repo, drop the Zenodo files into the empty `embeddings_output/` directory at the project root — see [Download from Zenodo](#download-from-zenodo) below.

> **Note on entity counts (rdflib vs PyKEEN).** All KG-size figures elsewhere in this README (e.g. **656,121 unique RDF nodes**, **263,343 literal nodes**) are computed by parsing `data/kg/imdb_kg_cleaned.ttl` with `rdflib`. The PyKEEN entity table that backs the released KG embeddings has **656,003** rows instead — 118 fewer than rdflib reports — because PyKEEN dedupes literals more aggressively than rdflib (e.g., literals with identical lexical form but different datatypes or language tags are collapsed into one entity). The 118-node delta is entirely in the literal block (rdflib: 263,343 distinct literals; PyKEEN: 263,225). Concretely, the released bundle contains:
>
> - **139,465** rows in the URIRef KG-embedding table (the table most users actually consume) — unaffected by the dedup difference.
> - **~656,003** rows in the optional `/kg_pykeen_entities/` HDF5 group, which exposes embeddings for *every* PyKEEN entity (URIs + blank nodes + deduped literals).
>
> Both numbers describe the same KG (`data/kg/imdb_kg_cleaned.ttl`); they differ only in how the literal namespace is collapsed.

### Released Vectors

| Modality | Rows | Dim | Model | Source predicates / files |
|---|---:|---:|---|---|
| Image | 33,247 | 768 | [`openai/clip-vit-large-patch14`](https://huggingface.co/openai/clip-vit-large-patch14) | Movie & actor stills (`schema:ImageObject`) |
| Video | 4,350 | 512 | [`microsoft/xclip-base-patch32`](https://huggingface.co/microsoft/xclip-base-patch32) | Trailers and movie clips (`schema:VideoObject`) |
| Audio | 4,034 | 512 | [`laion/larger_clap_music_and_speech`](https://huggingface.co/laion/larger_clap_music_and_speech) | Soundtrack tracks resolved to YouTube |
| Text | 4,216 | 1,024 | [`BAAI/bge-large-en-v1.5`](https://huggingface.co/BAAI/bge-large-en-v1.5) | `schema:abstract`, `schema:description`, `schema:reviewBody`, `schema:caption` |
| KG (RotatE) | 139,465 | 512 (real, from 256-d complex) | `pykeen/rotate/imdb4m-full-d256` | All KG `URIRef` entities |

### Held-out KG Variants

To support clean classification benchmarks, RotatE is additionally trained with specific label predicates removed before training. Held-out predicates are listed below; the all-labels run held out 66,838 triples (1,731,988 used for training).

| Variant | Held-out predicate(s) | Purpose |
|---|---|---|
| `full` | none | KG retrieval, projections, and KG-inclusive fusion |
| `genre` | `schema:genre` | Clean genre classification |
| `rating` | `schema:contentRating` | Clean rating classification |
| `decade` | `schema:datePublished` | Clean decade classification |
| `language` | `schema:inLanguage` | Clean language classification |
| `all-labels` | the four above, jointly | Stricter robustness setting |

### Storage Format

Each modality is delivered as a **Parquet** (zstd) file and a group inside a single master **HDF5** (gzip-4) file. Row order is shared between the two formats so `parquet_row == hdf5_index`.

| Column | Type | Notes |
|---|---|---|
| `entity_id` | string | Stable ID, e.g. `tt0120338`, `nm0000138`, `rm...`, `vi...`, or `kg_<sha1>` |
| `kg_uri` | string | Full schema.org URI of the entity |
| `source_url` | string | CDN / IMDb / YouTube URL of the media (empty for KG and text) |
| `filename` | string | Basename on disk or stable text row id |
| `model_id` | string | Hugging Face / PyKEEN identifier |
| `embedding` | `FixedSizeList[float32]` | 768 (image), 512 (video, audio, KG), or 1,024 (text) |

### Linking Vectors Back to KG Subjects

The Zenodo release includes an `embedding_metadata.ttl` file that emits one `imdb4m:hasEmbedding` record per parquet row. Each record names the parquet file, parquet row, HDF5 group, and HDF5 row index, so a SPARQL result can be joined directly against the vector table.

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

### Quick Start (after downloading from Zenodo)

```python
import pyarrow.parquet as pq
import numpy as np

t  = pq.read_table("image_embeddings.parquet")
df = t.to_pandas()
X  = np.stack(df["embedding"].to_numpy())   # (33247, 768) L2-normalised
ids = df["entity_id"].to_numpy()
```

```python
import h5py

with h5py.File("embeddings.h5", "r") as hf:
    X   = hf["/image/embeddings"][:]        # (33247, 768) float32
    ids = hf["/image/entity_id"][:]         # (33247,) bytes
    assert hf["/image"].attrs["normalized"]
```

### SPARQL: Joining KG and Vectors

```sparql
PREFIX schema: <http://schema.org/>
PREFIX imdb4m: <http://imdb4m.org/embedding/>

SELECT ?movie ?poster ?row WHERE {
  ?movie a schema:Movie ;
         schema:image ?poster .
  ?poster imdb4m:hasEmbedding [
    imdb4m:modality   "image" ;
    imdb4m:parquetRow ?row
  ] .
}
```

### Alignment Guarantee

Every row in the released parquet files has a matching subject in `data/kg/imdb_kg_cleaned.ttl`.

| Modality | Parquet rows | KG references | Orphans | Missing |
|---|---:|---:|---:|---:|
| Image | 33,247 | 33,247 | 0 | 0 |
| Video | 4,350 | 4,350 | 0 | 0 |
| Audio | 4,034 | 357 entities | 0 | 3 entities* |

\* Three movies assert ≥1 soundtrack track in the KG but the track lacks a resolvable YouTube URL and was therefore not embedded.

### Download from Zenodo

The pre-computed vectors are archived at
[10.5281/zenodo.20057840](https://doi.org/10.5281/zenodo.20057840). To
hook them up to the project code, clone this repo and drop every file
from the Zenodo deposit into the empty `embeddings_output/` directory:

```bash
git clone https://github.com/onradio/imdb4m.git
cd imdb4m
pip install -r requirements.txt

# Pull every file from the Zenodo record straight into embeddings_output/
pip install zenodo_get
zenodo_get 10.5281/zenodo.20057840 -o embeddings_output/

# Sanity-check that everything is in place
python verify_embeddings_output.py
```

Once `embeddings_output/` is populated, the rest of the project (KG
loaders, plotting code, embedding-quality scripts, the `release/`
bundling pipeline, etc.) picks the files up automatically — no further
configuration is needed. See [embeddings/KG_ROTATE.md](embeddings/KG_ROTATE.md)
for the per-variant training metadata that ships alongside the vectors,
and [release/README_bundle.md](release/README_bundle.md) for the
release-bundle layout.

> **Note on reproducibility.** IMDB4M follows the *Linking over
> Hosting* principle and does not redistribute the underlying images,
> videos, or audio clips, so the embedding pipeline cannot be re-run
> end-to-end without first re-downloading the source media from IMDb
> and YouTube under their respective terms of use. The code under
> `embeddings/` is published for transparency and review of the exact
> models / hyper-parameters used to produce the released vectors.

---

## 📐 Embedding Quality

The `plots/embedding_projections.py` pipeline measures how well each modality (and several fusion strategies) recovers KG-derived labels for the 352-movie multimodal intersection. Headline numbers from [plots/out/tab_fusion_metrics.tex](plots/out/tab_fusion_metrics.tex), evaluated with leave-one-out **NCC accuracy**:

| Modality / Fusion | Decade (5 classes) | Rating (4 classes) | Genre (9 classes) |
|---|---:|---:|---:|
| Random baseline | 20.0% | 25.0% | 11.1% |
| Poster (CLIP ViT-L/14) | 77.6% | 61.2% | 37.5% |
| Trailer (X-CLIP) | 44.6% | 56.9% | 30.1% |
| Soundtrack (CLAP) | 34.9% | 29.5% | 13.8% |
| KG (RotatE, label-held-out) | 38.4% | 48.0% | 25.8% |
| Text balanced avg. (BGE) | 40.3% | 64.3% | 50.1% |
| Fused, late, poster-weighted (2:1:1:1:1) | **65.6%** | **63.7%** | **42.7%** |
| Fused, supervised CV late | **80.0%** ± 4.2 | **61.6%** ± 2.2 | **57.4%** ± 6.0 |

Visualisations (UMAP / t-SNE 2-D projections per modality, qualitative top-5 retrieval grids, intra-movie consistency plots) and the full numerical breakdown live under [plots/out/](plots/out/), described in [plots/EMBEDDING_VIZ.md](plots/EMBEDDING_VIZ.md).

> **Caveat:** the language-classification numbers are reported in the appendix only — ~94 % of the pool is English, so minority centroids are unreliable.

---

## 📈 Knowledge Graph Analysis

```bash
# Analyse the released KG (no files are written)
python analyze_kg.py                                  # defaults to data/kg/imdb_kg_cleaned.ttl
python analyze_kg.py --kg path/to/other.ttl          # analyse a different KG file

# Legacy mode: rebuild the cleaned KG from the per-entity TTL corpus
python analyze_kg.py --build --source-dir data/movies --output-dir data/kg
```

### Entity Type Distribution

| Type | Count |
|------|------:|
| `schema:PerformanceRole` | 232,492 |
| `schema:Movie` | 50,756 |
| `schema:ImageObject` | 34,039 |
| `schema:Person` | 16,994 |
| `schema:MusicRecording` | 4,521 |
| `schema:Place` | 4,009 |
| `schema:VideoObject` | 3,981 |
| `schema:MusicComposition` | 3,970 |
| `schema:QuantitativeValue` | 3,054 |
| `schema:Award` | 1,991 |
| `schema:MonetaryAmount` | 832 |
| `schema:AggregateRating` | 734 |
| `schema:Review` | 563 |
| `schema:Organization` | 531 |
| `schema:Rating` | 487 |

**Top Predicates** (by triple count, computed via `rdflib`): `schema:actor` (471,741), `schema:type` (359,614), `schema:performerIn` (240,607), `schema:characterName` (232,492), `schema:url` (91,168), `schema:name` (82,853), `schema:datePublished` (64,153), `schema:height` (37,093), `schema:width` (34,039), `schema:caption` (34,039), `schema:image` (34,039), `schema:description` (18,885), `schema:jobTitle` (11,467), `schema:author` (5,728), `schema:audio` (4,521).

> Earlier versions of this table reported predicate counts derived from a regex line-scan of the Turtle file. Those numbers undercounted any predicate that uses Turtle's "object list" shorthand (e.g. `?m schema:actor [...], [...], [...]` is one source line but three triples). The values above come from `rdflib`-parsed triples and are the canonical counts.

### Graph Structure Statistics

The graph below is the directed multigraph induced by all `(subject, predicate, object)` triples in `data/kg/imdb_kg_cleaned.ttl`. URIs, blank nodes, and literals are all nodes; predicates become edge labels. The "URI-entity view" only retains URI-to-URI edges, which is the structurally meaningful subgraph for entity-based analyses.

| Metric | Value | Notes |
|--------|------:|-------|
| Total Triples | 1,800,490 | rdflib parse |
| Unique Subjects | 359,615 | URIs + blank nodes that appear as subjects |
| Unique Objects | 656,093 | URIs + blank nodes + literals |
| Unique Predicates | 58 | |
| Unique Nodes (full graph) | 656,121 | 139,465 URIs + 253,313 blank nodes + 263,343 literals |
| Connected Components (URI view) | 1 | the URI-entity subgraph is fully connected |
| Largest Component (URI view) | 139,096 nodes (100.0%) | every URI entity is reachable |
| Average Degree (full graph) | 5.49 | undirected total degree |
| Average In/Out Degree (full graph) | 2.74 / 2.74 | matches `triples / nodes` |
| Average Degree (URI view) | 7.19 | URI ↔ URI edges only |
| Max Total Degree | 232,492 | the `schema:PerformanceRole` *type* node (every PerformanceRole points to it) |
| Max Out-Degree | 786 | the most prolific actor URI (a hub of `schema:performerIn` edges) |
| Max In-Degree | 232,492 | same `schema:PerformanceRole` type hub |
| Source Nodes (in=0, out>0) | 28 | typically top-level seeds and namespace hubs |
| Sink Nodes (out=0, in>0) | 296,249 (45.2% of full graph) | predominantly literals and dangling references |
| Leaf Nodes (full graph, deg=1) | 253,779 (38.7%) | mostly literals |
| Leaf Nodes (URI view, deg=1) | 35,960 (25.9%) | one-off URI references (e.g. external links) |
| Blank Nodes | 253,313 (38.61% of all nodes) | mostly `schema:PerformanceRole`, `schema:MusicRecording`, `schema:Rating`, `schema:Review`, `schema:MonetaryAmount` reified relations |
| Hub Nodes (top 1% by total degree) | 6,630 nodes with degree ≥ 37 | dominated by prolific actors, schema-type hubs, and frequently-referenced roles |
| Density (URI view) | 5.17 × 10⁻⁵ | sparse, as expected for a Web-scale KG |
| Movies with a single actor (`schema:performerIn`) | 1 | residual edge case from the cleanup pipeline |
| Orphan movies (single actor + minimal info) | 0 | the disk-alignment pipeline removes them |

These statistics are produced by `analyze_kg.py` (analyse-only mode) in roughly 70 seconds on a single core. The full output, including a breakdown of movies by actor count and the top-15 predicate / type distributions, is printed to stdout.


---

## 📊 Validation & Evaluation

IMDB4M includes a comprehensive validation framework combining SPARQL-based question answering, KG-wide competency-question coverage, and human-validated link verification.

### Validation Results

The headline metrics come from `QA/evaluate_qa.py` (a `QA/qa_kg.json` ↔ `QA/QA_gold.json` comparison over 18 competency questions × 20 sample movies = 360 question instances). The query-success rate is computed by re-running each SPARQL pattern over **all 376 seed movies** in `data/kg/imdb_kg_cleaned.ttl` (so 6,768 total question instances, of which 6,720 return at least one answer). The YouTube-link accuracy is the human-validated agreement rate from `soundtrack_links.xlsx` (148 validated links, 129 confirmed correct).

| Metric | Value | Source |
|--------|------:|--------|
| Overall F1 Score | 98.72% | `QA/evaluate_qa.py` (set-based, 20-movie sample) |
| Precision | 99.35% | `QA/evaluate_qa.py` |
| Recall | 98.09% | `QA/evaluate_qa.py` |
| Exact Match Rate | 94.72% | `QA/evaluate_qa.py` |
| Avg. Levenshtein Similarity | 0.993 | `QA/evaluate_qa.py` |
| Query Success Rate (KG-wide) | 99.29% | 6,720 / 6,768 question instances over 376 seeds |
| YouTube Link Accuracy | 87.16% | `soundtrack_links.xlsx` (129/148 human-validated) |

### Running Evaluation

```bash
# Per-movie QA evaluation on the 20-movie sample
python QA/evaluate_qa.py            # writes QA/evaluation_results.csv

# KG-wide graph + RDF statistics (analyse-only, no writes)
python analyze_kg.py                # reads data/kg/imdb_kg_cleaned.ttl
```

### 18 Competency Questions (SPARQL Queries)

Each row reports the fraction of the 376 seed movies for which the corresponding SPARQL query (defined in `QA/qa_extractor.py` and `QA/sparql_queries.txt`) returns at least one answer when executed against `data/kg/imdb_kg_cleaned.ttl`.

| ID | Query | Coverage |
|----|-------|---------:|
| Q1  | Who directed the movie?                 | 100.00% (376/376) |
| Q2  | Who wrote the script?                   | 100.00% (376/376) |
| Q3  | Who are the actors?                     | 100.00% (376/376) |
| Q4  | What is the rating?                     | 100.00% (376/376) |
| Q5  | How many people have rated it?          | 100.00% (376/376) |
| Q6  | What is the plot?                       | 100.00% (376/376) |
| Q7  | When was it released?                   | 100.00% (376/376) |
| Q8  | What is the runtime?                    | 100.00% (376/376) |
| Q9  | What is the Metacritic score?           |  95.21% (358/376) |
| Q10 | What are the keywords?                  | 100.00% (376/376) |
| Q11 | What is the budget?                     |  95.48% (359/376) |
| Q12 | What is the trailer?                    |  99.20% (373/376) |
| Q13 | What is the genre?                      | 100.00% (376/376) |
| Q14 | What is the poster?                     | 100.00% (376/376) |
| Q15 | Which are the production companies?     | 100.00% (376/376) |
| Q16 | What are alternate names?               |  98.94% (372/376) |
| Q17 | What is the content rating?             |  98.40% (370/376) |
| Q18 | Which are the images and their captions?| 100.00% (376/376) |

The per-question precision / recall / F1 against the gold-standard sample (20 movies) live in [QA/evaluation_results.csv](QA/evaluation_results.csv); 12 of the 18 questions reach 100 % exact match on that sample. The genre query reaches 98.6 % recall and 100 % precision (F1 99.3 %) — the IMDb HTML often lists more genres than the JSON-LD block does, and we now recover the missing sub-genres (e.g. *Epic*, *Period Drama*, *Tragic Romance*) by also reading `__NEXT_DATA__.aboveTheFoldData.interests` (see commit `21be9f9`, GitHub issue #1); image-caption recall sits at 86.1 % because some captions are still loaded lazily by the IMDb gallery widget.

---

## 🎯 Applications

IMDB4M enables research across multiple domains:

### 🎥 Movie Recommendation
- Content-based recommendation using visual style of posters and acoustic features of soundtracks
- Extract audio embeddings from linked YouTube videos
- Temporal visual features from trailers for queries like "find movies with high-paced action sequences and electronic scores"

### 🔍 Multimodal Question Answering
- Knowledge Graph Question Answering (KGQA) with perceptual grounding
- Multimodal RAG systems answering "Who is the actor shown in this scene, and what other movies have they directed?"
- Complex queries involving reified relations ("Who played character X in movie Y?")

### 🧩 Multimodal Knowledge Graph Completion
- **Link Prediction**: Infer `schema:genre` from poster and plot using the released image and KG embeddings
- **Entity Alignment**: Cross-platform alignment via visual similarity of actor portraits and `imdb4m:hasEmbedding` pointers
- **KG Embeddings**: Use the released RotatE vectors directly, or fine-tune them with multimodal features (image / video / audio / text) using the held-out variants for a clean evaluation

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📜 License

This project is released under a **Creative Commons Attribution-NonCommercial (CC-BY-NC)** license to ensure alignment with IMDb's terms of use, which restrict data utilisation to academic and non-commercial settings.

IMDB4M functions strictly as a structural indexing layer rather than a media hosting platform. The resource does not store or redistribute any raw multimedia files—only external URIs that reference the original content hosted on IMDb and YouTube.

---

## 📄 Citation

If you use IMDB4M in your research, please cite:

```bibtex
@inproceedings{imdb4m2026,
  title={{IMDB4M}: A Large-Scale Multi-Modal Knowledge Graph of Movies},
  author={Reklos, Ioannis and de Berardinis, Jacopo and Simperl, Elena and Mero{\~n}o-Pe{\~n}uela, Albert},
  year={2026},
  note={Under review}
}
```

The embedding bundle is archived separately on Zenodo and should be cited via its dataset DOI:

```bibtex
@dataset{imdb4m_embeddings_2026,
  title  = {{IMDB4M} Multi-Modal and KG Embeddings (v1)},
  author = {Reklos, Ioannis and de Berardinis, Jacopo and Simperl, Elena and Mero{\~n}o-Pe{\~n}uela, Albert},
  year   = {2026},
  doi    = {10.5281/zenodo.20057840},
  url    = {https://doi.org/10.5281/zenodo.20057840}
}
```

### Comparison with Related Work

| Dataset | Text | Image | Video | Audio | #Entity | #Relation |
|---------|------|-------|-------|-------|---------|-----------|
| MKG-W | 14,123 | 14,463 | – | – | 15,000 | 169 |
| MKG-Y | 12,305 | 14,244 | – | – | 15,000 | 28 |
| TIVA-KG | 11,858 | 11,636 | 10,269 | 2,441 | 11,858 | 16 |
| KVC16K | 14,822 | 14,822 | 14,822 | 14,822 | 16,015 | 4 |
| **IMDB4M** | **392,035** | **34,039** | **3,981** | **4,521** | **656,121** | **58** |

---

## 🙏 Acknowledgments

- **IMDb** for movie metadata
- **Wikidata** for entity linking
- **Schema.org** for vocabulary standards
- **YouTube Data API** for video linking
- **Google Gemini** for intelligent matching

---

<div align="center">

**[⬆ Back to Top](#-imdb4m)**

Made with ❤️ for the Semantic Web community

</div>
