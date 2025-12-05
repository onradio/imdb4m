import os
import re
import requests
from pathlib import Path
from urllib.parse import urlparse


def extract_movie_id(url):
    """
    Extract the movie ID from an IMDb URL.
    
    Args:
        url: IMDb movie URL (e.g., https://www.imdb.com/title/tt0120338/)
    
    Returns:
        str: Movie ID (e.g., 'tt0120338')
    """
    # Pattern to match IMDb movie ID (tt followed by 7-8 digits)
    pattern = r'/title/(tt\d{7,8})'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    else:
        raise ValueError(f"Could not extract movie ID from URL: {url}")


def get_headers():
    """
    Get headers to mimic a browser request.
    
    Returns:
        dict: Headers dictionary
    """
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }


def download_imdb_movie(url, output_dir="movies"):
    """
    Download an IMDb movie page and save it to the specified directory structure.
    
    Args:
        url: IMDb movie URL (e.g., https://www.imdb.com/title/tt0120338/)
        output_dir: Base directory for saving movies (default: 'movies')
    
    Returns:
        str: Path to the saved HTML file
    """
    # Extract movie ID from URL
    movie_id = extract_movie_id(url)
    
    # Create directory structure: movies/{movie_id}/movie_html/
    movie_dir = Path(output_dir) / movie_id / "movie_html"
    movie_dir.mkdir(parents=True, exist_ok=True)
    
    # Download the HTML page
    print(f"Downloading IMDb page for movie ID: {movie_id}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Save the HTML content
        html_file = movie_dir / f"{movie_id}.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"Successfully saved HTML to: {html_file}")
        return str(html_file)
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading the page: {e}")
        raise


def download_imdb_soundtrack(movie_url, output_dir="movies"):
    """
    Download an IMDb movie soundtrack page and save it to the specified directory structure.
    
    Args:
        movie_url: IMDb movie URL (e.g., https://www.imdb.com/title/tt0120338/)
        output_dir: Base directory for saving movies (default: 'movies')
    
    Returns:
        str: Path to the saved HTML file
    """
    # Extract movie ID from URL
    movie_id = extract_movie_id(movie_url)
    
    # Construct soundtrack URL
    soundtrack_url = f"https://www.imdb.com/title/{movie_id}/soundtrack/"
    
    # Create directory structure: movies/{movie_id}/movie_soundtrack/
    soundtrack_dir = Path(output_dir) / movie_id / "movie_soundtrack"
    soundtrack_dir.mkdir(parents=True, exist_ok=True)
    
    # Download the HTML page
    print(f"Downloading IMDb soundtrack page for movie ID: {movie_id}")
    print(f"URL: {soundtrack_url}")
    
    try:
        response = requests.get(soundtrack_url, headers=get_headers(), timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Save the HTML content
        html_file = soundtrack_dir / f"{movie_id}_sound.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"Successfully saved soundtrack HTML to: {html_file}")
        return str(html_file)
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading the soundtrack page: {e}")
        raise


def main():
    """
    Main function to run the script from command line.
    """
    import sys
    
    # if len(sys.argv) < 2:
    #     print("Usage: python download_imdb_movie.py <imdb_url> [output_dir]")
    #     print("Example: python download_imdb_movie.py https://www.imdb.com/title/tt0120338/")
    #     sys.exit(1)
    
    # url = sys.argv[1]
    url = "https://www.imdb.com/title/tt0120338/"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "movies"
    
    try:
        # Download main movie page
        download_imdb_movie(url, output_dir)
        
        # Download soundtrack page
        download_imdb_soundtrack(url, output_dir)
        
        print("\nAll downloads completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

