<div align="center">

# 🎬 IMDB4M

### A Large-Scale Multi-Modal Knowledge Graph of Movies

[![ESWC 2026](https://img.shields.io/badge/ESWC-2026-blueviolet?style=for-the-badge)](https://2026.eswc-conferences.org/)
[![Resource Track](https://img.shields.io/badge/Resource-Track-orange?style=for-the-badge)]()
[![RDF](https://img.shields.io/badge/RDF-Turtle-00ADD8?style=for-the-badge&logo=semantic-web)](https://www.w3.org/TR/turtle/)
[![Schema.org](https://img.shields.io/badge/Schema.org-Vocabulary-red?style=for-the-badge)](https://schema.org/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

<p align="center">
  <strong>A comprehensive RDF knowledge graph combining movie metadata, soundtracks, videos, images, and reviews from IMDb</strong>
</p>

[Overview](#-overview) •
[Features](#-features) •
[Knowledge Graph Schema](#-knowledge-graph-schema) •
[Installation](#-installation) •
[Usage](#-usage) •
[Evaluation](#-evaluation) •
[Citation](#-citation)

</div>

---

## 📖 Overview

**IMDB4M** (IMDb Multi-Modal Movie Metadata) is a large-scale knowledge graph resource that captures rich, multi-modal information about movies from the Internet Movie Database (IMDb). This resource was developed for submission to the **International Semantic Web Conference (ESWC) 2026 Resource Track**.

The knowledge graph integrates:
- 🎥 **Movie Metadata**: Titles, plots, genres, ratings, release dates, production companies
- 🎭 **Cast & Crew**: Actors, directors, writers with their complete filmographies
- 🎵 **Soundtracks**: Music recordings, compositions, performers, composers, lyricists
- 📹 **Videos**: Movie trailers with thumbnails, duration, and upload dates
- 🖼️ **Images**: Movie stills and promotional images with captions
- ⭐ **Reviews & Ratings**: User reviews, aggregate ratings, Metacritic scores
- 🔗 **External Links**: Wikidata entity alignments via `owl:sameAs` mappings

---

## ✨ Features

### 🗃️ Multi-Modal Data Integration
| Modality | Description | Schema.org Types |
|----------|-------------|------------------|
| **Textual** | Plots, reviews, keywords, captions | `schema:abstract`, `schema:Review` |
| **Visual** | Movie stills, posters | `schema:ImageObject` |
| **Video** | Movie trailers, clips | `schema:VideoObject` |
| **Audio** | Soundtrack metadata | `schema:MusicRecording`, `schema:MusicComposition` |
| **Structural** | Entity relationships | `schema:Person`, `schema:Movie`, `schema:Organization` |

### 📊 Knowledge Graph Statistics

| Metric | Value |
|--------|-------|
| Movies | 379+ |
| Actors/Crew | 1000+ |
| Soundtracks | 379+ movies with audio metadata |
| Videos/Trailers | Multiple per movie |
| Images | Multiple per movie with captions |
| RDF Triples | 100,000+ |
| Predicates | 40+ Schema.org properties |

### 🔗 External Linkage
- **Wikidata Integration**: `owl:sameAs` mappings for movies and actors
- **YouTube Links**: Soundtrack-to-video linking via intelligent matching

---

## 🏗️ Knowledge Graph Schema

IMDB4M uses [Schema.org](https://schema.org/) vocabulary as its primary ontology. Below is a simplified view of the schema:

```
                          ┌─────────────────┐
                          │  schema:Movie   │
                          └────────┬────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────┐
    │              │               │               │              │
    ▼              ▼               ▼               ▼              ▼
┌────────┐  ┌───────────┐  ┌────────────┐  ┌───────────┐  ┌────────┐
│ Person │  │ImageObject│  │VideoObject │  │  Review   │  │ Audio  │
│(Actors)│  │ (Stills)  │  │ (Trailers) │  │(Ratings)  │  │(Music) │
└────────┘  └───────────┘  └────────────┘  └───────────┘  └────────┘
    │                                                          │
    │                                                          ▼
    │                                          ┌───────────────────────┐
    │                                          │ schema:MusicRecording │
    │                                          └───────────┬───────────┘
    │                                                      │
    │                                                      ▼
    │                                          ┌───────────────────────┐
    │                                          │schema:MusicComposition│
    │                                          └───────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ schema:performerIn      │
│ (Actor Filmographies)   │
└─────────────────────────┘
```

### Key Properties

| Property | Domain | Range | Description |
|----------|--------|-------|-------------|
| `schema:actor` | Movie | Person | Cast member |
| `schema:director` | Movie | Person | Film director |
| `schema:trailer` | Movie | VideoObject | Movie trailer |
| `schema:audio` | Movie | MusicRecording | Soundtrack entry |
| `schema:image` | Movie | ImageObject | Movie still/poster |
| `schema:aggregateRating` | Movie | AggregateRating | IMDb/Metacritic score |
| `schema:review` | Movie | Review | User review |
| `schema:byArtist` | MusicRecording | Person | Performer |
| `schema:composer` | MusicComposition | Person | Music composer |
| `schema:caption` | ImageObject | Text | Image description |
| `schema:embedUrl` | VideoObject | URL | Trailer embed URL |
| `schema:thumbnailUrl` | VideoObject | URL | Trailer thumbnail |
| `schema:duration` | VideoObject | Duration | Video length |
| `owl:sameAs` | Entity | WikidataURI | External link |

---

## 📁 Repository Structure

```
imdb4m/
├── 📂 data/
│   ├── 📂 movies/                   # Movie data organized by IMDb ID
│   │   └── 📂 tt0120338/           # Example: Titanic
│   │       ├── 📂 movie_html/      # Parsed movie metadata (.ttl)
│   │       └── 📂 movie_soundtrack/ # Soundtrack metadata (.ttl, .json)
│   ├── 📂 kg/                       # Consolidated knowledge graph
│   │   ├── imdb_kg_cleaned.ttl     # Main KG file
│   │   └── sameas_mappings.ttl     # Wikidata alignments
│   └── 📂 sample/                   # Sample subset for testing
│
├── 📂 linker/                       # Music Linker module
│   ├── models.py                   # Pydantic data models
│   ├── youtube_client.py           # YouTube API integration
│   ├── gemini_matcher.py           # LLM-powered matching
│   └── music_linker.py             # Main orchestrator
│
├── 📂 scraper/                      # Data collection scripts
│   ├── download_imdb_movie.py      # Movie page scraper
│   ├── download_imdb_actor.py      # Actor page scraper
│   └── 📂 movie_seeds/             # Movie selection criteria
│
├── 📂 QA/                           # Quality assurance
│   ├── QA_gold.json                # Gold standard annotations
│   ├── qa_kg.json                  # KG-derived answers
│   └── evaluate_qa.py              # Evaluation metrics
│
├── 📜 parse_imdb_movie.py          # HTML → RDF parser (movies)
├── 📜 parse_imdb_actor.py          # HTML → RDF parser (actors)
├── 📜 parse_soundtrack_to_ttl.py   # Soundtrack → RDF parser
├── 📜 analyze_kg.py                # KG statistics & analysis
├── 📜 create_sameas_mappings.py    # Wikidata linking
└── 📜 requirements.txt             # Python dependencies
```

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

```python
from rdflib import Graph

# Load the main knowledge graph
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

### Music Linker

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

# Find YouTube matches
results = linker.find_matches_batch(soundtracks)

for result in results:
    if result.best_match:
        print(f"🎵 {result.soundtrack.title}: {result.best_match.url}")
```

---

## 📊 Evaluation

IMDB4M includes a comprehensive Question-Answering (QA) evaluation framework to assess the completeness and accuracy of the knowledge graph.

### Running Evaluation

```bash
cd QA
python evaluate_qa.py
```

### Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Precision** | Correct answers / Predicted answers |
| **Recall** | Correct answers / Gold standard answers |
| **F1 Score** | Harmonic mean of Precision and Recall |
| **Levenshtein Similarity** | String-based fuzzy matching |
| **Exact Match Rate** | Percentage of perfect matches |

### Sample Questions Evaluated

- Who directed the movie?
- Who are the actors in the movie?
- What is the rating of the movie?
- What is the plot of the movie?
- What are the soundtracks of the movie?
- What is the trailer of the movie?
- Which are the images and their captions?

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

IMDB4M includes `owl:sameAs` mappings to Wikidata for enhanced interoperability:

```turtle
<https://www.imdb.com/title/tt0120338> owl:sameAs <http://www.wikidata.org/entity/Q44578> .
<https://www.imdb.com/name/nm0000138> owl:sameAs <http://www.wikidata.org/entity/Q38111> .
```

Generate mappings:
```bash
python create_sameas_mappings.py
```

---

## 📈 Knowledge Graph Analysis

```bash
# Run comprehensive KG analysis
python analyze_kg.py
```

This generates:
- Triple counts and distribution
- Node degree statistics
- Connected component analysis
- Predicate frequency analysis
- Entity type distribution
- Orphan movie detection and cleanup

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

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 📄 Citation

If you use IMDB4M in your research, please cite:

```bibtex
@inproceedings{imdb4m2026,
  title={IMDB4M: A Large-Scale Multi-Modal Knowledge Graph of Movies},
  author={[Authors]},
  booktitle={Extended Semantic Web Conference (ESWC) - Resource Track},
  year={2026}
}
```

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
