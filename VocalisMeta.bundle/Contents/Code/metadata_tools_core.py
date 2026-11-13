# coding: utf-8
"""Isolated metadata drafts and portable report/export helpers for Python 2.7."""
from __future__ import unicode_literals
from audible_core import to_text
from identity_core import client_identity
from config_core import TEXT_TYPES

PREFIXES = ('Series: ', 'Sequence: ', 'Language: ', 'Edition: ', 'Work-ID: ',
            'Contributor-ID: ', 'Work-Published: ', 'Rating-Source: ', 'Rating-Count: ', 'Production: ')


class Tags(list):
    def clear(self):
        del self[:]

    def add(self, value):
        if value not in self:
            self.append(value)


class Posters(dict):
    def validate_keys(self, keys):
        for key in list(self.keys()):
            if key not in keys:
                self.pop(key)


class Draft(object):
    def __init__(self, metadata):
        self.id = metadata.id
        self.title = metadata.title
        self.title_sort = metadata.title_sort
        self.summary = metadata.summary
        self.studio = metadata.studio
        self.rating = metadata.rating
        self.originally_available_at = metadata.originally_available_at
        self.genres = Tags([to_text(value) for value in metadata.genres])
        self.styles = Tags([to_text(value) for value in metadata.styles])
        self.moods = Tags([to_text(value) for value in metadata.moods])
        self.posters = Posters()
        for key in metadata.posters:
            # Values are not mutated; a draft can only replace/remove references.
            self.posters[key] = metadata.posters[key]


def snapshot(metadata):
    date = metadata.originally_available_at
    return {'id': to_text(metadata.id), 'title': to_text(metadata.title),
        'title_sort': to_text(metadata.title_sort), 'summary': to_text(metadata.summary),
        'studio': to_text(metadata.studio), 'rating': metadata.rating,
        'originally_available_at': date.isoformat()[:10] if date else None,
        'genres': [to_text(v) for v in metadata.genres],
        'styles': [to_text(v) for v in metadata.styles],
        'moods': [to_text(v) for v in metadata.moods],
        'posters': sorted([to_text(v) for v in metadata.posters])}


def changes(before, after):
    result = {}
    for field in sorted(set(before).union(after)):
        if before.get(field) != after.get(field):
            result[field] = {'before': before.get(field), 'after': after.get(field)}
    return result


def export_sidecar(record):
    """Export explicit metadata; do not invent image bytes or provider IDs."""
    if not isinstance(record, dict):
        raise ValueError('snapshot must be an object')
    if 'after' in record:
        record = record['after']
    if not isinstance(record, dict):
        raise ValueError('report.after must be a snapshot object')
    metadata = {}
    for source, target in (('title', 'title'), ('summary', 'summary'), ('studio', 'publisher'),
                           ('originally_available_at', 'release_date')):
        value = record.get(source)
        if value:
            if not isinstance(value, TEXT_TYPES):
                raise ValueError('snapshot.%s must be text' % source)
            metadata[target] = to_text(value)
    for source, target in (('genres', 'genres'), ('styles', 'narrators')):
        values = record.get(source)
        if isinstance(values, list):
            metadata[target] = values
    authors, series, sequences = [], [], {}
    moods = record.get('moods') or []
    if not isinstance(moods, list):
        raise ValueError('snapshot.moods must be an array')
    for value in moods:
        if not isinstance(value, TEXT_TYPES):
            raise ValueError('snapshot.moods must contain text')
        value = to_text(value)
        if value.startswith('Series: '):
            title = value[8:].strip()
            if title and title not in series:
                series.append(title)
        elif value.startswith('Sequence: ') and ' #' in value:
            title, sequence = value[10:].rsplit(' #', 1)
            sequences[title] = sequence
        elif value.startswith('Language: '):
            metadata['language'] = value[10:].strip()
        elif value in ('Edition: Abridged', 'Edition: Unabridged'):
            metadata['abridged'] = value == 'Edition: Abridged'
        elif value and not value.startswith(PREFIXES) and value not in authors:
            authors.append(value)
    # Saved Plex XML can supply the album artist when author Moods are disabled.
    if not authors and record.get('primary_author'):
        authors.append(to_text(record['primary_author']))
    if authors:
        metadata['authors'] = authors
    if series:
        metadata['series'] = [{'title': title, 'sequence': sequences.get(title, '')} for title in series]
    result = {'schema_version': 1, 'metadata': metadata}
    parsed = client_identity(record.get('id'))
    if parsed and parsed.get('scope') == 'book':
        provider = parsed['provider']
        if provider in ('audible', 'librivox', 'isbn'):
            result['identity'] = {'provider': provider, 'id': parsed['id']}
            if provider == 'audible':
                result['identity']['region'] = parsed['region']
        elif provider == 'local':
            result['identity'] = {'provider': 'local'}
    slug = record.get('ljudboksarkivet_slug')
    if slug:
        result['identity'] = {'provider': 'ljudboksarkivet', 'slug': slug}
    return result
