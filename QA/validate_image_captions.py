#!/usr/bin/env python3
"""
Image Caption Validator

Opens each image from qa_results.json and prompts for validation in the terminal.
If rejected, the image entry is removed from the JSON.
"""

import json
import webbrowser
from pathlib import Path


def load_json(json_path: Path) -> dict:
    """Load the JSON data from file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(json_path: Path, data: dict):
    """Save the modified JSON data back to file."""
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def collect_image_entries(data: dict) -> list:
    """
    Collect all image entries from the JSON.
    Returns a list of tuples: (movie_id, image_url, caption)
    """
    entries = []
    question_key = "Which are the images of the movie and their captions?"
    
    for movie_id, questions in data.items():
        if question_key in questions:
            html_images = questions[question_key].get("html", [])
            for img_data in html_images:
                if isinstance(img_data, list) and len(img_data) >= 2:
                    image_url, caption = img_data[0], img_data[1]
                    entries.append((movie_id, image_url, caption))
    
    return entries


def remove_image_entry(data: dict, movie_id: str, image_url: str, caption: str):
    """Remove a specific image entry from the data."""
    question_key = "Which are the images of the movie and their captions?"
    html_images = data[movie_id][question_key]["html"]
    
    for i, img_data in enumerate(html_images):
        if isinstance(img_data, list) and len(img_data) >= 2:
            if img_data[0] == image_url and img_data[1] == caption:
                html_images.pop(i)
                return True
    return False


def print_header():
    """Print a nice header."""
    print("\n" + "=" * 60)
    print("🎬  IMAGE CAPTION VALIDATOR")
    print("=" * 60)
    print("\nCommands:")
    print("  y/Y/Enter = Yes, caption is correct (keep)")
    print("  n/N       = No, caption is wrong (remove)")
    print("  s/S       = Skip this image")
    print("  q/Q       = Save and quit")
    print("=" * 60 + "\n")


def main():
    json_path = Path(__file__).parent / "qa_results.json"
    
    if not json_path.exists():
        print(f"Error: JSON file not found at {json_path}")
        return
    
    print_header()
    
    data = load_json(json_path)
    entries = collect_image_entries(data)
    
    if not entries:
        print("No image entries found in the JSON file.")
        return
    
    print(f"Found {len(entries)} images to validate.\n")
    
    kept_count = 0
    removed_count = 0
    skipped_count = 0
    
    for i, (movie_id, image_url, caption) in enumerate(entries):
        print("-" * 60)
        print(f"\n📷 Image {i + 1} of {len(entries)}")
        print(f"🎬 Movie: {movie_id}")
        print(f"📝 Caption: \"{caption}\"")
        print(f"\n   Stats: ✓ Kept: {kept_count} | ✗ Removed: {removed_count} | → Skipped: {skipped_count}")
        print()
        
        # Open image in browser
        webbrowser.open(image_url)
        
        while True:
            try:
                response = input("Is the caption correct? [Y/n/s/q]: ").strip().lower()
            except EOFError:
                response = 'q'
            except KeyboardInterrupt:
                print("\n\nInterrupted. Saving...")
                response = 'q'
            
            if response in ('', 'y', 'yes'):
                print("   ✓ Kept")
                kept_count += 1
                break
            elif response in ('n', 'no'):
                remove_image_entry(data, movie_id, image_url, caption)
                print("   ✗ Removed from JSON")
                removed_count += 1
                # Auto-save every 5 removals
                if removed_count % 5 == 0:
                    save_json(json_path, data)
                    print("   💾 Auto-saved")
                break
            elif response in ('s', 'skip'):
                print("   → Skipped")
                skipped_count += 1
                break
            elif response in ('q', 'quit', 'exit'):
                save_json(json_path, data)
                print("\n" + "=" * 60)
                print("💾 Changes saved!")
                print(f"\nFinal stats:")
                print(f"   ✓ Kept:    {kept_count}")
                print(f"   ✗ Removed: {removed_count}")
                print(f"   → Skipped: {skipped_count}")
                print("=" * 60 + "\n")
                return
            else:
                print("   Invalid input. Please enter y, n, s, or q.")
    
    # Finished all images
    save_json(json_path, data)
    print("\n" + "=" * 60)
    print("🎉 All images reviewed!")
    print("💾 Changes saved!")
    print(f"\nFinal stats:")
    print(f"   ✓ Kept:    {kept_count}")
    print(f"   ✗ Removed: {removed_count}")
    print(f"   → Skipped: {skipped_count}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
