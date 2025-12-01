#!/usr/bin/env python3
"""
Script to fetch Wikidata IDs for actors based on their IMDb IDs.
Reads actor_stats.xlsx, queries Wikidata SPARQL endpoint for each actor_id,
and adds wikidata_id and wikidata_label columns to the file.
"""

import pandas as pd
import requests
import time
from typing import Optional, Tuple

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

def query_wikidata_by_imdb_id(imdb_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Query Wikidata for an entity by its IMDb ID.
    
    Args:
        imdb_id: The IMDb ID (e.g., "nm0000138")
        
    Returns:
        Tuple of (wikidata_id, wikidata_label) or (None, None) if not found
    """
    query = f"""
    SELECT ?item ?itemLabel
    WHERE
    {{
      ?item wdt:P345 "{imdb_id}" .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
    }}
    """
    
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "IMDb4M Actor Stats Script/1.0 (https://github.com/imdb4m)"
    }
    
    try:
        response = requests.get(
            WIKIDATA_SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", {}).get("bindings", [])
        
        if results:
            # Get the first result
            item = results[0]
            item_uri = item.get("item", {}).get("value", "")
            item_label = item.get("itemLabel", {}).get("value", "")
            
            # Extract Q-number from URI (e.g., "http://www.wikidata.org/entity/Q44578" -> "Q44578")
            wikidata_id = item_uri.split("/")[-1] if item_uri else None
            
            return wikidata_id, item_label
        
        return None, None
        
    except requests.exceptions.RequestException as e:
        print(f"  Error querying Wikidata for {imdb_id}: {e}")
        return None, None


def main():
    # Load the Excel file
    input_file = "actor_stats.xlsx"
    print(f"Loading {input_file}...")
    df = pd.read_excel(input_file)
    
    print(f"Found {len(df)} actors to process")
    
    # Initialize new columns
    df["wikidata_id"] = None
    df["wikidata_label"] = None
    
    # Process each actor
    total = len(df)
    found_count = 0
    
    for idx, row in df.iterrows():
        actor_id = row["actor_id"]
        actor_name = row.get("actor_name", "Unknown")
        
        print(f"[{idx + 1}/{total}] Querying Wikidata for {actor_id} ({actor_name})...", end=" ")
        
        wikidata_id, wikidata_label = query_wikidata_by_imdb_id(actor_id)
        
        if wikidata_id:
            df.at[idx, "wikidata_id"] = wikidata_id
            df.at[idx, "wikidata_label"] = wikidata_label
            print(f"Found: {wikidata_id} - {wikidata_label}")
            found_count += 1
        else:
            print("Not found")
        
        # Rate limiting: wait 200ms between requests to be respectful to Wikidata
        time.sleep(0.2)
        
        # Save progress every 100 actors in case of interruption
        if (idx + 1) % 100 == 0:
            print(f"\n  [Checkpoint] Saving progress after {idx + 1} actors...")
            df.to_excel(input_file, index=False)
    
    # Save the final file
    print(f"\nSaving updated file to {input_file}...")
    df.to_excel(input_file, index=False)
    
    print(f"\nDone! Found Wikidata IDs for {found_count}/{total} actors ({found_count/total*100:.1f}%)")


if __name__ == "__main__":
    main()

