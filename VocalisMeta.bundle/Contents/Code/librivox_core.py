# coding: utf-8
"""Pure, Python 2.7-compatible helpers for the released LibriVox API."""

from __future__ import unicode_literals

import re

try:
    from urllib import urlencode
except ImportError:  # Python 3 test environment
    from urllib.parse import urlencode

from audible_core import clean_html, score_product, text_field, to_text


LIBRIVOX_BASE = 'https://librivox.org/api/feed/audiobooks'
BOOK_ID_RE = re.compile(r'^[1-9]\d{0,9}$')
BOOK_HINT_RE = re.compile(r'\b(?:librivox|lv)\s*[:#]\s*([1-9]\d{0,9})\b', re.I)
SOURCE_HINT_RE = re.compile(
    r'(?:^|[^a-z0-9])librivox(?:[^a-z0-9]|$)', re.I
)
HTTP_URL_RE = re.compile(r'^https?://', re.I)
TIME_RE = re.compile(r'^(\d+):(\d{1,2}):(\d{1,2})$')


def encoded_query(params):
    encoded = {}
    for key, value in params.items():
        if isinstance(value, int):
            encoded[key] = value
        else:
            encoded[key] = to_text(value).encode('utf-8')
    return urlencode(encoded)


def normalize_book_id(value):
    value = to_text(value).strip()
    return value if BOOK_ID_RE.match(value) else ''


def find_book_id(*values):
    for value in values:
        match = BOOK_HINT_RE.search(to_text(value))
        if match:
            return match.group(1)
    return ''


def has_source_hint(*values):
    """Return True when a path explicitly identifies LibriVox content."""
    for value in values:
        if SOURCE_HINT_RE.search(to_text(value)):
            return True
    return False


def strip_book_id_hint(value):
    value = BOOK_HINT_RE.sub(' ', to_text(value))
    return re.sub(r'\s+', ' ', value).strip(' -_:|')


def make_id(value):
    book_id = normalize_book_id(value)
    return 'librivox:' + book_id if book_id else ''


def split_id(value):
    value = re.sub(r'/-?\d+$', '', to_text(value).strip()).lower()
    if not value.startswith('librivox:'):
        return ''
    return normalize_book_id(value.split(':', 1)[1])


def api_url(params):
    values = dict(params or {})
    values['format'] = 'json'
    values['extended'] = 1
    values['coverart'] = 1
    return LIBRIVOX_BASE + '/?' + encoded_query(values)


def book_url(value):
    book_id = normalize_book_id(value)
    return api_url({'id': book_id}) if book_id else ''


def search_url(title, author='', limit=20):
    title = text_field(title)
    if not title:
        return ''
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit = 20
    params = {'title': '^' + title, 'limit': limit}
    author = text_field(author)
    if author:
        params['author'] = author.rsplit(' ', 1)[-1]
    return api_url(params)


def book_id(book):
    return normalize_book_id(book.get('id')) if isinstance(book, dict) else ''


def books_from_response(response):
    if not isinstance(response, dict):
        return []
    books = response.get('books')
    if not isinstance(books, list):
        return []
    output = []
    for book in books:
        if not isinstance(book, dict) or not book_id(book):
            continue
        if text_field(book.get('title')):
            output.append(book)
    return output


def valid_books_response(response):
    return isinstance(response, dict) and isinstance(response.get('books'), list)


def list_values(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    output = []
    for item in values:
        text = text_field(item)
        if text and text not in output:
            output.append(text)
    return output


def person_name(person):
    if not isinstance(person, dict):
        return text_field(person)
    direct = (
        text_field(person.get('display_name'))
        or text_field(person.get('name'))
    )
    if direct:
        return direct
    return ' '.join(filter(None, [
        text_field(person.get('first_name')),
        text_field(person.get('last_name')),
    ])).strip()


def people(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    output = []
    for person in values:
        name = person_name(person)
        if name and name not in output:
            output.append(name)
    return output


def authors(book):
    if not isinstance(book, dict) or not isinstance(book.get('authors'), list):
        return []
    return people(book.get('authors'))


def readers(book, maximum=32):
    if not isinstance(book, dict):
        return []
    output = (
        people(book.get('readers'))
        if isinstance(book.get('readers'), list) else []
    )
    sections = book.get('sections')
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_readers = section.get('readers')
            if not isinstance(section_readers, list):
                continue
            for name in people(section_readers):
                if name not in output:
                    output.append(name)
                    if len(output) >= maximum:
                        return output
    return output[:maximum]


def genres(book, maximum=8):
    if not isinstance(book, dict):
        return []
    values = book.get('genres')
    values = values if isinstance(values, list) else []
    output = []
    for value in values:
        name = person_name(value)
        if name and name not in output:
            output.append(name)
            if len(output) >= maximum:
                break
    return output


def description(book):
    value = text_field(book.get('description')) if isinstance(book, dict) else ''
    return clean_html(value) if value else ''


def language(book):
    return text_field(book.get('language')) if isinstance(book, dict) else ''


def copyright_year(book):
    value = text_field(book.get('copyright_year')) if isinstance(book, dict) else ''
    try:
        year = int(value)
        return year if 0 < year < 10000 else None
    except (TypeError, ValueError):
        return None


def duration_seconds(book):
    if not isinstance(book, dict):
        return None
    try:
        value = int(float(book.get('totaltimesecs')))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    match = TIME_RE.match(text_field(book.get('totaltime')))
    if not match:
        return None
    hours, minutes, seconds = [int(value) for value in match.groups()]
    if minutes >= 60 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def runtime_label(book):
    seconds = duration_seconds(book)
    if not seconds:
        return ''
    minutes = int(round(seconds / 60.0))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return '%dh %dm' % (hours, remainder)
    if hours:
        return '%dh' % hours
    return '%dm' % remainder


def cover_urls(book):
    if not isinstance(book, dict):
        return []
    output = []
    for key in ('coverart_jpg', 'coverart_thumbnail'):
        url = text_field(book.get(key))
        if HTTP_URL_RE.match(url) and url not in output:
            output.append(url)
    return output


def product_view(book):
    year = copyright_year(book)
    seconds = duration_seconds(book)
    return {
        'asin': '0000000000',
        'title': text_field(book.get('title')),
        'authors': [{'name': name} for name in authors(book)],
        'narrators': [{'name': name} for name in readers(book)],
        'language': language(book),
        'release_date': str(year) if year else '',
        'runtime_length_min': seconds / 60.0 if seconds else None,
    }


def score_book(
    title, author, wanted_language, book, index=0, duration_minutes=None,
    wanted_readers=None, year=None
):
    return max(0, min(96, score_product(
        title, author, wanted_language, product_view(book), index,
        duration_minutes, wanted_readers, year, None
    )))


def search_result_label(book):
    names = authors(book)
    label = '"%s"' % text_field(book.get('title'))
    if names:
        label += ' by ' + ', '.join(names)
    book_readers = readers(book)
    if book_readers:
        shown = book_readers[:3]
        label += ' — read by ' + ', '.join(shown)
        if len(book_readers) > len(shown):
            label += ' and %d more' % (len(book_readers) - len(shown))
    details = []
    runtime = runtime_label(book)
    if runtime:
        details.append(runtime)
    year = copyright_year(book)
    if year:
        details.append(str(year))
    book_language = language(book)
    if book_language:
        details.append(book_language)
    details.append('LibriVox')
    return label + ' — ' + ' · '.join(details)
