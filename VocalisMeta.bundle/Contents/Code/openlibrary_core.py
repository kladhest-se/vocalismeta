# coding: utf-8
"""Pure helpers for low-volume Open Library metadata enrichment."""

from __future__ import unicode_literals

import re

try:
    from urllib import urlencode
except ImportError:  # Python 3 test environment
    from urllib.parse import urlencode

from audible_core import score_product, to_text


OPENLIBRARY_BASE = 'https://openlibrary.org'
OPENLIBRARY_FIELDS = ','.join([
    'key', 'title', 'subtitle', 'author_name', 'first_publish_year',
    'subject', 'cover_i', 'isbn', 'language', 'first_sentence',
])
WORK_ID_RE = re.compile(r'^OL\d+W$', re.I)
ISBN_RE = re.compile(r'^(?:\d{9}[\dX]|\d{13})$')
LANGUAGE_NAMES = {
    'eng': 'english', 'deu': 'german', 'ger': 'german', 'spa': 'spanish',
    'fra': 'french', 'fre': 'french', 'ita': 'italian', 'jpn': 'japanese',
}


def encoded_query(params):
    encoded = {}
    for key, value in params.items():
        if isinstance(value, int):
            encoded[key] = value
        else:
            encoded[key] = to_text(value).encode('utf-8')
    return urlencode(encoded)


def normalize_work_id(value):
    value = to_text(value).strip().split('/')[-1].upper()
    return value if WORK_ID_RE.match(value) else ''


def work_identity(value):
    """Return the stable client work identity for an Open Library result."""
    if isinstance(value, dict):
        value = value.get('key')
    work_id = normalize_work_id(value)
    return 'openlibrary:' + work_id if work_id else ''


def work_url(value):
    work_id = normalize_work_id(value.get('key') if isinstance(value, dict) else value)
    return OPENLIBRARY_BASE + '/works/' + work_id + '.json' if work_id else ''


def search_url(title, author='', language='', limit=10):
    try:
        limit = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        limit = 10
    params = {
        'title': to_text(title).strip(),
        'fields': OPENLIBRARY_FIELDS,
        'limit': limit,
    }
    if to_text(author).strip():
        params['author'] = to_text(author).strip()
    language = to_text(language).strip().lower()[:2]
    if language:
        params['lang'] = language
    return OPENLIBRARY_BASE + '/search.json?' + encoded_query(params)


def normalize_isbn(value):
    value = re.sub(r'[^0-9Xx]', '', to_text(value)).upper()
    if not ISBN_RE.match(value):
        return ''
    if len(value) == 10:
        total = 0
        for index, char in enumerate(value):
            total += (10 - index) * (10 if char == 'X' else int(char))
        return value if total % 11 == 0 else ''
    total = 0
    for index, char in enumerate(value):
        total += int(char) * (1 if index % 2 == 0 else 3)
    return value if total % 10 == 0 else ''


def isbn10_to_isbn13(value):
    isbn = normalize_isbn(value)
    if len(isbn) != 10:
        return ''
    body = '978' + isbn[:9]
    total = 0
    for index, char in enumerate(body):
        total += int(char) * (1 if index % 2 == 0 else 3)
    return body + str((10 - (total % 10)) % 10)


def isbn13_to_isbn10(value):
    isbn = normalize_isbn(value)
    if len(isbn) != 13 or not isbn.startswith('978'):
        return ''
    body = isbn[3:12]
    total = 0
    for index, char in enumerate(body):
        total += (10 - index) * int(char)
    check = (11 - (total % 11)) % 11
    if check == 10:
        suffix = 'X'
    elif check == 0:
        suffix = '0'
    else:
        suffix = str(check)
    return body + suffix


def equivalent_isbns(value):
    isbn = normalize_isbn(value)
    if not isbn:
        return []
    alternate = (
        isbn10_to_isbn13(isbn) if len(isbn) == 10 else isbn13_to_isbn10(isbn)
    )
    return [isbn] + ([alternate] if alternate and alternate != isbn else [])


def isbn_values(values):
    output = []
    for value in values:
        for isbn in equivalent_isbns(value):
            if isbn not in output:
                output.append(isbn)
    return output


def isbn_search_url(isbn, limit=10):
    isbn = normalize_isbn(isbn)
    if not isbn:
        return ''
    try:
        limit = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        limit = 10
    return OPENLIBRARY_BASE + '/search.json?' + encoded_query({
        'isbn': isbn,
        'fields': OPENLIBRARY_FIELDS,
        'limit': limit,
    })


def documents_from_response(response):
    if not isinstance(response, dict):
        return []
    docs = response.get('docs')
    if not isinstance(docs, list):
        return []
    return [doc for doc in docs if isinstance(doc, dict) and normalize_work_id(doc.get('key'))]


def list_values(value):
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = [value]
    output = []
    for item in values:
        text = to_text(item).strip()
        if text and text not in output:
            output.append(text)
    return output


def document_title(document):
    title = to_text(document.get('title')).strip()
    subtitle = to_text(document.get('subtitle')).strip()
    if subtitle and subtitle.lower() not in title.lower():
        return '%s: %s' % (title, subtitle)
    return title


def document_authors(document):
    return list_values(document.get('author_name'))


def document_isbns(document):
    return isbn_values(list_values(document.get('isbn')))


def product_isbns(product):
    """Return valid edition ISBNs without exposing them as Plex metadata."""
    if not isinstance(product, dict):
        return []
    values = []
    for key in ('isbn', 'isbn_10', 'isbn10', 'isbn_13', 'isbn13'):
        values.extend(list_values(product.get(key)))
    extended = product.get('product_extended_attrs')
    if isinstance(extended, dict):
        for key in ('isbn', 'isbn_10', 'isbn10', 'isbn_13', 'isbn13'):
            values.extend(list_values(extended.get(key)))
    return isbn_values(values)


def document_year(document):
    try:
        year = int(document.get('first_publish_year'))
        return year if 0 < year < 10000 else None
    except (TypeError, ValueError):
        return None


def document_subjects(document, maximum=8):
    return list_values(document.get('subject'))[:maximum]


def document_summary(document):
    value = document.get('first_sentence')
    if isinstance(value, dict):
        value = value.get('value')
    values = list_values(value)
    return values[0] if values else ''


def work_description(work):
    if not isinstance(work, dict):
        return ''
    value = work.get('description')
    if isinstance(value, dict):
        value = value.get('value')
    return to_text(value).strip()


def cover_urls(document):
    try:
        cover_id = int(document.get('cover_i'))
    except (TypeError, ValueError):
        return []
    if cover_id <= 0:
        return []
    base = 'https://covers.openlibrary.org/b/id/%d-' % cover_id
    return [base + size + '.jpg?default=false' for size in ('L', 'M', 'S')]


def product_view(document):
    languages = list_values(document.get('language'))
    language = LANGUAGE_NAMES.get(languages[0].lower(), '') if languages else ''
    year = document_year(document)
    return {
        # score_product requires a structurally valid identifier; this value is
        # local to scoring and is never exposed as an Audible ASIN.
        'asin': '0000000000',
        'title': to_text(document.get('title')).strip(),
        'subtitle': to_text(document.get('subtitle')).strip(),
        'authors': [{'name': name} for name in document_authors(document)],
        'language': language,
        'release_date': str(year) if year else '',
    }


def score_document(title, author, language, document, index=0):
    # Keep book-level fallbacks below equally good audiobook-edition matches.
    return max(0, min(
        94, score_product(title, author, language, product_view(document), index) - 3
    ))
