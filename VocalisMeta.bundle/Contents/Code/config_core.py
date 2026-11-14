# coding: utf-8
"""Strict, dependency-free filesystem configuration for VocalisMeta."""

from __future__ import unicode_literals

import json
import io
import os

try:
    from urlparse import urlparse
except ImportError:  # pragma: no cover - Python 3
    from urllib.parse import urlparse


MAX_CONFIG_BYTES = 1024 * 1024
MAX_SECRET_BYTES = 16 * 1024
REGIONS = ('au', 'ca', 'de', 'es', 'fr', 'in', 'it', 'jp', 'us', 'uk')

try:
    TEXT_TYPES = (basestring,)  # noqa: F821 - Python 2
    INTEGER_TYPES = (int, long)  # noqa: F821 - Python 2
except NameError:  # pragma: no cover - Python 3
    TEXT_TYPES = (str,)
    INTEGER_TYPES = (int,)


class ConfigError(ValueError):
    """A configuration error safe to report without exposing secret data."""

    def __init__(self, message, watch_path=None):
        ValueError.__init__(self, message)
        self.watch_path = watch_path


def file_signature(path):
    """Return a cheap signature suitable for detecting atomic file changes."""
    try:
        info = os.stat(path)
    except (IOError, OSError) as error:
        raise ConfigError('cannot stat file: %s' % error)
    return (
        info.st_dev, info.st_ino, info.st_size,
        int(info.st_mtime * 1000000000),
        int(info.st_ctime * 1000000000),
    )


def read_bounded(path, maximum, label):
    try:
        size = os.path.getsize(path)
    except (IOError, OSError) as error:
        raise ConfigError('cannot inspect %s: %s' % (label, error), path)
    if size > maximum:
        raise ConfigError('%s exceeds %d bytes' % (label, maximum), path)
    try:
        with io.open(path, 'rb') as handle:
            data = handle.read(maximum + 1)
    except (IOError, OSError) as error:
        raise ConfigError('cannot read %s: %s' % (label, error), path)
    if len(data) > maximum:
        raise ConfigError('%s exceeds %d bytes' % (label, maximum), path)
    return data


def require_object(value, location, allowed):
    if not isinstance(value, dict):
        raise ConfigError('%s must be an object' % location)
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ConfigError('%s contains unknown key: %s' % (location, unknown[0]))
    return value


def require_boolean(value, location):
    if not isinstance(value, bool):
        raise ConfigError('%s must be a boolean' % location)
    return value


def require_integer(value, location, minimum=None, maximum=None, choices=None):
    if isinstance(value, bool) or not isinstance(value, INTEGER_TYPES):
        raise ConfigError('%s must be an integer' % location)
    if minimum is not None and value < minimum:
        raise ConfigError('%s must be at least %d' % (location, minimum))
    if maximum is not None and value > maximum:
        raise ConfigError('%s must be at most %d' % (location, maximum))
    if choices is not None and value not in choices:
        raise ConfigError('%s must be one of %s' % (
            location, ', '.join([str(item) for item in choices])
        ))
    return value


def require_text(value, location, maximum=4096, allow_empty=True):
    if not isinstance(value, TEXT_TYPES):
        raise ConfigError('%s must be a string' % location)
    if len(value) > maximum:
        raise ConfigError('%s is too long' % location)
    if not allow_empty and not value:
        raise ConfigError('%s must not be empty' % location)
    if '\x00' in value:
        raise ConfigError('%s must not contain NUL bytes' % location)
    return value


def require_choice(value, location, choices):
    value = require_text(value, location, 64, False)
    if value not in choices:
        raise ConfigError('%s must be one of %s' % (location, ', '.join(choices)))
    return value


def copy_boolean_values(source, target, mapping, prefix):
    for key, pref_name in mapping:
        if key in source:
            target[pref_name] = require_boolean(
                source[key], '%s.%s' % (prefix, key)
            )


def read_secret(path):
    raw = read_bounded(path, MAX_SECRET_BYTES, 'secret file')
    try:
        value = raw.decode('utf-8').rstrip()
    except UnicodeDecodeError:
        raise ConfigError('secret file must contain valid UTF-8', path)
    if not value:
        raise ConfigError('secret file must not be empty', path)
    if '\x00' in value or '\n' in value or '\r' in value:
        raise ConfigError('secret file must contain a single text value', path)
    return value


