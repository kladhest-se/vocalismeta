# coding: utf-8
"""Stable, Python 2.7-compatible audiobook identity helpers."""

from __future__ import unicode_literals

import re

try:
    from urllib import unquote_plus
except ImportError:  # Python 3 test environment
    from urllib.parse import unquote_plus

from audible_core import (
    author_name_from_id,
    normalize_text,
    plex_identifier_from_guid,
    split_id,
    to_text,
    valid_asin,
)
from openlibrary_core import equivalent_isbns
from unicode_identity_core import fingerprint


LIBRIVOX_ID_RE = re.compile(r'^librivox:([1-9][0-9]{0,9})$', re.I)
LOCAL_ID_RE = re.compile(r'^local:([0-9a-f]{16})$', re.I)
PLEX_SUFFIX_RE = re.compile(r'/-?[0-9]+$')
VOCALISMETA_GUID_PROVIDER = 'com.plexapp.agents.spokenmeta'


def canonical_isbn(value):
    values = equivalent_isbns(value)
    for isbn in values:
        if len(isbn) == 13:
            return isbn
    return values[0] if values else ''


def isbn_identity(value):
    isbn = canonical_isbn(value)
    return 'isbn:' + isbn if isbn else ''


def duration_bucket(value):
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return 0
    if minutes <= 0:
        return 0
    return int((minutes + 2.5) / 5.0) * 5


def stable_fingerprint(value):
    """Return a deterministic 64-bit FNV-1a fingerprint."""
    return fingerprint(to_text(value))


def local_identity(title, author, duration_minutes=None, language='', abridged=None):
    abridgment = ''
    if abridged is True:
        abridgment = 'abridged'
    elif abridged is False:
        abridgment = 'unabridged'
    evidence = '|'.join([
        normalize_text(title),
        normalize_text(author),
        str(duration_bucket(duration_minutes)),
        to_text(language).strip().lower(),
        abridgment,
    ])
    return 'local:' + stable_fingerprint(evidence)


def book_identity(
    title, author, duration_minutes=None, language='', abridged=None,
    isbns=None
):
    for value in isbns or []:
        identifier = isbn_identity(value)
        if identifier:
            return identifier
    return local_identity(title, author, duration_minutes, language, abridged)


def split_book_identity(value):
    identifier = plex_identifier_from_guid(value)
    try:
        identifier = to_text(unquote_plus(identifier))
    except Exception:
        identifier = to_text(identifier)
    identifier = PLEX_SUFFIX_RE.sub('', identifier).strip()
    if identifier.lower().startswith('isbn:'):
        isbn = canonical_isbn(identifier[5:])
        return ('isbn', isbn) if isbn else (None, None)
    match = LOCAL_ID_RE.match(identifier)
    if match:
        return 'local', match.group(1).lower()
    return None, None


def guid_provider(value):
    """Return the provider portion of a full Plex GUID, when present."""
    text = to_text(value).strip().replace('\\:', ':')
    if '://' not in text:
        return ''
    return text.split('://', 1)[0].lower()


def client_identity(value):
    """Parse a VocalisMeta metadata ID or Plex GUID into contract-v1 fields."""
    provider = guid_provider(value)
    if provider and provider != VOCALISMETA_GUID_PROVIDER:
        return None
    identifier = plex_identifier_from_guid(value)
    try:
        identifier = to_text(unquote_plus(identifier))
    except Exception:
        identifier = to_text(identifier)
    identifier = PLEX_SUFFIX_RE.sub('', identifier).strip()

    match = LIBRIVOX_ID_RE.match(identifier)
    if match:
        return {'provider': 'librivox', 'id': match.group(1), 'scope': 'book'}

    kind, value = split_book_identity(identifier)
    if kind:
        return {'provider': kind, 'id': value, 'scope': 'book'}

    audible_id, region = split_id(identifier)
    if valid_asin(audible_id):
        return {
            'provider': 'audible', 'id': audible_id.upper(),
            'region': region, 'scope': 'book',
        }

    name = author_name_from_id(identifier)
    if name:
        return {'provider': 'name', 'id': name, 'scope': 'artist'}
    return None


def canonical_client_key(value):
    """Return the documented contract-v1 cloud key for a book identity."""
    parsed = client_identity(value)
    if not parsed or parsed.get('scope') != 'book':
        return ''
    provider = parsed.get('provider')
    identifier = parsed.get('id')
    if provider == 'audible':
        return 'spokenmeta:audible:%s:%s' % (
            parsed.get('region', 'us'), identifier,
        )
    if provider in ('librivox', 'isbn', 'local'):
        return 'spokenmeta:%s:%s' % (provider, identifier)
    return ''
