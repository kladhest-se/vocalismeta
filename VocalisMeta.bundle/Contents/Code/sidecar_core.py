# coding: utf-8
"""Strict, bounded, optional per-book metadata. Compatible with Python 2.7."""
from __future__ import unicode_literals
import json
import os
from config_core import (ConfigError, read_bounded, require_object, require_text,
                         require_boolean, require_integer, require_choice)
from audible_core import valid_asin, REGION_TLDS
from identity_core import isbn_identity


def names(value, label):
    if not isinstance(value, list) or len(value) > 32:
        raise ConfigError('%s must be an array of at most 32 names' % label)
    result = []
    for item in value:
        text = require_text(item, label, 512, False).strip()
        if not text:
            raise ConfigError('%s must not contain blank names' % label)
        if text not in result:
            result.append(text)
    return result


def load_sidecar(paths):
    """Only book-directory sidecars are used; conflicting multipart files reject."""
    found = []
    for path in paths:
        filename = os.path.join(os.path.dirname(path), 'vocalismeta.json')
        if os.path.isfile(filename) and filename not in found:
            found.append(filename)
    documents = []
    for filename in found:
        try:
            document = json.loads(read_bounded(filename, 256 * 1024, 'sidecar').decode('utf-8-sig'))
        except (ValueError, UnicodeDecodeError):
            raise ConfigError('sidecar must contain valid UTF-8 JSON')
        require_object(document, 'sidecar', ('schema_version', 'identity', 'metadata', 'artwork'))
        if require_integer(document.get('schema_version'), 'sidecar.schema_version') != 1:
            raise ConfigError('sidecar.schema_version must be 1')
        metadata = document.get('metadata', {})
        require_object(metadata, 'sidecar.metadata', ('title', 'summary', 'authors', 'narrators',
            'series', 'language', 'abridged', 'publisher', 'release_date', 'genres'))
        clean = {}
        for key in ('title', 'summary', 'language', 'publisher', 'release_date'):
            if key in metadata:
                clean[key] = require_text(metadata[key], 'metadata.' + key, 32768, False).strip()
                if not clean[key]:
                    raise ConfigError('metadata.%s must not be blank' % key)
        if 'release_date' in clean:
            import datetime
            try:
                datetime.datetime.strptime(clean['release_date'], '%Y-%m-%d')
            except ValueError:
                raise ConfigError('metadata.release_date must be a valid YYYY-MM-DD date')
        for key in ('authors', 'narrators', 'genres'):
            if key in metadata:
                clean[key] = names(metadata[key], 'metadata.' + key)
        if 'abridged' in metadata:
            clean['abridged'] = require_boolean(metadata['abridged'], 'metadata.abridged')
        if 'series' in metadata:
            entries = metadata['series']
            if not isinstance(entries, list) or len(entries) > 8:
                raise ConfigError('metadata.series must be an array of at most 8 entries')
            clean['series'] = []
            for entry in entries:
                require_object(entry, 'series entry', ('title', 'sequence'))
                title = require_text(entry.get('title'), 'series.title', 512, False).strip()
                if not title:
                    raise ConfigError('series.title must not be blank')
                clean['series'].append({'title': title, 'sequence': require_text(
                    entry.get('sequence', ''), 'series.sequence', 64)})
        identity = document.get('identity', {})
        require_object(identity, 'sidecar.identity', ('provider', 'id', 'region', 'slug'))
        if identity:
            provider = require_choice(identity.get('provider'), 'identity.provider',
                ('audible', 'librivox', 'isbn', 'local', 'ljudboksarkivet'))
            identifier = require_text(identity.get('id', ''), 'identity.id', 64)
            if provider == 'audible' and not valid_asin(identifier.upper()):
                raise ConfigError('identity.id must be an Audible ASIN')
            if provider == 'isbn' and not isbn_identity(identifier):
                raise ConfigError('identity.id must be a valid ISBN')
            import re
            if provider == 'librivox' and not re.match(r'^[1-9][0-9]{0,9}$', identifier):
                raise ConfigError('identity.id must be a LibriVox project ID')
            if provider == 'ljudboksarkivet' and not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$',
                    require_text(identity.get('slug', ''), 'identity.slug', 512)):
                raise ConfigError('identity.slug must be a catalogue slug')
            if 'region' in identity:
                require_choice(identity['region'], 'identity.region', tuple(REGION_TLDS))
            allowed = {'audible': ('provider', 'id', 'region'),
                'librivox': ('provider', 'id'), 'isbn': ('provider', 'id'),
                'local': ('provider',), 'ljudboksarkivet': ('provider', 'slug')}
            require_object(identity, 'sidecar.identity', allowed[provider])
        artwork = document.get('artwork', {})
        require_object(artwork, 'sidecar.artwork', ('file',))
        cover = None
        if artwork:
            relative = require_text(artwork.get('file'), 'artwork.file', 4096, False)
            base = os.path.realpath(os.path.dirname(filename))
            cover = os.path.realpath(os.path.join(base, relative))
            if os.path.isabs(relative) or not cover.startswith(base + os.sep):
                raise ConfigError('artwork.file must stay inside the book directory')
            from local_artwork import inspect_cover
            if not inspect_cover(cover):
                raise ConfigError('artwork.file must be a readable supported image')
        result = {'metadata': clean, 'identity': identity, 'cover': cover}
        if documents and result != documents[0]:
            raise ConfigError('multipart book has conflicting vocalismeta.json files')
        documents.append(result)
    return documents[0] if documents else {}