def load_config_file(path):
    """Load, strictly validate, and flatten a version-one JSON config."""
    if not isinstance(path, TEXT_TYPES):
        raise ConfigError('configuration path must be a string')
    if not os.path.isabs(path):
        raise ConfigError('configuration path must be absolute')

    raw = read_bounded(path, MAX_CONFIG_BYTES, 'configuration file')
    try:
        document = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError) as error:
        raise ConfigError('configuration file is not valid UTF-8 JSON: %s' % error)

    root_keys = (
        'schema_version', 'audible', 'providers', 'metadata', 'artwork',
        'network', 'logging',
    )
    document = require_object(document, 'configuration', root_keys)
    if 'schema_version' not in document:
        raise ConfigError('configuration.schema_version is required')
    if require_integer(
        document['schema_version'], 'configuration.schema_version'
    ) != 1:
        raise ConfigError('configuration.schema_version must be 1')

    values = {}
    secret_path = None

    if 'audible' in document:
        audible = require_object(document['audible'], 'audible', (
            'region', 'fallback_regions', 'maximum_results',
            'exclude_preorders', 'include_adult', 'api_base_url',
        ))
        if 'region' in audible:
            values['region'] = require_choice(
                audible['region'], 'audible.region', REGIONS
            )
        if 'fallback_regions' in audible:
            regions = audible['fallback_regions']
            if not isinstance(regions, list):
                raise ConfigError('audible.fallback_regions must be an array')
            if len(regions) > 4:
                raise ConfigError('audible.fallback_regions must contain at most 4 regions')
            unique = []
            for index, region in enumerate(regions):
                region = require_choice(
                    region, 'audible.fallback_regions[%d]' % index, REGIONS
                )
                if region not in unique:
                    unique.append(region)
            values['fallback_regions'] = ','.join(unique)
        if 'maximum_results' in audible:
            values['max_results'] = require_integer(
                audible['maximum_results'], 'audible.maximum_results',
                choices=(10, 20, 25, 50),
            )
        copy_boolean_values(audible, values, (
            ('exclude_preorders', 'exclude_preorders'),
            ('include_adult', 'include_adult'),
        ), 'audible')
        if 'api_base_url' in audible:
            url = require_text(
                audible['api_base_url'], 'audible.api_base_url', 2048
            ).strip()
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                    raise ConfigError('audible.api_base_url must be an HTTP(S) URL or empty')
            values['api_base_url'] = url

    if 'providers' in document:
        providers = require_object(document['providers'], 'providers', (
            'librivox', 'ljudboksarkivet', 'open_library', 'google_books',
            'enrichment_priority', 'request_budget',
        ))
        if 'librivox' in providers:
            librivox = require_object(
                providers['librivox'], 'providers.librivox',
                ('enabled', 'mode')
            )
            if 'enabled' in librivox:
                values['librivox_enabled'] = require_boolean(
                    librivox['enabled'], 'providers.librivox.enabled'
                )
            if 'mode' in librivox:
                values['librivox_mode'] = require_choice(
                    librivox['mode'], 'providers.librivox.mode',
                    ('hinted_only', 'fallback', 'preferred')
                )
        if 'ljudboksarkivet' in providers:
            provider = require_object(
                providers['ljudboksarkivet'],
                'providers.ljudboksarkivet', ('enabled', 'mode')
            )
            if 'enabled' in provider:
                values['ljudboksarkivet_enabled'] = require_boolean(
                    provider['enabled'],
                    'providers.ljudboksarkivet.enabled'
                )
            if 'mode' in provider:
                values['ljudboksarkivet_mode'] = require_choice(
                    provider['mode'], 'providers.ljudboksarkivet.mode',
                    ('fallback', 'preferred')
                )
        if 'open_library' in providers:
            provider = require_object(
                providers['open_library'], 'providers.open_library',
                ('enabled',)
            )
            if 'enabled' in provider:
                values['openlibrary_enabled'] = require_boolean(
                    provider['enabled'], 'providers.open_library.enabled'
                )
        if 'google_books' in providers:
            google = require_object(
                providers['google_books'], 'providers.google_books',
                ('enabled', 'api_key_file'),
            )
            if 'enabled' in google:
                values['googlebooks_enabled'] = require_boolean(
                    google['enabled'], 'providers.google_books.enabled'
                )
            if 'api_key_file' in google:
                secret_path = require_text(
                    google['api_key_file'], 'providers.google_books.api_key_file',
                    4096, False,
                )
                if not os.path.isabs(secret_path):
                    secret_path = os.path.abspath(os.path.join(
                        os.path.dirname(path), secret_path
                    ))
                values['googlebooks_api_key'] = read_secret(secret_path)
        if 'enrichment_priority' in providers:
            values['enrichment_order'] = require_choice(
                providers['enrichment_priority'], 'providers.enrichment_priority',
                ('openlibrary_first', 'googlebooks_first'),
            )
        if 'request_budget' in providers:
            values['enrichment_request_budget'] = require_integer(
                providers['request_budget'], 'providers.request_budget',
                choices=(2, 4, 6, 8, 12),
            )

    if 'metadata' in document:
        metadata = require_object(document['metadata'], 'metadata', (
            'include_subtitle', 'simplify_title', 'keep_existing_genres',
            'authors_as_moods', 'series_as_moods', 'embedded_series_fallback',
            'embedded_contributor_fallback', 'author_genres',
            'work_identity_as_mood', 'extended_player_metadata', 'preview_updates', 'reports', 'client_contract_v4',
        ))
        copy_boolean_values(metadata, values, (
            ('preview_updates', 'preview_updates'),
            ('reports', 'metadata_reports'),
            ('client_contract_v4', 'store_client_contract_v4'),
            ('include_subtitle', 'include_subtitle'),
            ('simplify_title', 'simplify_title'),
            ('keep_existing_genres', 'keep_existing_genres'),
            ('authors_as_moods', 'store_authors_as_moods'),
            ('series_as_moods', 'series_as_moods'),
            ('work_identity_as_mood', 'store_work_identity_as_mood'),
            ('extended_player_metadata', 'store_extended_player_metadata'),
            ('embedded_series_fallback', 'embedded_series_fallback'),
            ('embedded_contributor_fallback', 'embedded_contributor_fallback'),
            ('author_genres', 'author_genres'),
        ), 'metadata')

    if 'artwork' in document:
        artwork = require_object(document['artwork'], 'artwork', (
            'preference', 'requested_size',
        ))
        if 'preference' in artwork:
            values['artwork_preference'] = require_choice(
                artwork['preference'], 'artwork.preference',
                ('local_first', 'audible_first', 'local_only', 'audible_only'),
            )
        if 'requested_size' in artwork:
            values['image_size'] = require_integer(
                artwork['requested_size'], 'artwork.requested_size',
                choices=(500, 1000, 2000, 3000),
            )

    if 'network' in document:
        network = require_object(document['network'], 'network', (
            'attempts', 'timeout_seconds', 'search_request_budget', 'search_timeout_seconds',
        ))
        if 'attempts' in network:
            values['request_retries'] = require_integer(
                network['attempts'], 'network.attempts', 1, 5
            )
        if 'timeout_seconds' in network:
            values['request_timeout'] = require_integer(
                network['timeout_seconds'], 'network.timeout_seconds', 10, 120
            )

        if 'search_request_budget' in network:
            values['search_request_budget'] = require_integer(
                network['search_request_budget'], 'network.search_request_budget', choices=(12, 24, 48))
        if 'search_timeout_seconds' in network:
            values['search_timeout'] = require_integer(
                network['search_timeout_seconds'], 'network.search_timeout_seconds', choices=(30, 60, 90, 180))

    if 'logging' in document:
        logging = require_object(document['logging'], 'logging', ('level',))
        if 'level' in logging:
            values['logging_level'] = require_choice(
                logging['level'], 'logging.level', ('DEBUG', 'INFO', 'WARN', 'ERROR')
            )

    return {
        'values': values,
        'secret_path': secret_path,
        'config_signature': file_signature(path),
        'secret_signature': file_signature(secret_path) if secret_path else None,
    }
