import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

# Define Namespaces
SCHEMA = Namespace("http://schema.org/")

def parse_duration(pt_string):
    """Ensures duration is passed through or cleaned if necessary."""
    return pt_string

def clean_text(text):
    """Cleans whitespace from extracted text."""
    if text:
        return text.strip().replace('\n', ' ').replace('  ', ' ')
    return None

def extract_json_ld(soup):
    """Extracts the main JSON-LD block from the IMDb page."""
    script = soup.find('script', type='application/ld+json')
    if script:
        return json.loads(script.string)
    return None

def create_knowledge_graph(html_content, base_url="https://www.imdb.com/"):
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("xsd", XSD)

    soup = BeautifulSoup(html_content, 'html5lib')
    data = extract_json_ld(soup)
    # print(data.keys())

    if not data:
        print("Error: No JSON-LD found in HTML.")
        return None

    # --- 1. Main Movie Entity ---
    movie_uri = URIRef(data['url'])
    g.add((movie_uri, RDF.type, SCHEMA.Movie))
    g.add((movie_uri, SCHEMA.name, Literal(data['name'])))
    g.add((movie_uri, SCHEMA.url, URIRef(data['url'])))
    
    # Abstract/Short Description
    if 'description' in data:
        g.add((movie_uri, SCHEMA.abstract, Literal(data['description'])))

    # Long Description (Scraping from HTML meta or specific div if JSON is short)
    # Note: The JSON-LD usually has the short one. We link the plot summary URL.
    plot_summary_url = f"{data['url']}plotsummary/?ref_=tt_stry_pl#synopsis"
    g.add((movie_uri, SCHEMA.description, URIRef(plot_summary_url)))

    # Dates
    if 'datePublished' in data:
        g.add((movie_uri, SCHEMA.datePublished, Literal(data['datePublished'], datatype=XSD.date)))
    
    # We manually add US release date if not in main JSON (often in specific sub-sections)
    # For this script, we will assume the main date is the primary one to keep it automated.
    
    # Country of Origin (Extracting from links in HTML as JSON-LD often misses this)
    country_links = soup.select("a[href*='country_of_origin']")
    if country_links:
        # Taking the first one for simplicity, or you can iterate
        country_url = f"https://www.imdb.com{country_links[0]['href']}"
        g.add((movie_uri, SCHEMA.countryOfOrigin, URIRef(country_url)))

    # Languages
    # IMDb often lists languages in a specific ul/li structure or links
    lang_links = soup.select("a[href*='primary_language']")
    for link in lang_links:
        g.add((movie_uri, SCHEMA.inLanguage, Literal(link.text.strip())))

    # Genres
    if 'genre' in data:
        genres = data['genre'] if isinstance(data['genre'], list) else [data['genre']]
        for genre in genres:
            g.add((movie_uri, SCHEMA.genre, Literal(genre)))

    # Keywords
    if 'keywords' in data: # FIXME these should be comma-split if single string and more triples added
        g.add((movie_uri, SCHEMA.keywords, Literal(data['keywords'])))

    # Duration
    if 'duration' in data:
        g.add((movie_uri, SCHEMA.duration, Literal(data['duration'], datatype=XSD.duration)))

    # Content Rating
    if 'contentRating' in data:
        g.add((movie_uri, SCHEMA.contentRating, Literal(data['contentRating'])))

    # Thumbnail
    if 'image' in data:
        g.add((movie_uri, SCHEMA.thumbnail, URIRef(data['image'])))

    # Awards (Scraping specific text)
    award_text = soup.find("a", href=re.compile("awards"))
    if award_text and "won" in award_text.text.lower():
        # Basic extraction logic, might need tuning based on exact HTML structure
        g.add((movie_uri, SCHEMA.award, Literal(clean_text(award_text.text))))

    # Alternate Names (AKA)
    aka_section = soup.find(string="Also known as")
    if aka_section:
        # Navigate up to parent li, then find the span content
        aka_parent = aka_section.find_parent("li")
        if aka_parent:
             aka_item = aka_parent.find("span", class_="ipc-metadata-list-item__list-content-item")
             if aka_item:
                 g.add((movie_uri, SCHEMA.alternateName, Literal(aka_item.text)))

    # --- 2. People (Director, Creator, Actors) ---
    
    def add_person(person_data, predicate):
        if not person_data: return
        
        people_list = person_data if isinstance(person_data, list) else [person_data]
        
        for p in people_list:
            if p['@type'] == 'Person':
                # Ensure URL is absolute
                p_url = p['url'] if p['url'].startswith("http") else f"https://www.imdb.com{p['url']}"
                person_uri = URIRef(p_url)
                g.add((movie_uri, predicate, person_uri))
                g.add((person_uri, RDF.type, SCHEMA.Person))
                g.add((person_uri, SCHEMA.name, Literal(p['name'])))

    if 'director' in data:
        add_person(data['director'], SCHEMA.director)
    
    if 'creator' in data:
        add_person(data['creator'], SCHEMA.creator)
        
    if 'actor' in data:
        add_person(data['actor'], SCHEMA.actor)

    # --- 3. Organizations (Production Companies) ---
    # These are usually inside 'creator' with type Organization in JSON-LD
    if 'creator' in data:
        creators = data['creator'] if isinstance(data['creator'], list) else [data['creator']]
        for c in creators:
            if c['@type'] == 'Organization':
                org_url = c['url'] if c['url'].startswith("http") else f"https://www.imdb.com{c['url']}"
                org_uri = URIRef(org_url)
                g.add((movie_uri, SCHEMA.productionCompany, org_uri))
                g.add((org_uri, RDF.type, SCHEMA.Organization))
                # g.add((org_uri, SCHEMA.name, Literal(c['name'])))  # FIXME not found
                g.add((org_uri, SCHEMA.url, URIRef(org_url)))

    # --- 4. Trailer ---
    if 'trailer' in data:
        t_data = data['trailer']
        trailer_uri = URIRef(f"https://www.imdb.com{t_data['url']}") # Adjusting for IMDB relative path if needed, usually absolute in JSON
        g.add((movie_uri, SCHEMA.trailer, trailer_uri))
        g.add((trailer_uri, RDF.type, SCHEMA.VideoObject))
        g.add((trailer_uri, SCHEMA.name, Literal(t_data['name'])))
        g.add((trailer_uri, SCHEMA.description, Literal(t_data['description'])))
        g.add((trailer_uri, SCHEMA.embedUrl, URIRef(f"https://www.imdb.com{t_data['embedUrl']}")))
        g.add((trailer_uri, SCHEMA.thumbnailUrl, URIRef(t_data['thumbnailUrl'])))
        g.add((trailer_uri, SCHEMA.duration, Literal(t_data['duration'], datatype=XSD.duration)))
        g.add((trailer_uri, SCHEMA.uploadDate, Literal(t_data['uploadDate'], datatype=XSD.dateTime)))

    # --- 5. Aggregate Rating ---
    if 'aggregateRating' in data:
        ar_data = data['aggregateRating']
        ar_uri = URIRef(f"{data['url']}ratings/")
        g.add((movie_uri, SCHEMA.aggregateRating, ar_uri))
        g.add((ar_uri, RDF.type, SCHEMA.AggregateRating))
        g.add((ar_uri, SCHEMA.itemReviewed, movie_uri))
        g.add((ar_uri, SCHEMA.ratingValue, Literal(ar_data['ratingValue'], datatype=XSD.decimal)))
        g.add((ar_uri, SCHEMA.ratingCount, Literal(ar_data['ratingCount'], datatype=XSD.integer)))
        g.add((ar_uri, SCHEMA.bestRating, Literal(ar_data['bestRating'], datatype=XSD.integer)))
        g.add((ar_uri, SCHEMA.worstRating, Literal(ar_data['worstRating'], datatype=XSD.integer)))

    # --- 6. Reviews ---
    # Extract Featured Review from JSON-LD
    if 'review' in data:
        r_data = data['review']
        # Create a hash or blank node for review. Here using blank node.
        review_node =  URIRef(f"{data['url']}reviews/{r_data.get('dateCreated', 'featured')}") 
        
        g.add((movie_uri, SCHEMA.review, review_node))
        g.add((review_node, RDF.type, SCHEMA.Review))
        g.add((review_node, SCHEMA.itemReviewed, movie_uri))
        g.add((review_node, SCHEMA.name, Literal(r_data['name'])))
        g.add((review_node, SCHEMA.reviewBody, Literal(r_data['reviewBody'])))
        g.add((review_node, SCHEMA.inLanguage, Literal(r_data['inLanguage'])))
        g.add((review_node, SCHEMA.dateCreated, Literal(r_data['dateCreated'], datatype=XSD.date)))
        
        # Author
        author_node = URIRef(f"user:{r_data['author']['name'].replace(' ', '_')}") # Placeholder URI logic
        g.add((review_node, SCHEMA.author, author_node))
        g.add((author_node, RDF.type, SCHEMA.Person))
        g.add((author_node, SCHEMA.name, Literal(r_data['author']['name'])))

        # Rating
        if 'reviewRating' in r_data:
            rating_node = URIRef(f"{review_node}/rating")
            g.add((review_node, SCHEMA.reviewRating, rating_node))
            g.add((rating_node, RDF.type, SCHEMA.Rating))
            g.add((rating_node, SCHEMA.ratingValue, Literal(r_data['reviewRating']['ratingValue'], datatype=XSD.integer)))
            g.add((rating_node, SCHEMA.bestRating, Literal(r_data['reviewRating']['bestRating'], datatype=XSD.integer)))
            g.add((rating_node, SCHEMA.worstRating, Literal(r_data['reviewRating']['worstRating'], datatype=XSD.integer)))

    # --- 7. Budget (Scraping from HTML Box Office section) ---
    # This is tricky as it's not in JSON-LD usually. We look for specific LI elements or sections.
    # This is a heuristic approach based on common IMDb DOM structure.
    box_office_section = soup.find("li", {"data-testid": "title-boxoffice-budget"})
    if box_office_section:
        budget_text = box_office_section.find("span", class_="ipc-metadata-list-item__list-content-item").text
        # Cleaning string to get number: "$200,000,000 (estimated)" -> 200000000
        budget_amount = re.sub(r'[^\d]', '', budget_text)
        
        budget_node = URIRef(f"{data['url']}budget")
        g.add((movie_uri, SCHEMA.productionBudget, budget_node))
        g.add((budget_node, RDF.type, SCHEMA.MonetaryAmount))
        g.add((budget_node, SCHEMA.currency, Literal("USD"))) # Assuming USD for simplicity or extract symbol
        g.add((budget_node, SCHEMA.value, Literal(budget_amount, datatype=XSD.decimal)))
        g.add((budget_node, SCHEMA.description, Literal(budget_text)))

    # --- 8. Similar Movies ---
    # Looking for "More like this" section
    more_like_this = soup.select("a[href*='tt_mlt']")
    # Using a set to avoid duplicates
    similar_movies = set()
    for link in more_like_this:
        href = link['href']
        # Extract tt ID
        match = re.search(r'/title/(tt\d+)/', href)
        if match:
            similar_movies.add(f"https://www.imdb.com/title/{match.group(1)}")
    
    for movie_url in similar_movies:
        g.add((movie_uri, SCHEMA.isSimilarTo, URIRef(movie_url)))

    return g

# --- Execution ---

# 1. Load the HTML file
filename = '../data/titanic_movie.html'
with open(filename, 'r', encoding='utf-8') as f:
    html_content = f.read()

# 2. Generate Graph
graph = create_knowledge_graph(html_content)
if graph:  # print the number of triples in the graph
    print(f"Graph has {len(graph)} triples.")

# 3. Serialize to Turtle
if graph:
    output_turtle = graph.serialize(format='turtle')    
    with open('../data/titanic_graph_gen.ttl', 'w', encoding='utf-8') as f:
        f.write(output_turtle)
    print("\nTransformation complete. Saved to titanic_graph_gen.ttl")
