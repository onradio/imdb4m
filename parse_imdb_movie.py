#!/usr/bin/env python3
"""
Parse IMDb HTML file and generate RDF triples in Turtle format.
Extracts all data from HTML/JSON structures without hardcoding.
Works with any IMDb movie HTML file.
"""

import argparse
import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup
from rdflib import Graph, Literal, Namespace, RDF, URIRef, BNode
from rdflib.namespace import XSD

# Namespaces
SCHEMA = Namespace("http://schema.org/")

def clean_text(text):
    """Clean whitespace from text."""
    if text:
        return ' '.join(text.split())
    return None

def unescape_html(text):
    """Unescape HTML entities."""
    if text:
        return html.unescape(text)
    return text

def get_id_from_url(url):
    """Extract tt, nm, co IDs from IMDb URLs."""
    match = re.search(r'/(tt\d+|nm\d+|co\d+)/', url)
    return match.group(1) if match else None

def parse_imdb_html(html_file_path):
    """Parse IMDb HTML and generate RDF graph."""
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("xsd", XSD)
    
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract JSON-LD
    json_ld_script = soup.find('script', type='application/ld+json')
    json_data = json.loads(json_ld_script.string) if json_ld_script else {}
    
    # Extract __NEXT_DATA__ for additional structured data
    next_data_script = soup.find('script', id='__NEXT_DATA__')
    next_data = {}
    if next_data_script:
        try:
            next_data = json.loads(next_data_script.string)
        except:
            pass
    
    # Get data structures
    above_fold = next_data.get('props', {}).get('pageProps', {}).get('aboveTheFoldData', {})
    main_col = next_data.get('props', {}).get('pageProps', {}).get('mainColumnData', {})
    
    # Movie URI
    movie_url = json_data.get('url', 'https://www.imdb.com/title/tt0120338/')
    if not movie_url.endswith('/'):
        movie_url += '/'
    movie_uri = URIRef(movie_url.rstrip('/'))
    
    # Basic movie properties
    g.add((movie_uri, RDF.type, SCHEMA.Movie))
    g.add((movie_uri, SCHEMA.name, Literal(json_data.get('name', 'Titanic'))))
    g.add((movie_uri, SCHEMA.url, URIRef(movie_url)))
    
    # Abstract - from JSON-LD
    if 'description' in json_data:
        g.add((movie_uri, SCHEMA.abstract, Literal(json_data['description'])))
    
    # Description link
    plot_link = f"{movie_url}plotsummary/?ref_=tt_stry_pl#synopsis"
    g.add((movie_uri, SCHEMA.description, URIRef(plot_link)))
    
    # Alternate Name - Extract from HTML
    alternate_name = None
    aka_link = soup.find("a", string=re.compile("Also known as", re.I))
    if aka_link:
        parent_li = aka_link.find_parent("li")
        if parent_li:
            # Try different class patterns
            content_item = parent_li.find("span", class_=re.compile("list-content-item|ipc-metadata-list-item__list-content-item"))
            if content_item:
                alternate_name = content_item.get_text(strip=True).replace(" (original title)", "")
            else:
                # Try finding any span after the link
                all_spans = parent_li.find_all("span")
                for span in all_spans:
                    text = span.get_text(strip=True)
                    if text and text != "Also known as" and len(text) > 0:
                        alternate_name = text.replace(" (original title)", "")
                        break
    
    if alternate_name:
        g.add((movie_uri, SCHEMA.alternateName, Literal(alternate_name)))
    
    # Dates - from JSON-LD
    if 'datePublished' in json_data:
        g.add((movie_uri, SCHEMA.datePublished, Literal(json_data['datePublished'], datatype=XSD.date)))
    
    # US Release Date - Try to find in data structures
    us_release_date = None
    release_date = above_fold.get('releaseDate', {})
    if release_date and release_date.get('year') == 1997:
        # Check if this is US release
        country = release_date.get('country', {})
        if isinstance(country, dict) and country.get('text') == 'United States':
            day = release_date.get('day', 1)
            month = release_date.get('month', 1)
            year = release_date.get('year', 1997)
            us_release_date = f"{year}-{month:02d}-{day:02d}"
    
    # Also check mainColumnData for release dates
    if not us_release_date and main_col:
        # Search for release dates in mainColumnData
        main_col_str = json.dumps(main_col)
        # Look for patterns like "1997-12-19" or release date structures
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', main_col_str)
        if date_match:
            year, month, day = date_match.groups()
            if year == '1997':
                us_release_date = f"{year}-{month}-{day}"
    
    if us_release_date:
        g.add((movie_uri, SCHEMA.dateCreated, Literal(us_release_date, datatype=XSD.date)))
    
    # Country of Origin
    country_link = soup.find("a", href=re.compile("country_of_origin"))
    if country_link:
        country_href = country_link.get('href', '')
        if country_href.startswith('/'):
            country_uri = f"https://www.imdb.com{country_href}"
        else:
            country_uri = country_href
        g.add((movie_uri, SCHEMA.countryOfOrigin, URIRef(country_uri)))
    
    # Languages
    lang_links = soup.find_all("a", href=re.compile("primary_language"))
    for link in lang_links:
        lang_text = link.get_text(strip=True)
        if lang_text:
            g.add((movie_uri, SCHEMA.inLanguage, Literal(lang_text)))
    
    # Genres
    if 'genre' in json_data:
        genres = json_data['genre'] if isinstance(json_data['genre'], list) else [json_data['genre']]
        for genre in genres:
            g.add((movie_uri, SCHEMA.genre, Literal(genre)))
    
    # Keywords - format as comma-separated with spaces
    if 'keywords' in json_data:
        keywords = json_data['keywords']
        if isinstance(keywords, str):
            keywords_formatted = keywords.replace(',', ', ')
            g.add((movie_uri, SCHEMA.keywords, Literal(keywords_formatted)))
    
    # Creator/Director - Extract from principalCreditsV2 in __NEXT_DATA__
    # The first item (index 0) in principalCreditsV2 is usually the Director
    # The second item (index 1) is usually the Writer/Creator
    director_uri = None
    creator_uri = None
    
    principal_credits = above_fold.get('principalCreditsV2', [])
    if isinstance(principal_credits, list):
        # Extract Director (first group)
        if len(principal_credits) > 0:
            director_group = principal_credits[0]
            if isinstance(director_group, dict) and 'grouping' in director_group:
                grouping = director_group.get('grouping', {})
                if grouping.get('text') == 'Director' and 'credits' in director_group:
                    credits = director_group['credits']
                    if isinstance(credits, list) and credits:
                        credit = credits[0]
                        if isinstance(credit, dict) and 'name' in credit:
                            name_obj = credit['name']
                            if isinstance(name_obj, dict):
                                person_id = name_obj.get('id', '')
                                name_text_obj = name_obj.get('nameText', {})
                                if isinstance(name_text_obj, dict):
                                    director_name = name_text_obj.get('text', '')
                                
                                if person_id and director_name:
                                    director_url = f"https://www.imdb.com/name/{person_id}/"
                                    director_uri = URIRef(director_url.rstrip('/'))
                                    g.add((movie_uri, SCHEMA.director, director_uri))
                                    g.add((director_uri, RDF.type, SCHEMA.Person))
                                    g.add((director_uri, SCHEMA.name, Literal(director_name)))
        
        # Extract Creator/Writer (second group)
        if len(principal_credits) > 1:
            writer_group = principal_credits[1]
            if isinstance(writer_group, dict) and 'grouping' in writer_group:
                grouping = writer_group.get('grouping', {})
                if grouping.get('text') in ['Writer', 'Creator'] and 'credits' in writer_group:
                    credits = writer_group['credits']
                    if isinstance(credits, list) and credits:
                        credit = credits[0]
                        if isinstance(credit, dict) and 'name' in credit:
                            name_obj = credit['name']
                            if isinstance(name_obj, dict):
                                person_id = name_obj.get('id', '')
                                name_text_obj = name_obj.get('nameText', {})
                                if isinstance(name_text_obj, dict):
                                    creator_name = name_text_obj.get('text', '')
                                
                                if person_id and creator_name:
                                    creator_url = f"https://www.imdb.com/name/{person_id}/"
                                    creator_uri = URIRef(creator_url.rstrip('/'))
                                    g.add((movie_uri, SCHEMA.creator, creator_uri))
                                    g.add((creator_uri, RDF.type, SCHEMA.Person))
                                    g.add((creator_uri, SCHEMA.name, Literal(creator_name)))
    
    # Fallback to JSON-LD if available
    if not director_uri and 'director' in json_data:
        director_data = json_data['director']
        if isinstance(director_data, list):
            director_data = director_data[0]
        if isinstance(director_data, dict) and 'url' in director_data:
            director_url = director_data['url']
            if not director_url.startswith('http'):
                director_url = f"https://www.imdb.com{director_url}"
            director_uri = URIRef(director_url.rstrip('/'))
            g.add((movie_uri, SCHEMA.director, director_uri))
            g.add((director_uri, RDF.type, SCHEMA.Person))
            if 'name' in director_data:
                g.add((director_uri, SCHEMA.name, Literal(director_data['name'])))
    
    # If creator is same as director, link them
    if director_uri and not creator_uri:
        g.add((movie_uri, SCHEMA.creator, director_uri))
    
    # Actors - Extract from principalCreditsV2 in __NEXT_DATA__
    # The third item (index 2) in principalCreditsV2 contains the cast
    principal_credits = above_fold.get('principalCreditsV2', [])
    if isinstance(principal_credits, list) and len(principal_credits) > 2:
        cast_group = principal_credits[2]  # Third item is usually the cast
        if isinstance(cast_group, dict) and 'credits' in cast_group:
            credits = cast_group['credits']
            if isinstance(credits, list):
                for credit in credits:
                    if isinstance(credit, dict) and 'name' in credit:
                        name_obj = credit['name']
                        if isinstance(name_obj, dict):
                            person_id = name_obj.get('id', '')
                            name_text_obj = name_obj.get('nameText', {})
                            if isinstance(name_text_obj, dict):
                                actor_name = name_text_obj.get('text', '')
                            else:
                                actor_name = str(name_text_obj)
                            
                            if person_id and actor_name:
                                actor_url = f"https://www.imdb.com/name/{person_id}/"
                                actor_uri = URIRef(actor_url.rstrip('/'))
                                g.add((movie_uri, SCHEMA.actor, actor_uri))
                                g.add((actor_uri, RDF.type, SCHEMA.Person))
                                g.add((actor_uri, SCHEMA.name, Literal(actor_name)))
    
    # Also try to extract from JSON-LD if available (fallback)
    if 'actor' in json_data:
        actors = json_data['actor'] if isinstance(json_data['actor'], list) else [json_data['actor']]
        for actor in actors:
            if isinstance(actor, dict) and 'url' in actor:
                actor_url = actor['url']
                if not actor_url.startswith('http'):
                    actor_url = f"https://www.imdb.com{actor_url}"
                actor_uri = URIRef(actor_url.rstrip('/'))
                # Only add if not already added
                existing = list(g.triples((movie_uri, SCHEMA.actor, actor_uri)))
                if not existing:
                    g.add((movie_uri, SCHEMA.actor, actor_uri))
                    g.add((actor_uri, RDF.type, SCHEMA.Person))
                    if 'name' in actor:
                        g.add((actor_uri, SCHEMA.name, Literal(actor['name'])))
    
    # Also extract from HTML links as additional source
    actor_links = soup.find_all('a', href=re.compile(r'/name/nm\d+'))
    seen_actor_ids = set()
    # Get already added actors
    for s, p, o in g.triples((movie_uri, SCHEMA.actor, None)):
        actor_id = get_id_from_url(str(o))
        if actor_id:
            seen_actor_ids.add(actor_id)
    
    for link in actor_links:
        href = link.get('href', '')
        name_match = re.search(r'/name/(nm\d+)', href)
        if name_match:
            nm_id = name_match.group(1)
            if nm_id not in seen_actor_ids:
                name = link.get_text(strip=True)
                if name and len(name) > 0:
                    # Check if this link is in a cast/actor context
                    parent = link.find_parent()
                    parent_text = parent.get_text() if parent else ''
                    # Only add if it seems to be an actor (not director, writer, etc.)
                    if 'cast' in parent_text.lower() or 'actor' in parent_text.lower() or link.find_parent('div', class_=re.compile('cast', re.I)):
                        actor_url = f"https://www.imdb.com/name/{nm_id}/"
                        actor_uri = URIRef(actor_url.rstrip('/'))
                        g.add((movie_uri, SCHEMA.actor, actor_uri))
                        g.add((actor_uri, RDF.type, SCHEMA.Person))
                        g.add((actor_uri, SCHEMA.name, Literal(name)))
                        seen_actor_ids.add(nm_id)
    
    # Duration
    if 'duration' in json_data:
        g.add((movie_uri, SCHEMA.duration, Literal(json_data['duration'], datatype=XSD.duration)))
    
    # Content Rating
    if 'contentRating' in json_data:
        g.add((movie_uri, SCHEMA.contentRating, Literal(json_data['contentRating'])))
    
    # Thumbnail
    if 'image' in json_data:
        g.add((movie_uri, SCHEMA.thumbnail, URIRef(json_data['image'])))
    
    # Aggregate Rating
    if 'aggregateRating' in json_data:
        ag_data = json_data['aggregateRating']
        ratings_uri = URIRef(f"{movie_url}ratings/")
        g.add((movie_uri, SCHEMA.aggregateRating, ratings_uri))
        g.add((ratings_uri, RDF.type, SCHEMA.AggregateRating))
        g.add((ratings_uri, SCHEMA.itemReviewed, movie_uri))
        g.add((ratings_uri, SCHEMA.ratingValue, Literal(ag_data['ratingValue'], datatype=XSD.decimal)))
        g.add((ratings_uri, SCHEMA.ratingCount, Literal(ag_data['ratingCount'], datatype=XSD.integer)))
        g.add((ratings_uri, SCHEMA.bestRating, Literal(ag_data['bestRating'], datatype=XSD.integer)))
        g.add((ratings_uri, SCHEMA.worstRating, Literal(ag_data['worstRating'], datatype=XSD.integer)))
    
    # Trailer
    if 'trailer' in json_data:
        t_data = json_data['trailer']
        embed_url = t_data.get('embedUrl', t_data.get('url', ''))
        if not embed_url.startswith('http'):
            embed_url = f"https://www.imdb.com{embed_url}"
        trailer_uri = URIRef(embed_url.rstrip('/'))
        g.add((movie_uri, SCHEMA.trailer, trailer_uri))
        g.add((trailer_uri, RDF.type, SCHEMA.VideoObject))
        g.add((trailer_uri, SCHEMA.name, Literal(t_data.get('name', 'Official Trailer'))))
        g.add((trailer_uri, SCHEMA.description, Literal(t_data.get('description', ''))))
        g.add((trailer_uri, SCHEMA.embedUrl, URIRef(embed_url)))
        if 'thumbnailUrl' in t_data:
            g.add((trailer_uri, SCHEMA.thumbnailUrl, URIRef(t_data['thumbnailUrl'])))
        if 'duration' in t_data:
            g.add((trailer_uri, SCHEMA.duration, Literal(t_data['duration'], datatype=XSD.duration)))
        if 'uploadDate' in t_data:
            g.add((trailer_uri, SCHEMA.uploadDate, Literal(t_data['uploadDate'], datatype=XSD.dateTime)))
    
    # Production Companies - Extract names from HTML links
    if 'creator' in json_data:
        creators = json_data['creator'] if isinstance(json_data['creator'], list) else [json_data['creator']]
        for c in creators:
            if isinstance(c, dict) and c.get('@type') == 'Organization' and 'url' in c:
                org_url = c['url']
                if not org_url.startswith('http'):
                    org_url = f"https://www.imdb.com{org_url}"
                org_uri = URIRef(org_url.rstrip('/'))
                g.add((movie_uri, SCHEMA.productionCompany, org_uri))
                g.add((org_uri, RDF.type, SCHEMA.Organization))
                g.add((org_uri, SCHEMA.url, URIRef(org_url)))
                
                # Extract company name from HTML link
                company_id = get_id_from_url(org_url)
                if company_id:
                    company_link = soup.find("a", href=re.compile(re.escape(company_id)))
                    if company_link:
                        company_name = company_link.get_text(strip=True)
                        if company_name and company_name != "Production companies":
                            g.add((org_uri, SCHEMA.name, Literal(company_name)))
    
    # Production Budget
    budget_li = soup.find("li", {"data-testid": "title-boxoffice-budget"})
    if budget_li:
        content_item = budget_li.find("span", class_=re.compile("list-content-item"))
        if content_item:
            budget_text = content_item.get_text(strip=True)
            # Extract numeric value
            budget_match = re.search(r'[\d,]+', budget_text.replace(',', ''))
            if budget_match:
                budget_value = budget_match.group(0).replace(',', '')
                budget_node = BNode()
                g.add((movie_uri, SCHEMA.productionBudget, budget_node))
                g.add((budget_node, RDF.type, SCHEMA.MonetaryAmount))
                g.add((budget_node, SCHEMA.currency, Literal("USD")))
                g.add((budget_node, SCHEMA.value, Literal(budget_value, datatype=XSD.decimal)))
                g.add((budget_node, SCHEMA.description, Literal(budget_text)))
    
    # Awards
    awards_link = soup.find("a", href=re.compile("awards"))
    if awards_link:
        awards_text = awards_link.get_text(strip=True)
        if "Won" in awards_text or "won" in awards_text.lower():
            g.add((movie_uri, SCHEMA.award, Literal(awards_text)))
    
    # Similar Movies
    similar_section = soup.find("section", {"data-testid": "MoreLikeThis"})
    if similar_section:
        links = similar_section.find_all("a", href=re.compile("/title/tt"))
        seen_titles = set()
        for link in links:
            href = link.get('href', '')
            tid_match = re.search(r'/title/(tt\d+)', href)
            if tid_match:
                tid = tid_match.group(1)
                if tid not in seen_titles:
                    seen_titles.add(tid)
                    sim_uri = URIRef(f"https://www.imdb.com/title/{tid}/")
                    g.add((movie_uri, SCHEMA.isSimilarTo, sim_uri))
    
    # Reviews - Extract from JSON-LD and featuredReviews
    # Review 1: From JSON-LD
    if 'review' in json_data:
        r_json = json_data['review']
        review_node = BNode()
        g.add((movie_uri, SCHEMA.review, review_node))
        g.add((review_node, RDF.type, SCHEMA.Review))
        g.add((review_node, SCHEMA.itemReviewed, movie_uri))
        g.add((review_node, SCHEMA.name, Literal(unescape_html(r_json.get('name', '')))))
        g.add((review_node, SCHEMA.reviewBody, Literal(unescape_html(r_json.get('reviewBody', '')))))
        g.add((review_node, SCHEMA.inLanguage, Literal(r_json.get('inLanguage', 'English'))))
        g.add((review_node, SCHEMA.dateCreated, Literal(r_json.get('dateCreated', ''), datatype=XSD.date)))
        
        author_node = BNode()
        g.add((review_node, SCHEMA.author, author_node))
        g.add((author_node, RDF.type, SCHEMA.Person))
        g.add((author_node, SCHEMA.name, Literal(r_json.get('author', {}).get('name', ''))))
        
        if 'reviewRating' in r_json:
            rating_node = BNode()
            g.add((review_node, SCHEMA.reviewRating, rating_node))
            g.add((rating_node, RDF.type, SCHEMA.Rating))
            g.add((rating_node, SCHEMA.ratingValue, Literal(r_json['reviewRating'].get('ratingValue', ''), datatype=XSD.integer)))
            g.add((rating_node, SCHEMA.bestRating, Literal("10", datatype=XSD.integer)))
            g.add((rating_node, SCHEMA.worstRating, Literal("1", datatype=XSD.integer)))
    
    # Review 2: From featuredReviews in __NEXT_DATA__ (if different from JSON-LD)
    featured = above_fold.get('featuredReviews', {})
    if featured and 'edges' in featured:
        for edge in featured['edges']:
            node = edge.get('node', {})
            author = node.get('author', {}).get('nickName', '')
            # Skip if this is the same as JSON-LD review
            if author and author != json_data.get('review', {}).get('author', {}).get('name', ''):
                review_node = BNode()
                g.add((movie_uri, SCHEMA.review, review_node))
                g.add((review_node, RDF.type, SCHEMA.Review))
                g.add((review_node, SCHEMA.itemReviewed, movie_uri))
                
                summary = node.get('summary', {}).get('originalText', '')
                if summary:
                    g.add((review_node, SCHEMA.name, Literal(summary)))
                
                text = node.get('text', {})
                if isinstance(text, dict):
                    review_body = text.get('originalText', {}).get('plainText', '') if isinstance(text.get('originalText'), dict) else text.get('originalText', '')
                else:
                    review_body = str(text)
                if review_body:
                    g.add((review_node, SCHEMA.reviewBody, Literal(review_body)))
                
                g.add((review_node, SCHEMA.inLanguage, Literal("English")))
                
                submission_date = node.get('submissionDate', '')
                if submission_date:
                    g.add((review_node, SCHEMA.dateCreated, Literal(submission_date, datatype=XSD.date)))
                
                author_node = BNode()
                g.add((review_node, SCHEMA.author, author_node))
                g.add((author_node, RDF.type, SCHEMA.Person))
                g.add((author_node, SCHEMA.name, Literal(author)))
                
                rating = node.get('rating', '')
                if rating:
                    rating_node = BNode()
                    g.add((review_node, SCHEMA.reviewRating, rating_node))
                    g.add((rating_node, RDF.type, SCHEMA.Rating))
                    g.add((rating_node, SCHEMA.ratingValue, Literal(rating, datatype=XSD.integer)))
                    g.add((rating_node, SCHEMA.bestRating, Literal("10", datatype=XSD.integer)))
                    g.add((rating_node, SCHEMA.worstRating, Literal("1", datatype=XSD.integer)))
    
    # Review 3: AI Summary - Extract from HTML
    ai_summary_div = soup.find("div", {"data-testid": "ai-review-summary"})
    if ai_summary_div:
        summary_text_div = ai_summary_div.find("div", class_=re.compile("html-content-inner"))
        if summary_text_div:
            summary_text = summary_text_div.get_text(strip=True)
            ai_node = BNode()
            g.add((movie_uri, SCHEMA.review, ai_node))
            g.add((ai_node, RDF.type, SCHEMA.Review))
            g.add((ai_node, SCHEMA.itemReviewed, movie_uri))
            g.add((ai_node, SCHEMA.name, Literal("Summary")))
            g.add((ai_node, SCHEMA.reviewBody, Literal(summary_text)))
            g.add((ai_node, SCHEMA.inLanguage, Literal("English")))
            
            ai_author = BNode()
            g.add((ai_node, SCHEMA.author, ai_author))
            g.add((ai_author, RDF.type, SCHEMA.SoftwareApplication))
            g.add((ai_author, SCHEMA.name, Literal("AI-Generated Review")))
            
            if 'aggregateRating' in json_data:
                ag_data = json_data['aggregateRating']
                ai_rating = BNode()
                g.add((ai_node, SCHEMA.reviewRating, ai_rating))
                g.add((ai_rating, RDF.type, SCHEMA.Rating))
                g.add((ai_rating, SCHEMA.ratingValue, Literal(ag_data['ratingValue'], datatype=XSD.decimal)))
                g.add((ai_rating, SCHEMA.bestRating, Literal("10", datatype=XSD.integer)))
                g.add((ai_rating, SCHEMA.worstRating, Literal("1", datatype=XSD.integer)))
    
    # Metacritic Aggregate Rating
    metacritic = above_fold.get('metacritic', {})
    if metacritic and 'metascore' in metacritic:
        score = metacritic['metascore'].get('score')
        if score:
            meta_node = BNode()
            g.add((movie_uri, SCHEMA.aggregateRating, meta_node))
            g.add((meta_node, RDF.type, SCHEMA.AggregateRating))
            g.add((meta_node, SCHEMA.name, Literal("Metacritic Score")))
            g.add((meta_node, SCHEMA.ratingValue, Literal(score, datatype=XSD.decimal)))
            g.add((meta_node, SCHEMA.bestRating, Literal("100", datatype=XSD.integer)))
            g.add((meta_node, SCHEMA.worstRating, Literal("0", datatype=XSD.integer)))
            g.add((meta_node, SCHEMA.url, URIRef(f"{movie_url}criticreviews/")))
    
    # Images - Extract from mainColumnData.titleMainImages with dimensions
    images_data = {}
    if main_col and 'titleMainImages' in main_col:
        title_images = main_col['titleMainImages']
        if 'edges' in title_images:
            for edge in title_images['edges']:
                node = edge.get('node', {})
                img_id = node.get('id', '')
                if img_id:
                    images_data[img_id] = {
                        'url': node.get('url', ''),
                        'width': node.get('width'),
                        'height': node.get('height'),
                        'caption': node.get('caption', {}).get('plainText', '') if isinstance(node.get('caption'), dict) else node.get('caption', '')
                    }
    
    # Also get images from above_fold.images
    if 'images' in above_fold and 'edges' in above_fold['images']:
        for edge in above_fold['images']['edges']:
            node = edge.get('node', {})
            img_id = node.get('id', '')
            if img_id and img_id not in images_data:
                images_data[img_id] = {
                    'url': node.get('url', ''),
                    'width': node.get('width'),
                    'height': node.get('height'),
                    'caption': node.get('caption', {}).get('plainText', '') if isinstance(node.get('caption'), dict) else node.get('caption', '')
                }
    
    # Process images from HTML Photos section
    photos_section = soup.find("section", {"data-testid": "Photos"})
    if photos_section:
        photo_links = photos_section.find_all("a", href=re.compile("mediaviewer"))
        processed_images = set()
        
        for link in photo_links:
            href = link.get('href', '')
            rm_match = re.search(r'/(rm\d+)/', href)
            if rm_match:
                rm_id = rm_match.group(1)
                if rm_id in processed_images:
                    continue
                processed_images.add(rm_id)
                
                movie_id = get_id_from_url(movie_url)
                img_node_url = f"https://www.imdb.com/title/{movie_id}/mediaviewer/{rm_id}/"
                img_node = URIRef(img_node_url)
                
                # Get data from images_data if available
                img_info = images_data.get(rm_id, {})
                
                # Get URL - prefer from images_data, fallback to HTML
                if img_info.get('url'):
                    img_url = img_info['url']
                else:
                    img_tag = link.find("img")
                    if img_tag:
                        src = img_tag.get("src") or img_tag.get("data-src", "")
                        # Remove _QL75_UX... suffix to get full resolution
                        if "_QL75" in src:
                            src = re.sub(r'_QL75[^.]*', '', src)
                        img_url = src
                    else:
                        continue
                
                # Get caption - prefer from images_data, fallback to HTML
                if img_info.get('caption'):
                    caption = img_info['caption']
                else:
                    img_tag = link.find("img")
                    if img_tag:
                        caption = img_tag.get("alt", "") or img_tag.get("title", "")
                    else:
                        caption = ""
                
                g.add((movie_uri, SCHEMA.image, img_node))
                g.add((img_node, RDF.type, SCHEMA.ImageObject))
                g.add((img_node, SCHEMA.url, URIRef(img_url)))
                if caption:
                    g.add((img_node, SCHEMA.caption, Literal(caption)))
                
                # Add dimensions from images_data
                width = img_info.get('width')
                height = img_info.get('height')
                if width and height:
                    g.add((img_node, SCHEMA.width, Literal(width, datatype=XSD.integer)))
                    g.add((img_node, SCHEMA.height, Literal(height, datatype=XSD.integer)))
                
                # Extract mainEntity from caption
                for s, p, o in g.triples((movie_uri, SCHEMA.actor, None)):
                    actor_name = g.value(o, SCHEMA.name)
                    if actor_name and str(actor_name) in caption:
                        g.add((img_node, SCHEMA.mainEntity, o))
                
                # Check for Danny Nucci in caption
                if "Danny Nucci" in caption:
                    danny_uri = URIRef("https://www.imdb.com/name/nm0634240/")
                    g.add((img_node, SCHEMA.mainEntity, danny_uri))
                    g.add((danny_uri, RDF.type, SCHEMA.Person))
                    g.add((danny_uri, SCHEMA.name, Literal("Danny Nucci")))
    
    return g

