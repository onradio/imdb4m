import re
from pathlib import Path
from lxml import html, etree


def find_actor_section_and_count_movies(file_path):
    """
    Find the Actor section in the HTML and count movie URLs within it.
    
    Args:
        file_path: Path to the HTML file
    
    Returns:
        tuple: (count, unique_movie_ids, movie_urls_list)
    """
    try:
        # Read the HTML file
        content = file_path.read_text(encoding='utf-8')
        
        # Parse the HTML
        tree = html.fromstring(content)
        
        # Find the h3 element with class containing "ipc-title__text" and text "Actor"
        # Try multiple XPath selectors to find the Actor heading
        actor_headings = tree.xpath(
            "//h3[contains(@class, 'ipc-title__text') and contains(@class, 'ipc-title__text--reduced') and contains(text(), 'Actor')]"
        )
        
        if not actor_headings:
            # Try alternative selectors
            actor_headings = tree.xpath("//h3[contains(@class, 'ipc-title__text') and normalize-space(text())='Actor']")
        
        if not actor_headings:
            # Try finding by text content
            actor_headings = tree.xpath("//h3[normalize-space(text())='Actor']")
        
        if not actor_headings:
            print("Warning: Could not find Actor heading with expected class.")
            print("Trying alternative search methods...")
            # Try to find any element containing "Actor" as a section title
            actor_headings = tree.xpath("//*[contains(@class, 'ipc-title') and contains(text(), 'Actor')]")
        
        if not actor_headings:
            print("Error: Could not find Actor section heading.")
            return 0, [], []
        
        actor_heading = actor_headings[0]
        print(f"Found Actor heading: '{actor_heading.text_content().strip()}'")
        
        # Find the parent container - typically a section or div
        # The Actor section content is usually in a parent container
        parent = actor_heading.getparent()
        
        # Keep going up until we find a meaningful container (section, div with class, etc.)
        actor_section = parent
        max_depth = 10
        depth = 0
        
        while actor_section is not None and depth < max_depth:
            # Check if this is a good container (has class or is a section)
            tag = actor_section.tag.lower()
            classes = actor_section.get('class', '')
            
            # If it's a section or has relevant classes, use it
            if tag in ['section', 'div'] and ('ipc-page-section' in classes or 'credits' in classes.lower() or depth > 2):
                break
            
            parent = actor_section.getparent()
            if parent is None:
                break
            actor_section = parent
            depth += 1
        
        if actor_section is None:
            print("Warning: Could not find Actor section container. Using parent of heading.")
            actor_section = actor_heading.getparent()
        
        # Now find all movie URLs in the Actor section
        # Movie URLs typically have pattern: /title/tt\d{7,8} or https://www.imdb.com/title/tt\d{7,8}
        movie_url_pattern = r'/title/(tt\d{7,8})'
        movie_ids = []
        
        # Method 1: Get all links with href containing /title/tt
        if actor_section is not None:
            links = actor_section.xpath(".//a[contains(@href, '/title/tt')]")
            print(f"Found {len(links)} links with movie URLs in Actor section")
            
            for link in links:
                href = link.get('href', '')
                # Extract movie ID from href
                match = re.search(movie_url_pattern, href, re.IGNORECASE)
                if match:
                    movie_ids.append(match.group(1))
        
        # Method 2: Also search the HTML content as text (in case URLs are in data attributes, scripts, etc.)
        if actor_section is not None:
            try:
                section_html = etree.tostring(actor_section, encoding='unicode', method='html')
                # Find all movie URLs using regex in the HTML content
                text_matches = re.findall(movie_url_pattern, section_html, re.IGNORECASE)
                movie_ids.extend(text_matches)
            except:
                pass
        
        # Get unique movie IDs
        unique_movie_ids = list(set(movie_ids))
        
        return len(movie_ids), unique_movie_ids, movie_ids
        
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()
        return 0, [], []


def main():
    """
    Main function to count movie URLs in the Actor section.
    """
    import sys
    
    # Default file path
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
    else:
        file_path = Path("movies/actors/nm0000138/actor.html")
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("COUNTING MOVIE URLS IN ACTOR SECTION")
    print("=" * 60)
    print(f"\nAnalyzing file: {file_path}")
    
    total_count, unique_ids, all_movie_ids = find_actor_section_and_count_movies(file_path)
    
    print(f"\nResults:")
    print(f"  Total movie URL occurrences: {total_count}")
    print(f"  Unique movie IDs: {len(unique_ids)}")
    
    if unique_ids:
        print(f"\nFirst 20 unique movie IDs:")
        for i, movie_id in enumerate(sorted(unique_ids)[:20], 1):
            print(f"  {i}. {movie_id}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

