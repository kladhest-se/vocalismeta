# coding: utf-8
"""Pure helpers for the public Ljudboksarkivet audiobook catalogue."""

from __future__ import unicode_literals

import json
import re


BASE_URL = 'https://ljudboksarkivet.se'
SITEMAP_URL = BASE_URL + '/sitemap.xml'
BOOK_PATH = '/ljudbok/'

try:
    text_type = unicode
except NameError:  # pragma: no cover - Python 3 only
    text_type = str


def to_text(value):
    if value is None:
        return ''
    if isinstance(value, text_type):
        return value
    try:
        return value.decode('utf-8', 'replace')
    except AttributeError:
        return text_type(value)


def decode_entities(value):
    value = to_text(value)
    replacements = (
        ('&amp;', '&'), ('&quot;', '"'), ('&#39;', "'"),
        ('&apos;', "'"), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' '),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return re.sub(
        r'&#(?:x([0-9a-fA-F]+)|([0-9]+));',
        lambda match: text_type(chr(int(
            match.group(1) or match.group(2),
            16 if match.group(1) else 10,
        ))),
        value,
    )


def clean_text(value):
    value = re.sub(r'<[^>]+>', ' ', to_text(value))
    return re.sub(r'\s+', ' ', decode_entities(value)).strip()


def slugify(value):
    value = to_text(value).lower()
    replacements = (
        ('å', 'a'), ('ä', 'a'), ('á', 'a'), ('à', 'a'), ('â', 'a'),
        ('æ', 'ae'), ('ö', 'o'), ('ó', 'o'), ('ò', 'o'), ('ô', 'o'),
        ('ø', 'o'), ('é', 'e'), ('è', 'e'), ('ê', 'e'), ('ë', 'e'),
        ('í', 'i'), ('ì', 'i'), ('î', 'i'), ('ï', 'i'), ('ü', 'u'),
        ('ú', 'u'), ('ù', 'u'), ('û', 'u'), ('ç', 'c'), ('ñ', 'n'),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')


def book_url(slug):
    slug = re.sub(r'[^a-z0-9-]+', '', to_text(slug).lower()).strip('-')
    return BASE_URL + BOOK_PATH + slug if slug else ''


def sitemap_urls(payload):
    values = []
    for match in re.findall(r'<loc>([^<]+)</loc>', to_text(payload), re.I):
        url = decode_entities(match).strip()
        if re.search(r'/sitemap-books-[0-9]+\.xml$', url) and url not in values:
            values.append(url)
    return values


def book_slugs(payload):
    values = []
    seen = set()
    for match in re.findall(r'<loc>([^<]+)</loc>', to_text(payload), re.I):
        url = decode_entities(match).strip().rstrip('/')
        if BOOK_PATH not in url:
            continue
        slug = url.split(BOOK_PATH, 1)[1].split('?', 1)[0].strip('/')
        if slug and slug not in seen:
            seen.add(slug)
            values.append(slug)
    return values


def slug_score(wanted, candidate):
    if not wanted or not candidate:
        return 0
    if wanted == candidate:
        return 100
    if candidate.startswith(wanted + '-'):
        return 92
    if wanted.startswith(candidate + '-'):
        return 88
    wanted_tokens = set(wanted.split('-'))
    candidate_tokens = set(candidate.split('-'))
    common = len(wanted_tokens.intersection(candidate_tokens))
    total = max(len(wanted_tokens), len(candidate_tokens))
    if not common or not total:
        return 0
    score = int((100.0 * common) / total)
    if wanted_tokens and wanted_tokens.issubset(candidate_tokens):
        score = max(score, 82)
    return score


def candidate_slugs(title, slugs, limit=6):
    wanted = slugify(title)
    ranked = []
    for index in range(len(slugs or [])):
        slug = to_text(slugs[index]).strip()
        score = slug_score(wanted, slug)
        if score >= 55:
            ranked.append((score, slug))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in ranked[:max(1, int(limit))]]


def type_is_audiobook(value):
    if isinstance(value, list):
        for item in value:
            if to_text(item).lower() == 'audiobook':
                return True
        return False
    return to_text(value).lower() == 'audiobook'