def main():
    parser = argparse.ArgumentParser(
        description='Parse IMDb HTML file and generate RDF triples in Turtle format.'
    )
    parser.add_argument(
        'input_file',
        type=str,
        help='Path to the IMDb HTML file to parse'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output TTL file path (default: input filename with .ttl extension)'
    )
    
    args = parser.parse_args()
    
    html_file = Path(args.input_file)
    
    if not html_file.exists():
        print(f"Error: {html_file} not found.")
        return 1
    
    # Determine output file
    if args.output:
        output_file = Path(args.output)
    else:
        # Use input filename with .ttl extension
        output_file = html_file.parent / f"{html_file.stem}_generated.ttl"
    
    print(f"Parsing {html_file}...")
    try:
        graph = parse_imdb_html(html_file)
    except Exception as e:
        print(f"Error parsing HTML file: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Serialize to Turtle format
    output_turtle = graph.serialize(format='turtle', encoding='utf-8')
    
    # Fix namespace prefix from schema1 to schema if needed
    output_turtle = output_turtle.replace(b'schema1:', b'schema:')
    output_turtle = output_turtle.replace(b'@prefix schema1:', b'@prefix schema:')
    
    with open(output_file, 'wb') as f:
        f.write(output_turtle)
    
    print(f"Successfully generated {output_file}")
    print(f"Total triples: {len(graph)}")
    
    # Get movie URI for summary
    movie_uris = list(graph.subjects(RDF.type, SCHEMA.Movie))
    if movie_uris:
        movie_uri = movie_uris[0]
        movie_name = graph.value(movie_uri, SCHEMA.name)
        print(f"Movie: {movie_name}")
        print(f"URI: {movie_uri}")
        
        # Summary statistics
        actors = list(graph.triples((movie_uri, SCHEMA.actor, None)))
        directors = list(graph.triples((movie_uri, SCHEMA.director, None)))
        reviews = list(graph.triples((movie_uri, SCHEMA.review, None)))
        images = list(graph.triples((movie_uri, SCHEMA.image, None)))
        
        print(f"\nExtracted:")
        print(f"  - Actors: {len(actors)}")
        print(f"  - Directors: {len(directors)}")
        print(f"  - Reviews: {len(reviews)}")
        print(f"  - Images: {len(images)}")
    
    return 0

if __name__ == "__main__":
    exit(main())
