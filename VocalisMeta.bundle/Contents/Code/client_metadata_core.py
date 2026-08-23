# coding: utf-8
"""Pure helpers for optional VocalisMeta audiobook-player metadata."""

from __future__ import unicode_literals

import re

try:
    text_type = unicode
except NameError:  # pragma: no cover - Python 3 only
    text_type = str


AUDIBLE_ID_RE = re.compile(r'^[A-Z0-9]{10}$')
OPENLIBRARY_AUTHOR_RE = re.compile(r'^OL[0-9]+A$')
DECIMAL_ID_RE = re.compile(r'^[1-9][0-9]{0,9}$')
ALLOWED_ROLES = ('author', 'narrator')
ALLOWED_SOURCES = ('audible', 'librivox', 'openlibrary', 'name')


def to_text(value):
    if value is None:
        return ''
    if isinstance(value, text_type):
        return value
    try:
        return value.decode('utf-8', 'replace')
    except AttributeError:
        return text_type(value)


def text_field(value):
    if isinstance(value, text_type):
        return value.strip()
    try:
        return value.decode('utf-8', 'replace').strip()
    except AttributeError:
        return ''


def clean_name(value):
    value = re.sub(r'[\r\n\t]+', ' ', text_field(value))
    value = re.sub(r'\s+', ' ', value).strip()
    return value.replace(' = ', ' - ')


def name_fingerprint(value):
    """Return a deterministic fallback ID for an exact normalized name."""
    value = clean_name(value).lower()
    if not value:
        return ''
    checksum = 14695981039346656037
    modulus = 18446744073709551616
    for index in range(len(value)):
        checksum = checksum ^ ord(value[index])
        checksum = (checksum * 1099511628211) % modulus
    return '%016x' % checksum


def person_name(record):
    if not isinstance(record, dict):
        return ''
    name = clean_name(record.get('name') or record.get('display_name'))
    if name:
        return name
    parts = []
    for key in ('first_name', 'last_name'):
        value = clean_name(record.get(key))
        if value:
            parts.append(value)
    return ' '.join(parts)


def valid_contributor_id(source, value):
    source = text_field(source).lower()
    value = text_field(value)
    if source == 'audible':
        value = value.upper()
        return value if AUDIBLE_ID_RE.match(value) else ''
    if source == 'librivox':
        return value if DECIMAL_ID_RE.match(value) else ''
    if source == 'openlibrary':
        value = value.rsplit('/', 1)[-1].upper()
        return value if OPENLIBRARY_AUTHOR_RE.match(value) else ''
    if source == 'name':
        value = value.lower()
        return value if re.match(r'^[0-9a-f]{16}$', value) else ''
    return ''


def contributor_tag(role, source, identifier, name):
    role = text_field(role).lower()
    source = text_field(source).lower()
    if role not in ALLOWED_ROLES or source not in ALLOWED_SOURCES:
        return ''
    if source == 'name' and role != 'narrator':
        return ''
    identifier = valid_contributor_id(source, identifier)
    name = clean_name(name)
    if not identifier or not name:
        return ''
    return 'Contributor-ID: %s:%s:%s = %s' % (
        role, source, identifier, name
    )


def contributor_tags(records, role, source, id_key):
    output = []
    seen = set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        tag = contributor_tag(
            role, source, record.get(id_key), person_name(record)
        )
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            output.append(tag)
    return output


def name_contributor_tags(names, role='narrator'):
    """Return deterministic fallback tags for contributors without source IDs."""
    output = []
    seen = set()
    for value in names if isinstance(names, list) else []:
        name = clean_name(value)
        tag = contributor_tag(role, 'name', name_fingerprint(name), name)
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            output.append(tag)
    return output


def audible_contributor_tags(product):
    if not isinstance(product, dict):
        return []
    output = contributor_tags(
        product.get('authors'), 'author', 'audible', 'asin'
    )
    narrators = product.get('narrators')
    output.extend(contributor_tags(
        narrators, 'narrator', 'audible', 'asin'
    ))
    for record in narrators if isinstance(narrators, list) else []:
        if not isinstance(record, dict):
            continue
        name = person_name(record)
        if valid_contributor_id('audible', record.get('asin')) or not name:
            continue
        tag = name_contributor_tags([name])
        tag = tag[0] if tag else ''
        if tag and tag.lower() not in [value.lower() for value in output]:
            output.append(tag)
    return output


def librivox_contributor_tags(book):
    if not isinstance(book, dict):
        return []
    output = contributor_tags(
        book.get('authors'), 'author', 'librivox', 'id'
    )
    readers = []
    sections = book.get('sections')
    if not isinstance(sections, list):
        sections = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_readers = section.get('readers')
        if isinstance(section_readers, list):
            readers.extend(section_readers)
    output.extend(contributor_tags(
        readers, 'narrator', 'librivox', 'reader_id'
    ))
    deduplicated = []
    seen = set()
    for tag in output:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            deduplicated.append(tag)
    return deduplicated


def openlibrary_contributor_tags(document):
    if not isinstance(document, dict):
        return []
    names = document.get('author_name')
    identifiers = document.get('author_key')
    if not isinstance(names, list) or not isinstance(identifiers, list):
        return []
    records = []
    maximum = min(len(names), len(identifiers))
    for index in range(maximum):
        records.append({'name': names[index], 'key': identifiers[index]})
    return contributor_tags(
        records, 'author', 'openlibrary', 'key'
    )


def rating_count(product):
    if not isinstance(product, dict):
        return None
    rating = product.get('rating')
    if not isinstance(rating, dict):
        return None
    overall = rating.get('overall_distribution')
    if not isinstance(overall, dict):
        return None
    value = overall.get('num_ratings')
    if value is None:
        value = overall.get('rating_count')
    try:
        value = int(to_text(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def production_type(product):
    """Return only explicit provider production labels; never infer from cast size."""
    if not isinstance(product, dict):
        return ''
    values = []
    for key in ('production_type', 'content_delivery_type', 'format_type'):
        value = text_field(product.get(key))
        if value:
            values.append(value.lower())
    joined = ' '.join(values)
    if 'full cast' in joined or 'full-cast' in joined:
        return 'Full cast'
    if 'dramatized' in joined or 'dramatised' in joined:
        return 'Dramatized'
    if 'single narrator' in joined or 'single-narrator' in joined:
        return 'Single narrator'
    if 'multi narrator' in joined or 'multi-narrator' in joined:
        return 'Multi-narrator'
    return ''
