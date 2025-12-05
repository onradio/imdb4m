#!/usr/bin/env python3
"""
Analyze IMDb soundtrack HTML files to extract all property variations
and ensure the property mapping covers all cases.
"""

import os
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
from collections import Counter, defaultdict

# Import the comprehensive property mapping
from soundtrack_property_mapping import (
    PROPERTY_MAPPING, 
    COMPOUND_ROLES, 
    SCHEMA_ORG_MAPPING,
    normalize_label,
    categorize_label,
    get_compound_roles
)


def extract_soundtrack_data_from_next_data(html_content):
    """
    Extract soundtrack data from __NEXT_DATA__ JSON embedded in HTML.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    next_data_script = soup.find('script', id='__NEXT_DATA__')
    
    if not next_data_script:
        return None
    
    try:
        next_data = json.loads(next_data_script.string)
        content_data = next_data.get('props', {}).get('pageProps', {}).get('contentData', {})
        return content_data
    except json.JSONDecodeError:
        return None


def extract_soundtrack_entries(content_data):
    """
    Extract soundtrack entries from the content data.
    """
    if not content_data:
        return []
    
    section = content_data.get('section', {})
    items = section.get('items', [])
    
    return items


def extract_property_labels(soundtrack_items):
    """
    Extract all property labels from soundtrack items.
    Returns a list of (label, value) tuples.
    """
    properties = []
    
    for item in soundtrack_items:
        # Get the text content which contains the song info
        text = item.get('text', '')
        
        # Also check for attributes list
        attributes = item.get('attributes', [])
        
        for attr in attributes:
            if isinstance(attr, dict):
                label = attr.get('label', '')
                if label:
                    properties.append(label)
            elif isinstance(attr, str):
                # Try to extract label from string format "Label: Value"
                if ':' in attr:
                    label = attr.split(':')[0].strip()
                    properties.append(label)
    
    return properties


def find_property_patterns_in_text(text):
    """
    Find property patterns in free text format.
    Common patterns: "Property by Name" or "Property: Name"
    """
    patterns_found = []
    
    # Common patterns to look for
    property_patterns = [
        r'(Music by)',
        r'(Lyrics by)',
        r'(Written by)',
        r'(Performed by)',
        r'(Produced by)',
        r'(Arranged by)',
        r'(Conducted by)',
        r'(Orchestrated by)',
        r'(Sung by)',
        r'(Vocals by)',
        r'(Composed by)',
        r'(Score by)',
        r'(Words by)',
        r'(Mixed by)',
        r'(Engineered by)',
        r'(Remixed by)',
        r'(Programming by)',
        r'(Additional[\s\w]+ by)',
        r'([\w\s]+ by)',  # Catch-all for "X by" patterns
    ]
    
    for pattern in property_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        patterns_found.extend(matches)
    
    return patterns_found


def analyze_html_file(filepath):
    """
    Analyze a single HTML file and extract all property labels.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return [], []
    
    content_data = extract_soundtrack_data_from_next_data(html_content)
    
    if not content_data:
        return [], []
    
    soundtrack_items = extract_soundtrack_entries(content_data)
    
    # Extract structured labels
    labels = []
    raw_texts = []
    
    for item in soundtrack_items:
        # Check listContent for labels
        list_content = item.get('listContent', [])
        for entry in list_content:
            if isinstance(entry, dict):
                # Look for text fields that contain property patterns
                text = entry.get('text', '')
                html = entry.get('html', '')
                plain_text = entry.get('plainText', '')
                
                for t in [text, html, plain_text]:
                    if t:
                        raw_texts.append(t)
                        patterns = find_property_patterns_in_text(t)
                        labels.extend(patterns)
    
    return labels, raw_texts


def categorize_label_simple(label):
    """
    Simplified wrapper for categorize_label that returns (category, matched).
    """
    category, matched, is_compound = categorize_label(label)
    return category, matched


