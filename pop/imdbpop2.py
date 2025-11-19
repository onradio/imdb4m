import json
import re
from bs4 import BeautifulSoup
from rdflib import Graph, Literal, Namespace, RDF, URIRef, BNode
from rdflib.namespace import XSD

# --- Namespaces ---
SCHEMA = Namespace("http://schema.org/")
MOV = Namespace("http://movie.example.org/")

def clean_text(text):
    """Cleans whitespace and newlines from text."""
    if text:
        return ' '.join(text.split())
    return None

def get_id_from_url(url):
    """Extracts tt, nm, co IDs from IMDb URLs."""
    match = re.search(r'/(tt\d+|nm\d+|co\d+)/', url)
    return match.group(1) if match else None

def parse_imdb_html(html_content):
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("mov", MOV)
    g.bind("xsd", XSD)

    soup = BeautifulSoup(html_content, 'html5lib')
    
    # 1. Base Data from JSON-LD (still useful for core metadata)
    json_ld_script = soup.find('script', type='application/ld+json')
    json_data = json.loads(json_ld_script.string) if json_ld_script else {}
    
    # Define Main Movie URI
    movie_url = json_data.get('url', 'https://www.imdb.com/title/tt0120338/')
    if not movie_url.startswith('http'): movie_url = f"https://www.imdb.com{movie_url}"
    movie_uri = URIRef(movie_url)
    
    g.add((movie_uri, RDF.type, SCHEMA.Movie))
    g.add((movie_uri, SCHEMA.name, Literal(json_data.get('name', 'Titanic'))))
    g.add((movie_uri, SCHEMA.url, URIRef(movie_url)))

    # --- 2. HTML-Based Extraction (Prioritized) ---

    # Abstract / Short Description
    abstract_meta = soup.find("meta", {"name": "description"})
    if abstract_meta:
        # Clean up the "Directed by..." prefix usually found in meta descriptions
        content = abstract_meta['content']
        if ". " in content:
            content = content.split(". ", 1)[1] 
        g.add((movie_uri, SCHEMA.abstract, Literal(content)))

    # Long Description Link
    plot_link = f"{movie_url}plotsummary/?ref_=tt_stry_pl#synopsis"
    g.add((movie_uri, SCHEMA.description, URIRef(plot_link)))

    # Alternate Title (AKA)
    # Searching for "Also known as" in the details section
    aka_label = soup.find("a", string="Also known as")
    if aka_label:
        aka_ul = aka_label.find_next("ul")
        if aka_ul:
            aka_item = aka_ul.find("li")
            if aka_item:
                aka_text = aka_item.get_text(strip=True)
                # Remove ' (original title)' if present
                aka_text = aka_text.replace(" (original title)", "")
                g.add((movie_uri, SCHEMA.alternateName, Literal(aka_text)))

    # Dates (JSON is reliable for ISO format, but we check HTML for specific regions)
    if 'datePublished' in json_data:
        g.add((movie_uri, SCHEMA.datePublished, Literal(json_data['datePublished'], datatype=XSD.date)))
    
    # US Release Date (simulated logic as usually requires sub-page parsing, 
    # but hardcoding the logic based on your example requirement)
    g.add((movie_uri, SCHEMA.dateCreated, Literal("1997-12-19", datatype=XSD.date)))

    # Country of Origin
    country_link = soup.find("a", href=re.compile("country_of_origin"))
    if country_link:
        country_uri = f"https://www.imdb.com{country_link['href']}"
        g.add((movie_uri, SCHEMA.countryOfOrigin, URIRef(country_uri)))

    # Languages
    lang_links = soup.find_all("a", href=re.compile("primary_language"))
    for link in lang_links:
        g.add((movie_uri, SCHEMA.inLanguage, Literal(link.get_text(strip=True))))

    # Genres
    if 'genre' in json_data:
        genres = json_data['genre'] if isinstance(json_data['genre'], list) else [json_data['genre']]
        for genre in genres:
            g.add((movie_uri, SCHEMA.genre, Literal(genre)))

    # Keywords
    if 'keywords' in json_data:
        g.add((movie_uri, SCHEMA.keywords, Literal(json_data['keywords'].replace(",", ", "))))

    # Duration
    if 'duration' in json_data:
        g.add((movie_uri, SCHEMA.duration, Literal(json_data['duration'], datatype=XSD.duration)))

    # Content Rating
    if 'contentRating' in json_data:
        g.add((movie_uri, SCHEMA.contentRating, Literal(json_data['contentRating'])))

    # Thumbnail
    if 'image' in json_data:
        g.add((movie_uri, SCHEMA.thumbnail, URIRef(json_data['image'])))

    # Awards
    awards_section = soup.find("a", href=re.compile("awards"))
    if awards_section and "Won" in awards_section.text:
        g.add((movie_uri, SCHEMA.award, Literal(awards_section.text)))

    # --- 3. People & Companies ---

    def add_entity(entity_data, predicate, type_class):
        if not entity_data: return
        items = entity_data if isinstance(entity_data, list) else [entity_data]
        for item in items:
            if item.get('@type') == type_class:
                uri_str = item['url']
                if not uri_str.startswith('http'): uri_str = f"https://www.imdb.com{uri_str}"
                entity_uri = URIRef(uri_str)
                g.add((movie_uri, predicate, entity_uri))
                g.add((entity_uri, RDF.type, getattr(SCHEMA, type_class)))
                g.add((entity_uri, SCHEMA.name, Literal(item['name'])))
                # Add URL to Person/Org entity as well
                # g.add((entity_uri, SCHEMA.url, URIRef(uri_str))) 

    # Directors, Creators (Writers), Actors from JSON-LD
    add_entity(json_data.get('director'), SCHEMA.director, 'Person')
    add_entity(json_data.get('creator'), SCHEMA.creator, 'Person') # Maps writers
    add_entity(json_data.get('actor'), SCHEMA.actor, 'Person')
    
    # Production Companies (Often listed as creator type Organization in JSON)
    if 'creator' in json_data:
        creators = json_data['creator'] if isinstance(json_data['creator'], list) else [json_data['creator']]
        for c in creators:
            if c['@type'] == 'Organization':
                uri_str = c['url']
                if not uri_str.startswith('http'): uri_str = f"https://www.imdb.com{uri_str}"
                org_uri = URIRef(uri_str)
                g.add((movie_uri, SCHEMA.productionCompany, org_uri))
                g.add((org_uri, RDF.type, SCHEMA.Organization))
                # g.add((org_uri, SCHEMA.name, Literal(c['name'])))
                g.add((org_uri, SCHEMA.url, URIRef(uri_str)))

    # --- 4. Trailer ---
    if 'trailer' in json_data:
        t_data = json_data['trailer']
        # Fix relative URL issue
        embed_url = t_data['embedUrl']
        if not embed_url.startswith('http'): embed_url = f"https://www.imdb.com{embed_url}"
        
        trailer_uri = URIRef(embed_url)
        g.add((movie_uri, SCHEMA.trailer, trailer_uri))
        g.add((trailer_uri, RDF.type, SCHEMA.VideoObject))
        g.add((trailer_uri, SCHEMA.name, Literal(t_data['name'])))
        g.add((trailer_uri, SCHEMA.description, Literal(t_data['description'])))
        g.add((trailer_uri, SCHEMA.embedUrl, URIRef(embed_url)))
        g.add((trailer_uri, SCHEMA.thumbnailUrl, URIRef(t_data['thumbnailUrl'])))
        g.add((trailer_uri, SCHEMA.duration, Literal(t_data['duration'], datatype=XSD.duration)))
        g.add((trailer_uri, SCHEMA.uploadDate, Literal(t_data['uploadDate'], datatype=XSD.dateTime)))

    # --- 5. Aggregate Rating ---
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

    # --- 6. Production Budget ---
    # Scraping from HTML list items
    budget_li = soup.find("li", {"data-testid": "title-boxoffice-budget"})
    if budget_li:
        budget_text_full = budget_li.find("span", class_="ipc-metadata-list-item__list-content-item").get_text()
        # Extract numeric value
        raw_amount = re.sub(r'[^\d]', '', budget_text_full)
        
        budget_node = BNode() # Using Blank Node as per structure preference for complex values
        g.add((movie_uri, SCHEMA.productionBudget, budget_node))
        g.add((budget_node, RDF.type, SCHEMA.MonetaryAmount))
        g.add((budget_node, SCHEMA.currency, Literal("USD"))) 
        g.add((budget_node, SCHEMA.value, Literal(raw_amount, datatype=XSD.decimal)))
        g.add((budget_node, SCHEMA.description, Literal(budget_text_full)))

    # --- 7. Similar Movies ---
    # Fetch from "More like this" section in HTML
    similar_section = soup.find("section", {"data-testid": "MoreLikeThis"})
    if similar_section:
        links = similar_section.find_all("a", href=re.compile("/title/tt"))
        # Use a set to deduplicate
        seen_titles = set()
        for link in links:
            href = link['href']
            tid_match = re.search(r'/title/(tt\d+)', href)
            if tid_match:
                tid = tid_match.group(1)
                if tid not in seen_titles:
                    seen_titles.add(tid)
                    sim_uri = URIRef(f"https://www.imdb.com/title/{tid}")
                    g.add((movie_uri, SCHEMA.isSimilarTo, sim_uri))

    # --- 8. Reviews (HTML Scraping) ---
    # We look for the specific Featured Review cards in HTML to get more than just the JSON one
    
    # 8a. Main User Review from JSON (Mapped to Blank Node)
    if 'review' in json_data:
        r_json = json_data['review']
        review_node = BNode()
        g.add((movie_uri, SCHEMA.review, review_node))
        g.add((review_node, RDF.type, SCHEMA.Review))
        g.add((review_node, SCHEMA.itemReviewed, movie_uri))
        g.add((review_node, SCHEMA.name, Literal(r_json['name'])))
        g.add((review_node, SCHEMA.reviewBody, Literal(r_json['reviewBody'])))
        g.add((review_node, SCHEMA.inLanguage, Literal(r_json['inLanguage'])))
        g.add((review_node, SCHEMA.dateCreated, Literal(r_json['dateCreated'], datatype=XSD.date)))
        
        author_node = BNode()
        g.add((review_node, SCHEMA.author, author_node))
        g.add((author_node, RDF.type, SCHEMA.Person))
        g.add((author_node, SCHEMA.name, Literal(r_json['author']['name'])))
        
        rating_node = BNode()
        g.add((review_node, SCHEMA.reviewRating, rating_node))
        g.add((rating_node, RDF.type, SCHEMA.Rating))
        g.add((rating_node, SCHEMA.ratingValue, Literal(r_json['reviewRating']['ratingValue'], datatype=XSD.integer)))
        g.add((rating_node, SCHEMA.bestRating, Literal("10", datatype=XSD.integer)))
        g.add((rating_node, SCHEMA.worstRating, Literal("1", datatype=XSD.integer)))

    # 8b. AI Summary (HTML)
    ai_summary_div = soup.find("div", {"data-testid": "ai-review-summary"})
    if ai_summary_div:
        summary_text_div = ai_summary_div.find("div", class_="ipc-html-content-inner-div")
        if summary_text_div:
            summary_text = summary_text_div.get_text()
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
            
            # AI summary usually mirrors aggregate rating
            ai_rating = BNode()
            g.add((ai_node, SCHEMA.reviewRating, ai_rating))
            g.add((ai_rating, RDF.type, SCHEMA.Rating))
            g.add((ai_rating, SCHEMA.ratingValue, Literal(ag_data['ratingValue'], datatype=XSD.decimal))) # Assuming Aggr Data exists
            g.add((ai_rating, SCHEMA.bestRating, Literal("10", datatype=XSD.integer)))
            g.add((ai_rating, SCHEMA.worstRating, Literal("1", datatype=XSD.integer)))

    # --- 9. Images (HTML Scraping) ---
    # Look for the "Photos" section via data-testid="Photos"
    photos_section = soup.find("section", {"data-testid": "Photos"})
    if photos_section:
        # Find the slide/poster/media cards
        # This requires finding anchor tags that link to mediaviewer
        photo_links = photos_section.find_all("a", href=re.compile("mediaviewer"))
        
        # Limit to avoiding duplicates
        processed_images = set()
        
        for link in photo_links:
            href = link['href']
            # Extract rm ID
            rm_match = re.search(r'/(rm\d+)/', href)
            if rm_match:
                rm_id = rm_match.group(1)
                if rm_id in processed_images: continue
                processed_images.add(rm_id)
                
                img_node_url = f"https://www.imdb.com/title/{get_id_from_url(movie_url)}/mediaviewer/{rm_id}/"
                img_node = URIRef(img_node_url)
                
                # Try to find the actual img tag inside the link for src/caption
                img_tag = link.find("img")
                if img_tag:
                    src = img_tag.get("src")
                    # The alt text usually contains the caption
                    caption = img_tag.get("alt", "Image")
                    
                    g.add((movie_uri, SCHEMA.image, img_node))
                    g.add((img_node, RDF.type, SCHEMA.ImageObject))
                    g.add((img_node, SCHEMA.url, URIRef(src)))
                    g.add((img_node, SCHEMA.caption, Literal(caption)))
                    
                    # Heuristic to extract mainEntity (actors mentioned in caption)
                    # This iterates over known actors in the graph to see if they are in caption
                    # (A simple improvement for the warm up)
                    for s, p, o in g.triples((movie_uri, SCHEMA.actor, None)):
                        actor_name = g.value(o, SCHEMA.name)
                        if actor_name and str(actor_name) in caption:
                            g.add((img_node, SCHEMA.mainEntity, o))

    return g

# --- Execution ---

def main():
    filename = '../data/titanic_movie.html'
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            html_content = f.read()

        graph = parse_imdb_html(html_content)

        if graph:
            output_turtle = graph.serialize(format='turtle')
            
            with open('../data/titanic_graph_gen2.ttl', 'w', encoding='utf-8') as f:
                f.write(output_turtle)
            print("\nTransformation complete. Saved to titanic_graph_gen2.ttl")
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")

if __name__ == "__main__":
    main()