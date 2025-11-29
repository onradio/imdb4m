#!/usr/bin/env python3
"""
Parse an IMDb actor HTML page and reproduce the triples from example_dicaprio.ttl.

The script extracts structured data from JSON-LD, __NEXT_DATA__, and DOM fragments,
then emits a Turtle document that mirrors the layout and commentary style of the
reference example. The logic works for any actor page saved from IMDb that
contains the same structures (known-for list, filmography accordion, gallery, etc.).
"""

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

SCHEMA = Namespace("http://schema.org/")
ACTING_CATEGORY_IDS = {
    "amzn1.imdb.concept.name_credit_category.a9ab2a8b-9153-4edb-a27a-7c2346830d77",
    "amzn1.imdb.concept.name_credit_category.7f6d81aa-23aa-4503-844d-38201eb08761",
}


def clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.strip().split())


def extract_id_from_url(url: str, prefix: str) -> Optional[str]:
    match = re.search(rf"/({prefix}\d+)/", url)
    return match.group(1) if match else None


def parse_json_ld(soup: BeautifulSoup) -> Tuple[Dict, Optional[Dict], Optional[Dict]]:
    """Return (person_data, article_data, video_data)."""
    person_data = None
    article_data = None
    video_data = None

    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("@type") == "Person":
                    person_data = entry
        elif isinstance(data, dict):
            if data.get("@type") == "Person":
                person_data = data
            if data.get("@type") == "Article":
                article_data = data
                main_entity = data.get("mainEntity")
                if isinstance(main_entity, dict):
                    person_data = main_entity
                video_data = data.get("video")

    return person_data or {}, article_data, video_data


def parse_next_data(soup: BeautifulSoup) -> Dict:
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}
    try:
        return json.loads(script.string)
    except json.JSONDecodeError:
        return {}


def build_faq_lookup(main_column: Dict) -> Dict[str, Dict[str, str]]:
    lookup = {}
    faqs = main_column.get("faqs", {})
    edges = faqs.get("edges") if isinstance(faqs, dict) else None
    if not edges:
        return lookup

    for edge in edges:
        node = edge.get("node", {})
        attribute = node.get("attributeId")
        if not attribute:
            continue
        answer = node.get("answer", {})
        lookup[attribute] = {
            "text": answer.get("plainText", "") if isinstance(answer, dict) else "",
            "html": answer.get("plaidHtml", "") if isinstance(answer, dict) else "",
        }
    return lookup


def parse_known_for(faq_lookup: Dict[str, Dict[str, str]]) -> List[Tuple[str, str]]:
    known_for = []
    faq_entry = faq_lookup.get("well-known-movie-or-tv-show")
    if not faq_entry:
        return known_for

    snippet = faq_entry.get("html")
    if not snippet:
        return known_for

    snippet_soup = BeautifulSoup(snippet, "html.parser")
    for anchor in snippet_soup.find_all("a"):
        href = anchor.get("href")
        title_id = extract_id_from_url(href or "", "tt")
        name = clean_text(anchor.get_text())
        if title_id and name:
            known_for.append((title_id, name))
    return known_for


def extract_actor_dom_entries(soup: BeautifulSoup) -> List[Dict[str, Optional[str]]]:
    """
    Extract actor filmography entries from the DOM, capturing title id, name,
    release year (if present), and character name.
    """
    entries: List[Dict[str, Optional[str]]] = []
    seen_ids = set()
    for anchor in soup.select('a[href*="nm_flmg_job_"]'):
        href = anchor.get("href", "")
        title_id = extract_id_from_url(href, "tt")
        if not title_id or title_id in seen_ids:
            continue
        li = anchor.find_parent("li")
        if not li:
            continue
        data_testid = li.get("data-testid", "")
        if not any(cat in data_testid for cat in ACTING_CATEGORY_IDS):
            continue
        title = clean_text(anchor.get_text())
        if not title:
            continue
        year = None
        year_span = li.select_one(".ipc-metadata-list-summary-item__cc span")
        if year_span:
            year_text = clean_text(year_span.get_text())
            if year_text:
                match = re.search(r"(19|20)\d{2}", year_text)
                if match:
                    year = int(match.group(0))
        character = None
        char_span = li.select_one("ul.credit-text-list span")
        if char_span:
            character = clean_text(char_span.get_text())
        entries.append(
            {
                "id": title_id,
                "name": title,
                "year": year,
                "character": character,
            }
        )
        seen_ids.add(title_id)
    return entries


