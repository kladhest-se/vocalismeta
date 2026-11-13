# coding: utf-8
"""Detect conflicting evidence without treating absent tags as disagreements."""
from __future__ import unicode_literals
from audible_core import normalize_text, sequence_label, to_text
from identity_core import canonical_isbn


def language_key(value):
    value = to_text(value).lower().replace('_', '-').split('-', 1)[0]
    aliases = {'eng': 'en', 'english': 'en', 'swe': 'sv', 'swedish': 'sv',
               'deu': 'de', 'ger': 'de', 'german': 'de', 'fra': 'fr', 'fre': 'fr'}
    return aliases.get(value, value)


def conflicts(records):
    """Return field/value evidence for contradictory nonempty part tags."""
    output = []
    fields = ('asin', 'region', 'librivox_id', 'language', 'series', 'series_sequence', 'abridged')
    for field in fields:
        values = {}
        for path, record in records:
            value = record.get(field)
            if value is None or value == '':
                continue
            if field == 'language':
                value = language_key(value)
            elif field == 'series':
                value = normalize_text(value)
            elif field == 'series_sequence':
                value = sequence_label(value)
            else:
                value = to_text(value).strip().lower()
            if value:
                values.setdefault(value, []).append(path)
        if len(values) > 1:
            output.append({'field': field, 'evidence': values})
    common = None
    evidence = {}
    for path, record in records:
        values = set()
        for value in record.get('isbns') or []:
            isbn = canonical_isbn(value)
            if isbn:
                values.add(isbn)
        if values:
            evidence[path] = sorted(values)
            common = values if common is None else common.intersection(values)
    if common is not None and not common and len(evidence) > 1:
        output.append({'field': 'isbns', 'evidence': evidence})
    return output
