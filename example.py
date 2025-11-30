"""
Example script showing how to use the Music Linker.
Now prefers reading soundtrack metadata from local TTL files.
"""
from pathlib import Path
import os
from linker import MusicLinker, SoundtrackParser, Config, setup_logging
from linker.utils import save_results_to_json, save_results_to_csv


def main():
    # Setup logging
    setup_logging('INFO')
    
    # Load configuration from .env file
    config = Config()
    config.validate()
    
    # Prefer TTL parsing from data/subset/<IMDB_ID>
    project_root = Path(__file__).resolve().parent
    subset_root = project_root / "data" / "subset"
    imdb_id = os.getenv("IMDB_ID", "tt0405159")

    soundtracks = []
    movie_dir = subset_root / imdb_id
    has_ttl = (
        (movie_dir / "movie_html" / f"{imdb_id}.ttl").exists()
        and (movie_dir / "movie_soundtrack" / f"{imdb_id}_soundtrack.ttl").exists()
    )

    if has_ttl:
        print(f"Parsing TTL metadata for {imdb_id} from {subset_root}...")
        soundtracks = SoundtrackParser.parse_soundtrack_ttl(str(subset_root), imdb_id)
    else:
        print("TTL not found; falling back to text parsing example.")
        titanic_soundtrack_text = """My Heart Will Go On\nMusic by James Horner\nLyrics by Will Jennings\nPerformed by Céline Dion\nProduced by James Horner and Simon Franglen\nCeline Dion performs courtesy of 550 Music/Sony Music Entertainment (Canada) Inc.\nValse Septembre\nWritten by Felix Godin\nPerformed by Salonisti (as I Salonisti)\nProduced by John Altman\nWedding Dance\nWritten by Paul Lincke\nPerformed by Salonisti (as I Salonisti)\nProduced by John Altman\nSphinx\nWritten by Francis Popy\nPerformed by Salonisti (as I Salonisti)\nProduced by John Altman\nVision Of Salome\nWritten by Archibald Joyce\nPerformed by Salonisti (as I Salonisti)\nProduced by John Altman\nAlexander's Ragtime Band\nWritten by Irving Berlin\nPerformed by Salonisti (as I Salonisti)\nProduced by John Altman\nOh You Beautiful Doll\nby A. Seymour Brown and Nat Ayer as (Nat D. Ayer)\nProduced and Arranged by William Ross\nCome, Josephine, In My Flying Machine\nby Al Bryan (as Alfred Bryan) and Fred Fisher\nPerformed by Leonardo DiCaprio (uncredited) and Kate Winslet (uncredited)\nProduced and Arranged by William Ross\nNearer My God To Thee\nWritten by Lowell Mason and Sarah F. Adams (as Sarah Adams)\nPerformed by Salonisti (as I Salonisti)\nArranged by Jonathan Evans-Jones\nProduced by Lorenz Hasler\nAn Irish Party in Third Class\n(uncredited)\nincludes \"John Ryan's Polka\" and \"Blarney Pilgrim\" (Traditional)\nPerformed & Arranged by Gaelic Storm\nProduced by Randy Gerston\nJack Dawson's Luck\n(uncredited)\nincludes \"Humours of Caledon\", \"The Red-Haired Lass\", \"The Boys On The Hilltop\", and \"The Bucks Of Oranmore\" (Traditional)\nLament\n(uncredited)\nincludes \"A Spailpín A Rún\" (Traditional)\nBlue Danube\n(uncredited)\nWritten by Johann Strauss\nPerformed by Salonisti (as I Salonisti)\nOrpheus\n(uncredited)\nWritten by Jacques Offenbach\nPerformed by Salonisti (as I Salonisti)\nEternal Father Strong To Save\n(uncredited)\nLyrics by William Whiting and music by John B. Dykes (uncredited))\nPerformed by Cast"""
        print("Parsing soundtrack metadata from example text...")
        soundtracks = SoundtrackParser.parse_soundtrack_text(
            titanic_soundtrack_text,
            movie_title="Titanic"
        )
    print(f"Found {len(soundtracks)} soundtracks\n")
    
    # Initialize the music linker
    print("Initializing Music Linker...")
    linker = MusicLinker(
        youtube_api_key=config.youtube_api_key,
        gemini_api_key=config.gemini_api_key,
        max_search_results=config.max_search_results,
        max_comments_per_video=config.max_comments_per_video,
        use_comments=config.use_comments,
        gemini_model=config.gemini_model
    )
    
    # Find matches for all soundtracks (in parallel)
    print(f"Finding YouTube matches for {len(soundtracks)} soundtracks...\n")
    results = linker.find_matches_batch(
        soundtracks,
        max_workers=config.max_workers
    )
    
    # Print results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80 + "\n")
    
    for result in results:
        print(f"Song: {result.soundtrack.title}")
        if result.soundtrack.performer:
            print(f"Performer: {result.soundtrack.performer}")
        print(f"Search Query: {result.search_query}")
        
        if result.best_match:
            print(f"✓ Best Match: {result.best_match.title}")
            print(f"  URL: {result.best_match.url}")
            print(f"  Channel: {result.best_match.channel_title}")
            print(f"  Views: {result.best_match.view_count:,}")
            
            if result.match_score:
                print(f"  Confidence: {result.match_score.confidence:.2%}")
                print(f"  Reasoning: {result.match_score.reasoning}")
        else:
            print(f"✗ No match found")
            if result.error:
                print(f"  Error: {result.error}")
        
        print("-" * 80 + "\n")
    
    # Save results
    print("Saving results...")
    save_results_to_json(results, "output/results.json")
    save_results_to_csv(results, "output/results.csv")
    print("Results saved to output/results.json and output/results.csv")
    
    # Statistics
    successful = sum(1 for r in results if r.is_successful())
    high_confidence = sum(1 for r in results if r.match_score and r.match_score.confidence > 0.7)
    
    print(f"\nStatistics:")
    print(f"  Total soundtracks: {len(results)}")
    print(f"  Successful matches: {successful}")
    print(f"  High confidence matches (>70%): {high_confidence}")


if __name__ == "__main__":
    main()