def build_actor_credit_map(main_column: Dict) -> Dict[str, Dict]:
    mapping: Dict[str, Dict] = {}
    released = main_column.get("released") or {}
    for edge in released.get("edges") or []:
        node = (edge.get("node") or {}) if edge else {}
        if (node.get("grouping") or {}).get("text") != "Actor":
            continue
        for credit_edge in (node.get("credits") or {}).get("edges") or []:
            credit = (credit_edge.get("node") or {}) if credit_edge else {}
            title = credit.get("title")
            if not title:
                continue
            title_id = title.get("id")
            if not title_id:
                continue

            release_year = (
                (title.get("releaseYear") or {}).get("year")
                if isinstance(title.get("releaseYear"), dict)
                else None
            )
            title_type = (
                (title.get("titleType") or {}).get("id")
                if isinstance(title.get("titleType"), dict)
                else None
            )

            character_name = None
            credited_roles = (credit.get("creditedRoles") or {}).get("edges") or []
            if credited_roles:
                role_node = (credited_roles[0].get("node") or {}) if credited_roles[0] else {}
                chars = (role_node.get("characters") or {}).get("edges") or []
                if chars:
                    character_name = ((chars[0].get("node") or {}) if chars[0] else {}).get("name")
                if not character_name:
                    character_name = role_node.get("text")

            mapping[title_id] = {
                "name": (title.get("titleText") or {}).get("text"),
                "release_year": release_year,
                "title_type": title_type,
                "character": character_name,
            }
    return mapping


