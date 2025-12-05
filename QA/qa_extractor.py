#!/usr/bin/env python3
"""
QA Extractor Script

Loads TTL files from data/sample directory, runs SPARQL queries,
and extracts corresponding answers from locally saved IMDB HTML pages.
Outputs a JSON file comparing TTL-based answers with HTML-based answers.
"""

import os
import re
import json
from pathlib import Path
from rdflib import Graph
from bs4 import BeautifulSoup

# Base paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_SAMPLE_DIR = PROJECT_DIR / "data" / "sample"
QA_DIR = SCRIPT_DIR

# Questions from questions.txt
QUESTIONS = [
    "Who directed the movie?",
    "Who wrote the script for the movie?",
    "Who are the actors of the movie?",
    "What is the rating of the movie?",
    "How many people have rated the movie?",
    "What is the plot of the movie?",
    "When was the movie released?",
    "What is the runtime of the movie?",
    "What is the Metacritic Score of the movie?",
    "What are the keywords associated with the movie?",
    "What is the budget of the movie?",
    "What is the trailer of the movie?",
    "What is the genre of the movie?",
    "What is the poster of the movie?",
    "Which are the production companies of the movie?",
    "What are alternate names of the movie?",
    "What is the content rating of the movie?",
    "Which are the images of the movie and their captions?",
]