def main():
    """
    Main function to analyze all soundtrack HTML files.
    """
    base_dir = Path('/home/ioannis/PycharmProjects/imdb4m/extractor/movies')
    
    # Find all soundtrack HTML files
    sound_files = list(base_dir.glob('**/movie_soundtrack/*_sound.html'))
    
    print(f"Found {len(sound_files)} soundtrack HTML files to analyze\n")
    
    # Counters for analysis
    all_labels = Counter()
    unmatched_labels = Counter()
    category_counts = Counter()
    sample_texts = defaultdict(list)
    
    files_processed = 0
    files_with_data = 0
    
    for filepath in sound_files:
        labels, raw_texts = analyze_html_file(filepath)
        files_processed += 1
        
        if labels or raw_texts:
            files_with_data += 1
        
        for label in labels:
            normalized = normalize_label(label)
            all_labels[normalized] += 1
            
        category, matched = categorize_label_simple(label)
        if matched:
            category_counts[category] += 1
        else:
            unmatched_labels[normalized] += 1
        
        # Store sample texts for analysis
        for text in raw_texts[:5]:  # Keep first 5 samples per file
            sample_texts[str(filepath)].append(text[:200])  # Truncate long texts
        
        if files_processed % 50 == 0:
            print(f"Processed {files_processed}/{len(sound_files)} files...")
    
    print(f"\n{'='*60}")
    print("ANALYSIS RESULTS")
    print(f"{'='*60}\n")
    
    print(f"Files processed: {files_processed}")
    print(f"Files with soundtrack data: {files_with_data}\n")
    
    print(f"{'='*60}")
    print("ALL PROPERTY LABELS FOUND (sorted by frequency)")
    print(f"{'='*60}\n")
    
    for label, count in all_labels.most_common():
        category, matched = categorize_label_simple(label)
        compound_roles = get_compound_roles(label)
        if compound_roles:
            status = f"-> {', '.join(compound_roles)} (compound)"
        elif matched:
            status = f"-> {category}"
        else:
            status = "** UNMATCHED **"
        print(f"  {count:4d}x  {label:40s} {status}")
    
    print(f"\n{'='*60}")
    print("UNMATCHED LABELS (need to add to mapping)")
    print(f"{'='*60}\n")
    
    if unmatched_labels:
        for label, count in unmatched_labels.most_common():
            print(f"  {count:4d}x  {label}")
    else:
        print("  All labels are covered by the current mapping!")
    
    print(f"\n{'='*60}")
    print("CATEGORY DISTRIBUTION")
    print(f"{'='*60}\n")
    
    for category, count in category_counts.most_common():
        print(f"  {category:20s}: {count:5d}")
    
    print(f"\n{'='*60}")
    print("SAMPLE RAW TEXTS (first few files)")
    print(f"{'='*60}\n")
    
    sample_count = 0
    for filepath, texts in list(sample_texts.items())[:5]:
        print(f"\nFile: {Path(filepath).name}")
        for text in texts[:3]:
            print(f"  - {text[:100]}...")
        sample_count += 1
    
    # Save detailed results to file
    results_file = base_dir.parent / 'soundtrack_property_analysis.txt'
    with open(results_file, 'w', encoding='utf-8') as f:
        f.write("SOUNDTRACK PROPERTY ANALYSIS RESULTS\n")
        f.write("="*60 + "\n\n")
        
        f.write(f"Files processed: {files_processed}\n")
        f.write(f"Files with soundtrack data: {files_with_data}\n\n")
        
        f.write("ALL LABELS FOUND:\n")
        f.write("-"*40 + "\n")
        for label, count in all_labels.most_common():
            category, matched = categorize_label_simple(label)
            compound_roles = get_compound_roles(label)
            if compound_roles:
                status = f"-> {', '.join(compound_roles)} (compound)"
            elif matched:
                status = f"-> {category}"
            else:
                status = "** UNMATCHED **"
            f.write(f"{count:4d}x  {label:40s} {status}\n")
        
        f.write("\n\nUNMATCHED LABELS:\n")
        f.write("-"*40 + "\n")
        for label, count in unmatched_labels.most_common():
            f.write(f"{count:4d}x  {label}\n")
    
    print(f"\nDetailed results saved to: {results_file}")


if __name__ == '__main__':
    main()