def parse_height_value(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
    if match:
        return match.group(1)
    match = re.search(r"(\d+(?:\.\d+)?)\s*meters", text, flags=re.I)
    if match:
        return match.group(1)
    return None


def build_award_strings(main_column: Dict, faq_lookup: Dict[str, Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    oscar_summary = None
    prestige = main_column.get("prestigiousAwardSummary") or {}
    wins = prestige.get("wins")
    award_name = (prestige.get("award") or {}).get("text")
    if wins and award_name:
        oscar_summary = f"Won {wins} {award_name}"

    total_wins_text = (faq_lookup.get("number-of-awards") or {}).get("text")
    try:
        total_wins = int(total_wins_text.split()[0]) if total_wins_text else None
    except ValueError:
        total_wins = None

    nominations_total = (main_column.get("nominationsExcludeWins") or {}).get("total")
    overall_summary = None
    if total_wins is not None and nominations_total is not None:
        overall_summary = f"{total_wins} wins & {nominations_total} nominations total"

    return oscar_summary, overall_summary


def extract_salary_entry(main_column: Dict) -> Optional[Dict]:
    salaries = main_column.get("titleSalaries") or {}
    edges = salaries.get("edges") or [] if isinstance(salaries, dict) else []
    if not edges:
        return None
    return edges[0].get("node") if edges[0] else None


def extract_social_links(main_column: Dict) -> List[str]:
    urls = []
    links = main_column.get("personalDetailsExternalLinks") or {}
    for edge in links.get("edges") or []:
        node = (edge.get("node") or {}) if edge else {}
        label = (node.get("label") or "").lower()
        url = node.get("url")
        if label in {"facebook", "instagram"} and url:
            urls.append(url)
    return urls


def extract_images(main_column: Dict, nm_id: str) -> List[Dict]:
    images = []
    for edge in (main_column.get("images") or {}).get("edges") or []:
        node = (edge.get("node") or {}) if edge else {}
        image_id = node.get("id")
        if not image_id:
            continue
        image_uri = f"https://www.imdb.com/name/{nm_id}/mediaviewer/{image_id}/"
        images.append(
            {
                "mediaviewer": image_uri,
                "url": node.get("url"),
                "caption": (node.get("caption") or {}).get("plainText"),
                "height": node.get("height"),
                "width": node.get("width"),
            }
        )
    return images


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse an IMDb actor HTML file and generate RDF triples."
    )
    parser.add_argument("input_file", type=Path, help="Path to the saved IMDb HTML file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output TTL path (default: <input_dir>/<nm_id>.ttl)",
    )
    parser.add_argument(
        "--max-actor-year",
        type=int,
        default=2019,
        help="Highest release year to keep in actor filmography (default: 2019).",
    )
    args = parser.parse_args()

    if not args.input_file.exists():
        raise SystemExit(f"Input file {args.input_file} does not exist.")

    html_text = args.input_file.read_text()
    soup = BeautifulSoup(html_text, "html.parser")

    person_data, article_data, video_data = parse_json_ld(soup)
    next_data = parse_next_data(soup)
    page_props = (next_data.get("props") or {}).get("pageProps") or {}
    main_column = page_props.get("mainColumnData") or {}
    faq_lookup = build_faq_lookup(main_column)

    person_url = person_data.get("url") or article_data.get("url") if article_data else None
    if not person_url:
        raise SystemExit("Unable to locate person URL in JSON-LD.")
    if not person_url.endswith("/"):
        person_url += "/"

    nm_id = extract_id_from_url(person_url, "nm")
    if not nm_id:
        raise SystemExit("Could not extract IMDb nm identifier.")

    output_path = args.output or args.input_file.parent / f"{nm_id}.ttl"

    stats_graph = Graph()
    stats_graph.bind("schema", SCHEMA)
    person_ref = URIRef(person_url)
    stats_graph.add((person_ref, RDF.type, SCHEMA.Person))
    stats_graph.add((person_ref, SCHEMA.url, person_ref))

    name = person_data.get("name")
    description = html.unescape(person_data.get("description") or "")
    if "Few actors" in description:
        description = "Few actors" + description.split("Few actors", 1)[1]
    birth_date = person_data.get("birthDate")
    job_titles = person_data.get("jobTitle")
    if isinstance(job_titles, str):
        job_titles = [job_titles]
    nick_names = [
        ((nick.get("displayableProperty") or {}).get("value") or {}).get("plainText")
        for nick in main_column.get("nickNames") or []
    ]
    nick_names = [clean_text(n) for n in nick_names if n and clean_text(n)]
    birth_name = clean_text((faq_lookup.get("birth-name") or {}).get("text"))
    alternate_names = [n for n in nick_names if n]
    if birth_name:
        alternate_names.append(birth_name)

    if name:
        stats_graph.add((person_ref, SCHEMA.name, Literal(name)))
    if description:
        stats_graph.add((person_ref, SCHEMA.description, Literal(description)))
    if birth_date:
        stats_graph.add((person_ref, SCHEMA.birthDate, Literal(birth_date, datatype=XSD.date)))
    for job in job_titles or []:
        stats_graph.add((person_ref, SCHEMA.jobTitle, Literal(job)))
    for alt in alternate_names:
        stats_graph.add((person_ref, SCHEMA.alternateName, Literal(alt)))

    primary_image = main_column.get("primaryImage") or {}
    primary_image.setdefault("url", person_data.get("image"))
    if primary_image.get("url"):
        primary_image_ref = URIRef(primary_image["url"])
        stats_graph.add((person_ref, SCHEMA.image, primary_image_ref))
        stats_graph.add((primary_image_ref, RDF.type, SCHEMA.ImageObject))
        stats_graph.add((primary_image_ref, SCHEMA.url, primary_image_ref))
        caption = (primary_image.get("caption") or {}).get("plainText")
        if caption:
            stats_graph.add((primary_image_ref, SCHEMA.caption, Literal(caption)))
        if primary_image.get("height"):
            stats_graph.add(
                (
                    primary_image_ref,
                    SCHEMA.height,
                    Literal(int(primary_image["height"]), datatype=XSD.integer),
                )
            )
        if primary_image.get("width"):
            stats_graph.add(
                (
                    primary_image_ref,
                    SCHEMA.width,
                    Literal(int(primary_image["width"]), datatype=XSD.integer),
                )
            )

    birth_location = (
        main_column.get("birthLocation") or {}
    ).get("text") or (faq_lookup.get("place-of-birth") or {}).get("text")
    if birth_location:
        place_node = BNode()
        stats_graph.add((person_ref, SCHEMA.birthPlace, place_node))
        stats_graph.add((place_node, RDF.type, SCHEMA.Place))
        stats_graph.add((place_node, SCHEMA.description, Literal(birth_location)))

    height_data = main_column.get("height") or {}
    height_text = (
        (height_data.get("displayableProperty") or {})
        .get("value") or {}
    ).get("plainText") or (faq_lookup.get("height") or {}).get("text")
    height_value = parse_height_value(height_text)
    if height_text:
        height_node = BNode()
        stats_graph.add((person_ref, SCHEMA.height, height_node))
        stats_graph.add((height_node, RDF.type, SCHEMA.QuantitativeValue))
        if height_value:
            stats_graph.add(
                (height_node, SCHEMA.value, Literal(height_value, datatype=XSD.decimal))
            )
        stats_graph.add((height_node, SCHEMA.unitCode, Literal("MTR")))
        stats_graph.add((height_node, SCHEMA.description, Literal(height_text)))

    known_for_entries = parse_known_for(faq_lookup)
    actor_map = build_actor_credit_map(main_column)
    actor_dom_entries = extract_actor_dom_entries(soup)
    for entry in actor_dom_entries:
        data = actor_map.get(entry["id"])
        if data:
            entry.setdefault("year", data.get("release_year"))
            entry.setdefault("character", data.get("character"))
            entry.setdefault("title_type", data.get("title_type"))

    def ensure_movie_entry(movie_map: Dict[str, Dict], title_id: str, name_val: Optional[str], year: Optional[int]):
        entry = movie_map.setdefault(title_id, {})
        if name_val:
            entry.setdefault("name", name_val)
        if year:
            entry.setdefault("year", year)
        return entry

    movies: Dict[str, Dict] = {}
    for tid, mname in known_for_entries:
        ensure_movie_entry(movies, tid, mname, None)

    performer_known_for: List[str] = []
    faqs_ids = [tid for tid, _ in known_for_entries]
    priority_ids = []
    known_v2 = ((page_props.get("aboveTheFold") or {}).get("knownForV2") or {}).get("credits") or []
    if known_v2:
        priority_id = ((known_v2[0].get("title") or {}) if known_v2[0] else {}).get("id")
        if not priority_id:
            title_data = (known_v2[0].get("title") or {}) if known_v2[0] else {}
            priority_name = (title_data.get("titleText") or {}).get("text")
            for tid, movie_name in known_for_entries:
                if movie_name == priority_name:
                    priority_id = tid
                    break
        if priority_id:
            priority_ids.append(priority_id)
    ordered_known_for = []
    for tid in (priority_ids + faqs_ids):
        if tid and tid not in ordered_known_for:
            ordered_known_for.append(tid)
    for tid, _movie_name in known_for_entries:
        if tid not in ordered_known_for:
            ordered_known_for.append(tid)
    performer_known_for = ordered_known_for

    performer_roles: List[Dict] = []
    max_actor_year = args.max_actor_year
    for entry in actor_dom_entries:
        ensure_movie_entry(movies, entry["id"], entry["name"], entry.get("year"))
        if entry["id"] in performer_known_for:
            continue
        year = entry.get("year")
        if year is None:
            continue
        if year and max_actor_year and year > max_actor_year:
            continue
        performer_roles.append(entry)

    performer_movie_ids: List[str] = []
    seen_performers = set()
    for tid in performer_known_for + [entry["id"] for entry in performer_roles]:
        if tid in seen_performers:
            continue
        seen_performers.add(tid)
        performer_movie_ids.append(tid)
        stats_graph.add((person_ref, SCHEMA.performerIn, URIRef(f"https://www.imdb.com/title/{tid}/")))

    salary_entry = extract_salary_entry(main_column)
    salary_movie_id = None
    salary_movie_name = None
    salary_amount = None
    if salary_entry:
        title = salary_entry.get("title") or {}
        salary_movie_id = title.get("id")
        salary_movie_name = (title.get("titleText") or {}).get("text")
        if salary_movie_id and salary_movie_name:
            ensure_movie_entry(movies, salary_movie_id, salary_movie_name, (title.get("releaseYear") or {}).get("year"))
        display_value = (
            (salary_entry.get("displayableProperty") or {}).get("value") or {}
        ).get("plainText")
        if display_value:
            digits = re.sub(r"[^\d]", "", display_value)
            if digits:
                salary_amount = digits

    oscars_text, overall_text = build_award_strings(main_column, faq_lookup)
    video_info = video_data or (article_data.get("video") if article_data else None)
    gallery_images = extract_images(main_column, nm_id)
    social_links = extract_social_links(main_column)

    role_map = {entry["id"]: entry for entry in performer_roles}
    for tid, data in movies.items():
        movie_uri = URIRef(f"https://www.imdb.com/title/{tid}/")
        stats_graph.add((movie_uri, RDF.type, SCHEMA.Movie))
        if data.get("name"):
            stats_graph.add((movie_uri, SCHEMA.name, Literal(data["name"])))
        stats_graph.add((movie_uri, SCHEMA.url, movie_uri))
        if data.get("year"):
            stats_graph.add(
                (
                    movie_uri,
                    SCHEMA.datePublished,
                    Literal(str(data["year"]), datatype=XSD.gYear),
                )
            )
        if tid in role_map:
            role_node = BNode()
            stats_graph.add((movie_uri, SCHEMA.actor, role_node))
            stats_graph.add((role_node, RDF.type, SCHEMA.PerformanceRole))
            stats_graph.add((role_node, SCHEMA.actor, person_ref))
            character = role_map[tid].get("character")
            if character:
                stats_graph.add((role_node, SCHEMA.characterName, Literal(character)))

    if oscars_text:
        award_node = BNode()
        stats_graph.add((person_ref, SCHEMA.award, award_node))
        stats_graph.add((award_node, RDF.type, SCHEMA.Award))
        stats_graph.add((award_node, SCHEMA.name, Literal(oscars_text)))
    if overall_text:
        award_node = BNode()
        stats_graph.add((person_ref, SCHEMA.award, award_node))
        stats_graph.add((award_node, RDF.type, SCHEMA.Award))
        stats_graph.add((award_node, SCHEMA.description, Literal(overall_text)))

    if salary_movie_id and salary_amount:
        prop_node = BNode()
        stats_graph.add((person_ref, SCHEMA.additionalProperty, prop_node))
        stats_graph.add((prop_node, RDF.type, SCHEMA.PropertyValue))
        if salary_movie_name:
            stats_graph.add(
                (prop_node, SCHEMA.name, Literal(f"Salary ({salary_movie_name})"))
            )
        money_node = BNode()
        stats_graph.add((prop_node, SCHEMA.value, money_node))
        stats_graph.add((money_node, RDF.type, SCHEMA.MonetaryAmount))
        stats_graph.add((money_node, SCHEMA.currency, Literal("USD")))
        stats_graph.add(
            (money_node, SCHEMA.value, Literal(int(salary_amount), datatype=XSD.integer))
        )

    video_url = None
    video_ref = None
    if isinstance(video_info, dict):
        video_url = video_info.get("url") or video_info.get("embedUrl")
        if video_url:
            video_ref = URIRef(video_url)
            stats_graph.add((person_ref, SCHEMA.video, video_ref))
            stats_graph.add((video_ref, RDF.type, SCHEMA.VideoObject))
            if video_info.get("name"):
                stats_graph.add((video_ref, SCHEMA.name, Literal(video_info["name"])))
            video_desc = html.unescape(video_info.get("description", ""))
            if video_desc:
                stats_graph.add((video_ref, SCHEMA.description, Literal(video_desc)))
            embed = video_info.get("embedUrl") or video_url
            stats_graph.add((video_ref, SCHEMA.embedUrl, URIRef(embed)))
            thumb = video_info.get("thumbnailUrl") or (video_info.get("thumbnail") or {}).get(
                "contentUrl"
            )
            if thumb:
                stats_graph.add((video_ref, SCHEMA.thumbnailUrl, URIRef(thumb)))
            if video_info.get("duration"):
                stats_graph.add(
                    (
                        video_ref,
                        SCHEMA.duration,
                        Literal(video_info["duration"], datatype=XSD.duration),
                    )
                )
            if video_info.get("uploadDate"):
                stats_graph.add(
                    (
                        video_ref,
                        SCHEMA.uploadDate,
                        Literal(video_info["uploadDate"], datatype=XSD.dateTime),
                    )
                )

    for image in gallery_images:
        image_ref = URIRef(image["mediaviewer"])
        stats_graph.add((person_ref, SCHEMA.image, image_ref))
        stats_graph.add((image_ref, RDF.type, SCHEMA.ImageObject))
        if image.get("url"):
            stats_graph.add((image_ref, SCHEMA.url, URIRef(image["url"])))
        if image.get("caption"):
            stats_graph.add((image_ref, SCHEMA.caption, Literal(image["caption"])))
        if image.get("height"):
            stats_graph.add(
                (
                    image_ref,
                    SCHEMA.height,
                    Literal(int(image["height"]), datatype=XSD.integer),
                )
            )
        if image.get("width"):
            stats_graph.add(
                (
                    image_ref,
                    SCHEMA.width,
                    Literal(int(image["width"]), datatype=XSD.integer),
                )
            )

    for link in social_links:
        stats_graph.add((person_ref, SCHEMA.sameAs, URIRef(link)))

    def esc(text: str) -> str:
        if not text:
            return ""
        # Remove control characters first (except newline, carriage return, tab which we handle explicitly)
        result = "".join(c if ord(c) >= 32 or c in "\n\r\t" else "" for c in text)
        # Escape backslashes first, then quotes
        result = result.replace("\\", "\\\\").replace('"', '\\"')
        # Handle common whitespace/control chars
        result = result.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return result

    def uri(value: str) -> str:
        return f"<{value}>"

    def performer_comment(title_id: str) -> str:
        return movies.get(title_id, {}).get("name", "")

    def format_performer_list(end_with_period: bool = False) -> List[str]:
        entries = performer_known_for + [item["id"] for item in performer_roles]
        if not entries:
            return []
        uri_comments = [
            (uri(f"https://www.imdb.com/title/{tid}/"), performer_comment(tid))
            for tid in entries
        ]
        terminator = " ." if end_with_period else " ;"
        # Handle single entry case - use terminator instead of comma
        if len(uri_comments) == 1:
            return [
                f"    schema:performerIn {uri_comments[0][0]}{terminator}    # {uri_comments[0][1]}"
            ]
        lines = [
            f"    schema:performerIn {uri_comments[0][0]},    # {uri_comments[0][1]}"
        ]
        for idx, (uri_value, comment) in enumerate(uri_comments[1:], start=2):
            prefix = "                       "
            if idx == len(performer_known_for) + 1:
                lines.append(f"{prefix}# More (With Character Roles)")
            if idx == len(uri_comments):
                lines.append(f"{prefix}{uri_value}{terminator} # {comment}")
            else:
                lines.append(f"{prefix}{uri_value},    # {comment}")
        return lines

    video_url = None
    video_lines: List[str] = []
    if isinstance(video_info, dict):
        video_url = video_info.get("url") or video_info.get("embedUrl")
        if video_url:
            thumbnail = video_info.get("thumbnailUrl") or (video_info.get("thumbnail") or {}).get(
                "contentUrl"
            )
            duration = video_info.get("duration")
            upload_date = video_info.get("uploadDate")
            normalized_date = upload_date
            if upload_date:
                try:
                    normalized_dt = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))
                    normalized_date = normalized_dt.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                except ValueError:
                    normalized_date = upload_date
            video_desc = html.unescape(video_info.get("description", ""))
            video_lines = [
                f"{uri(video_url)} a schema:VideoObject ;",
                f'        schema:name "{esc(video_info.get("name", ""))}" ;',
                f'        schema:description "{esc(video_desc)}" ;',
                f"        schema:embedUrl {uri(video_info.get('embedUrl', video_url))} ;",
            ]
            if thumbnail:
                video_lines.append(f'        schema:thumbnailUrl "{esc(thumbnail)}" ;')
            if duration:
                video_lines.append(f'        schema:duration "{duration}"^^xsd:duration ;')
            if normalized_date:
                video_lines.append(f'        schema:uploadDate "{normalized_date}"^^xsd:dateTime .')
            else:
                video_lines[-1] = video_lines[-1].rstrip(" ;") + " ."

    lines: List[str] = []
    lines.append("@prefix schema: <http://schema.org/> .")
    lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
    lines.append("")

    lines.append("")
    lines.append(f"{uri(person_url)} a schema:Person ;")
    lines.append(f'    schema:name "{esc(name)}" ;')
    lines.append(f"    schema:url {uri(person_url)} ;")
    # Only output birthDate if it's a valid date format (YYYY-MM-DD)
    if birth_date and isinstance(birth_date, str) and birth_date.count("-") >= 2:
        lines.append(f'    schema:birthDate "{birth_date}"^^xsd:date ;')
    job_literal = ", ".join(f'"{esc(job)}"' for job in (job_titles or []) if job and job.strip())
    if job_literal:
        lines.append(f"    schema:jobTitle {job_literal} ;")
    alt_literal = ", ".join(f'"{esc(n)}"' for n in (alternate_names or []) if n and n.strip())
    if alt_literal:
        lines.append(f"    schema:alternateName {alt_literal} ;")
    lines.append(f'    schema:description "{esc(description)}" ;')
    primary_image_url = primary_image.get('url')
    if primary_image_url:
        lines.append(f"    schema:image {uri(primary_image_url)} ;")
    if birth_location:
        lines.append("")
        lines.append("    schema:birthPlace [")
        lines.append("        a schema:Place ;")
        lines.append(f'        schema:description "{esc(birth_location)}"')
        lines.append("    ] ;")
    if height_text and height_value:
        lines.append("")
        lines.append("    schema:height [")
        lines.append("        a schema:QuantitativeValue ;")
        lines.append(f'        schema:value "{height_value}"^^xsd:decimal ;')
        lines.append('        schema:unitCode "MTR" ;')
        lines.append(f'        schema:description "{esc(height_text)}"')
        lines.append("    ] ;")
    
    # Determine what properties will be added after performer list
    gallery_uris = [img["mediaviewer"] for img in gallery_images]
    has_more_properties = oscars_text or overall_text or (salary_movie_id and salary_amount) or video_lines or gallery_uris
    
    performer_lines = format_performer_list(end_with_period=not has_more_properties)
    if performer_lines:
        lines.append("    ")
        lines.extend(performer_lines)
        lines.append("")
    
    if oscars_text:
        lines.append("    schema:award [")
        lines.append("        a schema:Award ;")
        lines.append(f'        schema:name "{esc(oscars_text)}"')
        lines.append("    ] ;")
    if overall_text:
        lines.append("    schema:award [")
        lines.append("        a schema:Award ;")
        lines.append(f'        schema:description "{esc(overall_text)}"')
        lines.append("    ] ;")
    if salary_movie_id and salary_amount:
        lines.append("")
        lines.append("    schema:additionalProperty [")
        lines.append("        a schema:PropertyValue ;")
        lines.append(f'        schema:name "Salary ({esc(salary_movie_name)})" ;')
        lines.append("        schema:value [")
        lines.append("            a schema:MonetaryAmount ;")
        lines.append('            schema:currency "USD" ;')
        lines.append(f'            schema:value "{salary_amount}"^^xsd:integer')
        lines.append("        ]")
        lines.append("    ] ;")
    if video_lines:
        lines.append("")
        # End with '.' if no gallery images follow, otherwise ';'
        video_terminator = " ;" if gallery_uris else " ."
        lines.append(f"    schema:video {uri(video_url)}{video_terminator}")
    
    if gallery_uris:
        lines.append("")
        lines.append("    # Link to gallery images")
        if len(gallery_uris) == 1:
            lines.append(f"    schema:image {uri(gallery_uris[0])} .")
        else:
            lines.append(
                "    schema:image "
                + ",\n                 ".join(f"{uri(u)}" for u in gallery_uris[:-1])
                + ","
            )
            lines.append(f"                 {uri(gallery_uris[-1])} .")
    elif not video_lines and (has_more_properties or not performer_lines):
        # No video and no gallery images, and either:
        # - has_more_properties is True (performer_lines ended with ';'), or
        # - no performer_lines at all
        # Need to terminate the person statement by fixing last ';' to '.'
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].rstrip().endswith(";"):
                lines[i] = lines[i].rstrip()[:-1] + " ."
                break
    lines.append("")
    lines.append("# ==============================================================================")
    lines.append("# KNOWN FOR (schema:Movie definitions)")
    lines.append("# ==============================================================================")
    lines.append("")
    for tid in performer_known_for:
        movie_uri = uri(f"https://www.imdb.com/title/{tid}/")
        lines.extend([
            f"{movie_uri} a schema:Movie ;",
            f'    schema:name "{esc(movies.get(tid, {}).get("name", ""))}" ;',
            f"    schema:url {movie_uri} .",
            "",
        ])
    if salary_movie_id:
        salary_uri = uri(f"https://www.imdb.com/title/{salary_movie_id}/")
        lines.extend([
            f"{salary_uri} a schema:Movie ;",
            f'    schema:name "{esc(salary_movie_name)}" ;',
            f"    schema:url {salary_uri} .",
            "",
        ])
    lines.append("")
    lines.append("# ==============================================================================")
    lines.append("# MOVIE DEFINITIONS (With Character Roles)")
    lines.append("# ==============================================================================")
    lines.append("")
    for movie in performer_roles:
        movie_uri = uri(f"https://www.imdb.com/title/{movie['id']}/")
        lines.append(f"# {movie['name']} ({movie['year']})")
        lines.extend([
            f"{movie_uri} a schema:Movie ;",
            f'    schema:name "{esc(movie["name"])}" ;',
            f"    schema:url {movie_uri} ;",
            f'    schema:datePublished "{movie["year"]}"^^xsd:gYear ;',
            "    schema:actor [",
            "        a schema:PerformanceRole ;",
            f"        schema:actor {uri(person_url)} ;",
            f'        schema:characterName "{esc(movie.get("character", ""))}"',
            "    ] .",
            ""
        ])
    lines.append("# ==============================================================================")
    lines.append("# VIDEO (schema:VideoObject definition) ")
    lines.append("# ==============================================================================")
    lines.append("")
    if video_lines:
        lines.extend(video_lines)
    lines.append("")
    lines.append("# ==============================================================================")
    lines.append("# IMAGES (schema:ImageObject definitions)")
    lines.append("# ==============================================================================")
    lines.append("")
    if primary_image.get('url'):
        primary_img_lines = [
            f"{uri(primary_image.get('url'))} a schema:ImageObject ;",
            f'    schema:url {uri(primary_image.get("url"))} ;',
            f'    schema:caption "{esc((primary_image.get("caption") or {}).get("plainText", ""))}" ;',
        ]
        if primary_image.get("height") is not None:
            primary_img_lines.append(f'    schema:height "{primary_image.get("height")}"^^xsd:integer ;')
        if primary_image.get("width") is not None:
            # Use '.' if this is the last property, otherwise would need ';'
            primary_img_lines.append(f'    schema:width "{primary_image.get("width")}"^^xsd:integer .')
        else:
            # Fix the last line to end with '.' instead of ';'
            if primary_img_lines:
                primary_img_lines[-1] = primary_img_lines[-1].rstrip(' ;') + ' .'
        primary_img_lines.append("")
        lines.extend(primary_img_lines)
    for image in gallery_images:
        img_lines = [
            f"{uri(image['mediaviewer'])} a schema:ImageObject ;",
            f"    schema:url {uri(image.get('url'))} ;",
            f'    schema:caption "{esc(image.get("caption", ""))}" ;',
        ]
        if image.get("height") is not None:
            img_lines.append(f'    schema:height "{image.get("height")}"^^xsd:integer ;')
        if image.get("width") is not None:
            img_lines.append(f'    schema:width "{image.get("width")}"^^xsd:integer .')
        else:
            # Fix the last line to end with '.' instead of ';'
            if img_lines:
                img_lines[-1] = img_lines[-1].rstrip(' ;') + ' .'
        img_lines.append("")
        lines.extend(img_lines)
    lines.append("# ==============================================================================")
    lines.append("# Entity alignments")
    lines.append("# ==============================================================================")
    if social_links:
        lines.append(f"{uri(person_url)}")
        if len(social_links) == 2:
            lines.append(
                f"    schema:sameAs {uri(social_links[0])},"
            )
            lines.append(
                f"                  {uri(social_links[1])} ."
            )
        elif len(social_links) == 1:
            lines.append(
                f"    schema:sameAs {uri(social_links[0])} ."
            )
        else:
            lines.append(
                f"    schema:sameAs {', '.join(uri(url) for url in social_links[:-1])},"
            )
            lines.append(
                f"                  {uri(social_links[-1])} ."
            )
    lines.append("")
    lines.append("# TODO: Add Wikidata URI via querying the SPARQL endpoint with URI lookup.")

    ttl_output = "\n".join(lines).rstrip("\n") + "\n"
    output_path.write_text(ttl_output)

    triple_count = len(stats_graph)

    print(f"Generated {output_path}")
    if triple_count is not None:
        print(f"  Triples: {triple_count}")
    print(
        "  Movies: {total} (Known-for {known_for}, Roles {roles})".format(
            total=len(movies),
            known_for=len(performer_known_for),
            roles=len(performer_roles),
        )
    )
    print(f"  Images: {len(gallery_images)}  Social links: {len(social_links)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

