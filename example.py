"""
Example script showing how to use the Music Linker.
"""
from src import MusicLinker, SoundtrackParser, Config, setup_logging
from src.utils import save_results_to_json, save_results_to_csv


def main():
    # Setup logging
    setup_logging('INFO')
    
    # Load configuration from .env file
    config = Config()
    config.validate()
    
    # IMDb soundtrack text (example from Titanic)
    titanic_soundtrack_text = """My Heart Will Go On
Music by James Horner
Lyrics by Will Jennings
Performed by Céline Dion
Produced by James Horner and Simon Franglen
Celine Dion performs courtesy of 550 Music/Sony Music Entertainment (Canada) Inc.
Valse Septembre
Written by Felix Godin
Performed by Salonisti (as I Salonisti)
Produced by John Altman
Wedding Dance
Written by Paul Lincke
Performed by Salonisti (as I Salonisti)
Produced by John Altman
Sphinx
Written by Francis Popy
Performed by Salonisti (as I Salonisti)
Produced by John Altman
Vision Of Salome
Written by Archibald Joyce
Performed by Salonisti (as I Salonisti)
Produced by John Altman
Alexander's Ragtime Band
Written by Irving Berlin
Performed by Salonisti (as I Salonisti)
Produced by John Altman
Oh You Beautiful Doll
by A. Seymour Brown and Nat Ayer as (Nat D. Ayer)
Produced and Arranged by William Ross
Come, Josephine, In My Flying Machine
by Al Bryan (as Alfred Bryan) and Fred Fisher
Performed by Leonardo DiCaprio (uncredited) and Kate Winslet (uncredited)
Produced and Arranged by William Ross
Nearer My God To Thee
Written by Lowell Mason and Sarah F. Adams (as Sarah Adams)
Performed by Salonisti (as I Salonisti)
Arranged by Jonathan Evans-Jones
Produced by Lorenz Hasler
An Irish Party in Third Class
(uncredited)
includes "John Ryan's Polka" and "Blarney Pilgrim" (Traditional)
Performed & Arranged by Gaelic Storm
Produced by Randy Gerston
Jack Dawson's Luck
(uncredited)
includes "Humours of Caledon", "The Red-Haired Lass", "The Boys On The Hilltop", and "The Bucks Of Oranmore" (Traditional)
Lament
(uncredited)
includes "A Spailpín A Rún" (Traditional)
Blue Danube
(uncredited)
Written by Johann Strauss
Performed by Salonisti (as I Salonisti)
Orpheus
(uncredited)
Written by Jacques Offenbach
Performed by Salonisti (as I Salonisti)
Eternal Father Strong To Save
(uncredited)
Lyrics by William Whiting and music by John B. Dykes (uncredited))
Performed by Cast"""
    
    # Parse the soundtrack text
    print("Parsing soundtrack metadata...")
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