# SPARQL queries corresponding to each question
SPARQL_QUERIES = {
    "Who directed the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?directorName
        WHERE {
            ?movie a schema:Movie ;
                   schema:director ?director .
            ?director schema:name ?directorName .
        }
    """,
    "Who wrote the script for the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?writerName
        WHERE {
            ?movie a schema:Movie ;
                   schema:creator ?writer .
            ?writer schema:name ?writerName .
        }
    """,
    "Who are the actors of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?actorName
        WHERE {
            ?movie a schema:Movie ;
                   schema:actor ?actor .
            ?actor schema:name ?actorName .
        }
    """,
    "What is the rating of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?ratingValue
        WHERE {
            ?movie a schema:Movie ;
                   schema:aggregateRating ?rating .
            ?rating a schema:AggregateRating ;
                    schema:ratingValue ?ratingValue .
            FILTER NOT EXISTS { ?rating schema:name "Metacritic Score" }
        }
    """,
    "How many people have rated the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?ratingCount
        WHERE {
            ?movie a schema:Movie ;
                   schema:aggregateRating ?rating .
            ?rating a schema:AggregateRating ;
                    schema:ratingCount ?ratingCount .
        }
    """,
    "What is the plot of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?plot
        WHERE {
            ?movie a schema:Movie ;
                   schema:abstract ?plot .
        }
    """,
    "When was the movie released?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?releaseDate
        WHERE {
            ?movie a schema:Movie ;
                   schema:datePublished ?releaseDate .
        }
    """,
    "What is the runtime of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?duration
        WHERE {
            ?movie a schema:Movie ;
                   schema:duration ?duration .
        }
    """,
    "What is the Metacritic Score of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?metacriticScore
        WHERE {
            ?movie a schema:Movie ;
                   schema:aggregateRating ?rating .
            ?rating schema:name "Metacritic Score" ;
                    schema:ratingValue ?metacriticScore .
        }
    """,
    "What are the keywords associated with the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?keywords
        WHERE {
            ?movie a schema:Movie ;
                   schema:keywords ?keywords .
        }
    """,
    "What is the budget of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?budgetDescription
        WHERE {
            ?movie a schema:Movie ;
                   schema:productionBudget ?budget .
            ?budget schema:description ?budgetDescription .
        }
    """,
    "What is the trailer of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?trailerUrl
        WHERE {
            ?movie a schema:Movie ;
                   schema:trailer ?trailer .
            ?trailer schema:embedUrl ?trailerUrl .
        }
    """,
    "What is the genre of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?genre
        WHERE {
            ?movie a schema:Movie ;
                   schema:genre ?genre .
        }
    """,
    "What is the poster of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?posterUrl
        WHERE {
            ?movie a schema:Movie ;
                   schema:thumbnail ?posterUrl .
        }
    """,
    "Which are the production companies of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?companyName
        WHERE {
            ?movie a schema:Movie ;
                   schema:productionCompany ?company .
            ?company schema:name ?companyName .
        }
    """,
    "What are alternate names of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?alternateName
        WHERE {
            ?movie a schema:Movie ;
                   schema:alternateName ?alternateName .
        }
    """,
    "What is the content rating of the movie?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?contentRating
        WHERE {
            ?movie a schema:Movie ;
                   schema:contentRating ?contentRating .
        }
    """,
    "Which are the images of the movie and their captions?": """
        PREFIX schema: <http://schema.org/>
        SELECT ?imageUrl ?caption
        WHERE {
            ?movie a schema:Movie ;
                   schema:image ?image .
            ?image schema:url ?imageUrl .
            OPTIONAL { ?image schema:caption ?caption }
        }
    """,
}


def get_movie_ids_from_qa():
    """Get list of movie IDs (tt########) from QA directory."""
    movie_ids = []
    for item in os.listdir(QA_DIR):
        if item.startswith("tt") and os.path.isdir(QA_DIR / item):
            movie_ids.append(item)
    return sorted(movie_ids)


def load_ttl_graph(movie_id: str) -> Graph:
    """Load TTL file for a movie into an RDF graph."""
    ttl_path = DATA_SAMPLE_DIR / movie_id / "movie_html" / f"{movie_id}.ttl"
    if not ttl_path.exists():
        raise FileNotFoundError(f"TTL file not found: {ttl_path}")
    
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    return g


def run_sparql_query(graph: Graph, query: str) -> list:
    """Run a SPARQL query and return results as a list."""
    results = []
    for row in graph.query(query):
        # Convert row to list of string values
        row_values = [str(val) for val in row if val is not None]
        if len(row_values) == 1:
            results.append(row_values[0])
        elif len(row_values) > 1:
            results.append(row_values)
    return results


def extract_from_ttl(movie_id: str) -> dict:
    """Extract answers from TTL file using SPARQL queries."""
    graph = load_ttl_graph(movie_id)
    answers = {}
    
    for question, query in SPARQL_QUERIES.items():
        results = run_sparql_query(graph, query)
        answers[question] = results
    
    return answers


def load_local_html(movie_id: str) -> tuple:
    """Load local IMDB HTML file and return soup, JSON-LD data, and __NEXT_DATA__."""
    html_path = QA_DIR / movie_id / "movie_html" / f"{movie_id}.html"
    
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract JSON-LD data
    json_ld = {}
    script = soup.find('script', type='application/ld+json')
    if script and script.string:
        try:
            json_ld = json.loads(script.string)
        except json.JSONDecodeError:
            pass
    
    # Extract __NEXT_DATA__ (Next.js server-side data)
    next_data = {}
    next_script = soup.find('script', id='__NEXT_DATA__')
    if next_script and next_script.string:
        try:
            next_data = json.loads(next_script.string)
        except json.JSONDecodeError:
            pass
    
    return soup, json_ld, next_data


def extract_from_html(movie_id: str) -> dict:
    """Extract answers from locally saved IMDB HTML file using __NEXT_DATA__ and JSON-LD."""
    answers = {q: [] for q in QUESTIONS}
    
    try:
        soup, json_ld, next_data = load_local_html(movie_id)
    except Exception as e:
        print(f"    Error loading HTML file: {e}")
        return answers
    
    # Extract page props from __NEXT_DATA__
    page_props = next_data.get('props', {}).get('pageProps', {})
    atf = page_props.get('aboveTheFoldData', {})  # Above the fold data
    mcd = page_props.get('mainColumnData', {})    # Main column data
    
    # Q1: Director - from __NEXT_DATA__ crewV2
    try:
        crew_list = mcd.get('crewV2', [])
        directors = []
        for crew_group in crew_list:
            role = crew_group.get('grouping', {}).get('text', '')
            if 'Director' in role:
                for credit in crew_group.get('credits', []):
                    name = credit.get('name', {}).get('nameText', {}).get('text', '')
                    if name:
                        directors.append(name)
        answers["Who directed the movie?"] = directors
    except Exception:
        pass
    
    # Q2: Writer - from __NEXT_DATA__ crewV2
    try:
        crew_list = mcd.get('crewV2', [])
        writers = []
        for crew_group in crew_list:
            role = crew_group.get('grouping', {}).get('text', '')
            if 'Writer' in role:
                for credit in crew_group.get('credits', []):
                    name = credit.get('name', {}).get('nameText', {}).get('text', '')
                    if name:
                        writers.append(name)
        answers["Who wrote the script for the movie?"] = writers
    except Exception:
        pass
    
    # Q3: Actors - from __NEXT_DATA__ castV2
    try:
        cast_list = mcd.get('castV2', [])
        actors = []
        for cast_group in cast_list:
            for credit in cast_group.get('credits', []):
                name = credit.get('name', {}).get('nameText', {}).get('text', '')
                if name:
                    actors.append(name)
        answers["Who are the actors of the movie?"] = actors
    except Exception:
        pass
    
    # Q4: Rating - from __NEXT_DATA__
    try:
        ratings = atf.get('ratingsSummary', {})
        rating = ratings.get('aggregateRating')
        answers["What is the rating of the movie?"] = [str(rating)] if rating else []
    except Exception:
        pass
    
    # Q5: Rating count - from __NEXT_DATA__
    try:
        ratings = atf.get('ratingsSummary', {})
        count = ratings.get('voteCount')
        answers["How many people have rated the movie?"] = [str(count)] if count else []
    except Exception:
        pass
    
    # Q6: Plot - from __NEXT_DATA__
    try:
        plot = atf.get('plot', {}).get('plotText', {}).get('plainText', '')
        answers["What is the plot of the movie?"] = [plot] if plot else []
    except Exception:
        pass
    
    # Q7: Release date - from __NEXT_DATA__
    try:
        release = atf.get('releaseDate', {})
        if release:
            year = release.get('year', '')
            month = release.get('month', '')
            day = release.get('day', '')
            if year and month and day:
                date_str = f"{year}-{month:02d}-{day:02d}"
            elif year:
                date_str = str(year)
            else:
                date_str = ''
            answers["When was the movie released?"] = [date_str] if date_str else []
    except Exception:
        pass
    
    # Q8: Runtime - from __NEXT_DATA__
    try:
        runtime = atf.get('runtime', {})
        if runtime:
            seconds = runtime.get('seconds', 0)
            if seconds:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                duration_str = f"PT{hours}H{minutes}M" if hours else f"PT{minutes}M"
                answers["What is the runtime of the movie?"] = [duration_str]
    except Exception:
        pass
    
    # Q9: Metacritic Score - from __NEXT_DATA__
    try:
        metacritic = atf.get('metacritic', {})
        score = metacritic.get('metascore', {}).get('score')
        answers["What is the Metacritic Score of the movie?"] = [str(score)] if score else []
    except Exception:
        pass
    
    # Q10: Keywords - from __NEXT_DATA__
    try:
        keywords_data = atf.get('keywords', {})
        edges = keywords_data.get('edges', [])
        keywords = [edge.get('node', {}).get('text', '') for edge in edges]
        keywords = [k for k in keywords if k]
        answers["What are the keywords associated with the movie?"] = keywords
    except Exception:
        pass
    
    # Q11: Budget - from __NEXT_DATA__
    try:
        budget_data = mcd.get('productionBudget', {})
        budget = budget_data.get('budget', {})
        amount = budget.get('amount')
        currency = budget.get('currency', 'USD')
        if amount:
            # Format as currency string
            budget_str = f"${amount:,} (estimated)" if currency == 'USD' else f"{amount:,} {currency} (estimated)"
            answers["What is the budget of the movie?"] = [budget_str]
    except Exception:
        pass
    
    # Q12: Trailer - from __NEXT_DATA__ or JSON-LD
    try:
        # Try __NEXT_DATA__ videoStrip first
        video_strip = mcd.get('videoStrip', {})
        edges = video_strip.get('edges', [])
        if edges:
            # Get first video (usually the trailer)
            video_id = edges[0].get('node', {}).get('id', '')
            if video_id:
                trailer_url = f"https://www.imdb.com/video/{video_id}/"
                answers["What is the trailer of the movie?"] = [trailer_url]
        # Fallback to JSON-LD
        if not answers["What is the trailer of the movie?"]:
            trailer = json_ld.get('trailer', {})
            if isinstance(trailer, dict):
                trailer_url = trailer.get('embedUrl') or trailer.get('url')
                if trailer_url:
                    answers["What is the trailer of the movie?"] = [trailer_url]
    except Exception:
        pass
    
    # Q13: Genre - from __NEXT_DATA__
    try:
        genres_data = atf.get('genres', {}).get('genres', [])
        genres = [g.get('text', '') for g in genres_data]
        genres = [g for g in genres if g]
        answers["What is the genre of the movie?"] = genres
    except Exception:
        pass
    
    # Q14: Poster - from __NEXT_DATA__
    try:
        primary_image = atf.get('primaryImage', {})
        poster_url = primary_image.get('url', '')
        answers["What is the poster of the movie?"] = [poster_url] if poster_url else []
    except Exception:
        pass
    
    # Q15: Production companies - from __NEXT_DATA__
    try:
        production = atf.get('production', {})
        edges = production.get('edges', [])
        companies = []
        for edge in edges:
            company_text = edge.get('node', {}).get('company', {}).get('companyText', {}).get('text', '')
            if company_text:
                companies.append(company_text)
        answers["Which are the production companies of the movie?"] = companies
    except Exception:
        pass
    
    # Q16: Alternate names - from __NEXT_DATA__
    try:
        akas = mcd.get('akas', {})
        edges = akas.get('edges', [])
        alt_names = [edge.get('node', {}).get('text', '') for edge in edges]
        alt_names = [n for n in alt_names if n]
        answers["What are alternate names of the movie?"] = alt_names
    except Exception:
        pass
    
    # Q17: Content rating - from __NEXT_DATA__
    try:
        certificate = atf.get('certificate', {})
        rating = certificate.get('rating', '')
        answers["What is the content rating of the movie?"] = [rating] if rating else []
    except Exception:
        pass
    
    # Q18: Images and captions - from __NEXT_DATA__
    try:
        images_data = mcd.get('titleMainImages', {})
        edges = images_data.get('edges', [])
        images = []
        for edge in edges:
            node = edge.get('node', {})
            url = node.get('url', '')
            caption = node.get('caption', {}).get('plainText', '')
            if url:
                images.append([url, caption] if caption else [url])
        answers["Which are the images of the movie and their captions?"] = images
    except Exception:
        pass
    
    return answers


def main():
    """Main function to process all movies and generate QA JSON."""
    movie_ids = get_movie_ids_from_qa()
    print(f"Found {len(movie_ids)} movies in QA directory")
    
    all_results = {}
    
    for i, movie_id in enumerate(movie_ids):
        print(f"\n[{i+1}/{len(movie_ids)}] Processing {movie_id}...")
        movie_results = {}
        
        # Extract from TTL
        try:
            print(f"  Loading TTL file...")
            ttl_answers = extract_from_ttl(movie_id)
        except Exception as e:
            print(f"  Error loading TTL: {e}")
            ttl_answers = {q: [] for q in QUESTIONS}
        
        # Extract from HTML (local file)
        try:
            print(f"  Loading local HTML file...")
            html_answers = extract_from_html(movie_id)
        except Exception as e:
            print(f"  Error loading HTML: {e}")
            html_answers = {q: [] for q in QUESTIONS}
        
        # Combine results for this movie
        for question in QUESTIONS:
            movie_results[question] = {
                "ttl": ttl_answers.get(question, []),
                "html": html_answers.get(question, [])
            }
        
        all_results[movie_id] = movie_results
        print(f"  Done!")
    
    # Save results to JSON
    output_path = QA_DIR / "qa_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to {output_path}")
    return all_results


if __name__ == "__main__":
    main()
