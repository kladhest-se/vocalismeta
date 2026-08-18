# coding: utf-8
"""Pure, Python 2.7-compatible helpers for Google Books enrichment."""

from __future__ import unicode_literals

import re

try:
    from urllib import urlencode
except ImportError:  # Python 3 test environment
    from urllib.parse import urlencode

from audible_core import clean_html, score_product, text_field, to_text
from openlibrary_core import equivalent_isbns, normalize_isbn


GOOGLE_BOOKS_BASE = 'https://www.googleapis.com/books/v1'
DATE_RE = re.compile(r'^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$')
HTTP_URL_RE = re.compile(r'^https?://', re.I)


def encoded_query(params):
    encoded = {}
    for key, value in params.items():
        if isinstance(value, int):
            encoded[key] = value
        else:
            encoded[key] = to_text(value).encode('utf-8')
    return urlencode(encoded)


def volumes_url(query, api_key, language='', limit=10):
    query = to_text(query).strip()
    api_key = to_text(api_key).strip()
    if not query or not api_key:
        return ''
    try:
        limit = max(1, min(40, int(limit)))
    except (TypeError, ValueError):
        limit = 10
    params = {
        'q': query,
        'key': api_key,
        'maxResults': limit,
        'printType': 'books',
        'projection': 'full',
    }
    language = to_text(language).strip().lower()[:2]
    if language:
        params['langRestrict'] = language
    return GOOGLE_BOOKS_BASE + '/volumes?' + encoded_query(params)


def isbn_url(isbn, api_key, limit=10):
    isbn = normalize_isbn(isbn)
    return volumes_url('isbn:' + isbn, api_key, limit=limit) if isbn else ''


def search_url(title, author, api_key, language='', limit=10):
    title = to_text(title).strip()
    author = to_text(author).strip()
    if not title:
        return ''
    query = 'intitle:"%s"' % title.replace('"', ' ')
    if author:
        query += ' inauthor:"%s"' % author.replace('"', ' ')
    return volumes_url(query, api_key, language, limit)


def volume_info(volume):
    if not isinstance(volume, dict):
        return {}
    info = volume.get('volumeInfo')
    return info if isinstance(info, dict) else {}


def volumes_from_response(response):
    if not isinstance(response, dict):
        return []
    items = response.get('items')
    if not isinstance(items, list):
        return []
    output = []
    for volume in items:
        if not isinstance(volume, dict) or not text_field(volume.get('id')):
            continue
        if text_field(volume_info(volume).get('title')):
            output.append(volume)
    return output


def list_values(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    output = []
    for item in values:
        text = text_field(item)
        if text and text not in output:
            output.append(text)
    return output


def volume_authors(volume):
    return list_values(volume_info(volume).get('authors'))


def volume_isbns(volume):
    identifiers = volume_info(volume).get('industryIdentifiers')
    if not isinstance(identifiers, list):
        return []
    output = []
    for item in identifiers:
        if not isinstance(item, dict):
            continue
        value = normalize_isbn(text_field(item.get('identifier')))
        for isbn in equivalent_isbns(value):
            if isbn and isbn not in output:
                output.append(isbn)
    return output


def volume_description(volume):
    value = volume_info(volume).get('description')
    value = text_field(value)
    return clean_html(value) if value else ''


def volume_categories(volume, maximum=8):
    return list_values(volume_info(volume).get('categories'))[:maximum]


def volume_date(volume):
    value = text_field(volume_info(volume).get('publishedDate'))
    match = DATE_RE.match(value)
    if not match:
        return ''
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    if not 0 < year < 10000 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return ''
    return '%04d-%02d-%02d' % (year, month, day)


def cover_urls(volume):
    links = volume_info(volume).get('imageLinks')
    if not isinstance(links, dict):
        return []
    output = []
    for key in ('extraLarge', 'large', 'medium', 'small', 'thumbnail', 'smallThumbnail'):
        url = text_field(links.get(key))
        if not HTTP_URL_RE.match(url):
            continue
        if url.startswith('http://books.google.') or url.startswith('http://books.googleusercontent.'):
            url = 'https://' + url[len('http://'):]
        if url not in output:
            output.append(url)
    return output


def product_view(volume):
    info = volume_info(volume)
    return {
        # score_product requires a valid-looking identifier. This never leaves
        # the in-memory ranking helper or becomes a Plex metadata ID.
        'asin': '0000000000',
        'title': text_field(info.get('title')),
        'subtitle': text_field(info.get('subtitle')),
        'authors': [{'name': name} for name in volume_authors(volume)],
        'language': text_field(info.get('language')),
        'release_date': volume_date(volume),
    }


def score_volume(title, author, language, volume, index=0):
    # Google Books is tertiary book-level enrichment, below Audible editions
    # and Open Library's earlier fallback position.
    return max(0, min(
        93, score_product(title, author, language, product_view(volume), index) - 4
    ))