def find_audiobook_record(value):
    if isinstance(value, list):
        for item in value:
            found = find_audiobook_record(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    if type_is_audiobook(value.get('@type')):
        return value
    graph = value.get('@graph')
    return find_audiobook_record(graph) if graph else None


def person_names(value):
    if not isinstance(value, list):
        value = [value] if value else []
    names = []
    for item in value:
        if isinstance(item, dict):
            name = clean_text(item.get('name'))
        else:
            name = clean_text(item)
        if name and name not in names:
            names.append(name)
    return names


def duration_minutes(value):
    match = re.match(
        r'^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$',
        to_text(value).strip(), re.I,
    )
    if not match:
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = float(match.group(4) or 0)
    return days * 1440 + hours * 60 + minutes + seconds / 60.0


def series_entries(html):
    values = []
    seen = set()
    pattern = r'<a[^>]+href=["\'][^"\']*/bokserie/[^"\']+["\'][^>]*>(.*?)</a>'
    for raw in re.findall(pattern, to_text(html), re.I | re.S):
        label = clean_text(raw)
        match = re.match(r'^(.*?)\s*(?:[·\-–—]\s*)?del\s+([0-9]+(?:[.,][0-9]+)?)$', label, re.I)
        if match:
            title = match.group(1).strip(' ·-–—')
            sequence = match.group(2).replace(',', '.')
        else:
            title = label
            sequence = ''
        key = title.lower()
        if title and key not in seen:
            seen.add(key)
            values.append({'title': title, 'sequence': sequence})
    return values


def audiobook_from_html(html, source_url=''):
    html = to_text(html)
    record = None
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.I | re.S,
    )
    for script in scripts:
        try:
            candidate = find_audiobook_record(json.loads(script.strip()))
        except (TypeError, ValueError):
            candidate = None
        if candidate:
            record = candidate
            break
    if not record:
        return None
    title = clean_text(record.get('name'))
    authors = person_names(record.get('author'))
    if not title or not authors:
        return None
    rating = record.get('aggregateRating')
    if not isinstance(rating, dict):
        rating = {}
    try:
        rating_value = float(rating.get('ratingValue'))
    except (TypeError, ValueError):
        rating_value = None
    try:
        rating_count = int(to_text(
            rating.get('ratingCount') or rating.get('reviewCount')
        ).replace(' ', '').replace(',', ''))
    except (TypeError, ValueError):
        rating_count = None
    try:
        best_rating = float(rating.get('bestRating') or 10)
    except (TypeError, ValueError):
        best_rating = 10.0
    isbn = re.sub(r'[^0-9Xx]+', '', to_text(record.get('isbn')))
    genres_value = record.get('genre')
    if not isinstance(genres_value, list):
        genres_value = [genres_value] if genres_value else []
    genres = []
    for value in genres_value:
        value = clean_text(value)
        if value and value not in genres:
            genres.append(value)
    return {
        'title': title,
        'authors': authors,
        'narrators': person_names(record.get('readBy')),
        'language': clean_text(record.get('inLanguage')) or 'sv-SE',
        'description': clean_text(record.get('description')),
        'image': clean_text(record.get('image')),
        'isbn': isbn,
        'duration_minutes': duration_minutes(record.get('duration')),
        'release_date': clean_text(record.get('datePublished')),
        'publisher': clean_text(
            record.get('publisher', {}).get('name')
            if isinstance(record.get('publisher'), dict)
            else record.get('publisher')
        ),
        'genres': genres,
        'rating': rating_value,
        'rating_count': rating_count,
        'best_rating': best_rating,
        'series': series_entries(html),
        'url': clean_text(record.get('url')) or source_url,
    }


def as_product(book):
    if not isinstance(book, dict):
        return {}
    language = to_text(book.get('language')).strip()
    scoring_language = (
        'swedish' if language.lower().replace('_', '-').startswith('sv')
        else language
    )
    return {
        # score_product validates catalogue-shaped records before scoring.
        # This internal sentinel is never exposed as a Plex identity.
        'asin': 'LBA0000000',
        'title': book.get('title'),
        'authors': [{'name': name} for name in book.get('authors') or []],
        'narrators': [{'name': name} for name in book.get('narrators') or []],
        'language': scoring_language,
        'runtime_length_min': book.get('duration_minutes'),
        'release_date': book.get('release_date'),
        'publisher_name': book.get('publisher'),
        'publisher_summary': book.get('description'),
        'series': [
            {'title': item.get('title'), 'sequence': item.get('sequence')}
            for item in book.get('series') or []
        ],
        'isbn': book.get('isbn'),
    }


def search_result_label(book):
    title = to_text(book.get('title')).strip()
    authors = ', '.join(book.get('authors') or [])
    narrators = ', '.join(book.get('narrators') or [])
    value = '"%s"' % title
    if authors:
        value += ' av ' + authors
    if narrators:
        value += ' — uppläst av ' + narrators
    value += ' — Svenska · Ljudboksarkivet'
    return value
