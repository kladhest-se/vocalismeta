# coding: utf-8
"""VocalisMeta metadata agent for Plex Media Server."""

from __future__ import unicode_literals

import datetime
import json
import os
import re
from time import sleep

from audible_core import (
    as_bool,
    author_id_from_guid,
    author_name_from_guid,
    author_ratio,
    author_name_from_id,
    image_candidates,
    catalog_url,
    display_title,
    search_result_label,
    find_asin,
    filename_author,
    find_region,
    find_region_override,
    genres,
    is_preorder,
    make_author_id,
    make_id,
    language_label,
    normalize_text,
    people,
    primary_title,
    product_abridged,
    products_from_response,
    rating_out_of_ten,
    REGION_TLDS,
    release_date,
    score_author,
    score_product,
    search_title_variants,
    sequence_label,
    series_entries,
    sort_title,
    split_id,
    strip_identity_hints,
    summary,
    text_field,
    to_text,
    unique_authors,
    valid_asin,
)
from embedded_tags import read_embedded_metadata
from embedded_artwork import read_embedded_cover
from local_artwork import MAX_COVER_BYTES, find_local_cover, image_type, poster_key, read_cover
from googlebooks_core import (
    cover_urls as googlebooks_cover_urls,
    isbn_url as googlebooks_isbn_url,
    score_volume as score_googlebooks_volume,
    search_url as googlebooks_search_url,
    volume_categories as googlebooks_categories,
    volume_date as googlebooks_date,
    volume_description as googlebooks_description,
    volume_isbns as googlebooks_isbns,
    volumes_from_response as googlebooks_volumes,
)
from librivox_core import (
    authors as librivox_authors,
    book_id as librivox_book_id,
    book_url as librivox_book_url,
    books_from_response as librivox_books,
    copyright_year as librivox_year,
    cover_urls as librivox_cover_urls,
    description as librivox_description,
    find_book_id as find_librivox_id,
    genres as librivox_genres,
    has_source_hint as has_librivox_source_hint,
    language as librivox_language,
    make_id as make_librivox_id,
    readers as librivox_readers,
    score_book as score_librivox_book,
    search_result_label as librivox_result_label,
    search_url as librivox_search_url,
    split_id as split_librivox_id,
    strip_book_id_hint as strip_librivox_id_hint,
    valid_books_response as valid_librivox_response,
)
from openlibrary_core import (
    cover_urls as openlibrary_cover_urls,
    document_isbns as openlibrary_isbns,
    document_subjects as openlibrary_subjects,
    document_summary as openlibrary_summary,
    document_year as openlibrary_year,
    documents_from_response as openlibrary_documents,
    equivalent_isbns as openlibrary_equivalent_isbns,
    isbn_search_url as openlibrary_isbn_search_url,
    normalize_work_id as openlibrary_normalize_work_id,
    product_isbns,
    score_document as score_openlibrary_document,
    search_url as openlibrary_search_url,
    work_description as openlibrary_work_description,
    work_identity as openlibrary_work_identity,
    work_url as openlibrary_work_url,
)
from request_tools import RequestBudget, backoff_seconds, should_retry, status_from_error
from config_core import ConfigError, file_signature, load_config_file
from identity_core import book_identity, split_book_identity
from client_metadata_core import (
    audible_contributor_tags,
    librivox_contributor_tags,
    openlibrary_contributor_tags,
    production_type as client_production_type,
    rating_count as client_rating_count,
)

AGENT_NAME = 'VocalisMeta Agent'
VERSION = '0.1.1'
SERIES_MOOD_PREFIX = 'Series: '
SEQUENCE_MOOD_PREFIX = 'Sequence: '
LANGUAGE_MOOD_PREFIX = 'Language: '
EDITION_MOOD_PREFIX = 'Edition: '
WORK_ID_MOOD_PREFIX = 'Work-ID: '
CONTRIBUTOR_ID_MOOD_PREFIX = 'Contributor-ID: '
WORK_PUBLISHED_MOOD_PREFIX = 'Work-Published: '
RATING_SOURCE_MOOD_PREFIX = 'Rating-Source: '
RATING_COUNT_MOOD_PREFIX = 'Rating-Count: '
PRODUCTION_MOOD_PREFIX = 'Production: '
V3_MOOD_PREFIXES = (
    CONTRIBUTOR_ID_MOOD_PREFIX, WORK_PUBLISHED_MOOD_PREFIX,
    RATING_SOURCE_MOOD_PREFIX, RATING_COUNT_MOOD_PREFIX,
    PRODUCTION_MOOD_PREFIX,
)
MAX_MEDIA_PARTS = 256
MAX_FALLBACK_REGIONS = 4
AUDIBLE_SEARCH_CACHE_SECONDS = 300
LIBRIVOX_SEARCH_CACHE_SECONDS = 300
BOOK_SEARCH_CACHE_SECONDS = 300
UNKNOWN_VALUES = ('', '[Unknown Album]', '[Unknown Artist]', 'Unknown Artist')
API_KEY_RE = re.compile(r'([?&]key=)[^&]+', re.I)

CONFIG_STATE = {
    'path': None,
    'observed_config_signature': None,
    'watch_secret_path': None,
    'observed_secret_signature': None,
    'values': {},
    'has_good': False,
    'reported_error': None,
}


def raw_pref(name, default=None):
    try:
        value = Prefs[name]
        return default if value is None else value
    except Exception:
        return default


def config_log(level, message, *args):
    """Log without consulting pref(), which would recurse into the loader."""
    values = ('[%s %s] ' + message, AGENT_NAME, VERSION) + args
    if level == 'DEBUG':
        Log.Debug(*values)
    elif level == 'WARN':
        Log.Warn(*values)
    elif level == 'ERROR':
        Log.Error(*values)
    else:
        Log.Info(*values)


def observed_signature(path):
    if not path:
        return None
    try:
        return file_signature(path)
    except ConfigError as error:
        return ('unavailable', to_text(error))


def external_config_path():
    configured = to_text(raw_pref('config_file', '')).strip()
    if configured:
        return configured
    configured = to_text(os.environ.get('VOCALISMETA_CONFIG_FILE', '')).strip()
    if configured:
        return configured
    # Compatibility with deployments created before the VocalisMeta rename.
    return to_text(os.environ.get('SPOKENMETA_CONFIG_FILE', '')).strip()


def reset_config(path=None):
    CONFIG_STATE.update({
        'path': path,
        'observed_config_signature': None,
        'watch_secret_path': None,
        'observed_secret_signature': None,
        'values': {},
        'has_good': False,
        'reported_error': None,
    })


def external_config_values(force=False):
    path = external_config_path()
    if not path:
        if CONFIG_STATE['path'] is not None:
            reset_config()
        return {}

    path_changed = path != CONFIG_STATE['path']
    if path_changed:
        reset_config(path)

    config_signature = observed_signature(path)
    secret_signature = observed_signature(CONFIG_STATE['watch_secret_path'])
    if (
        not force
        and config_signature == CONFIG_STATE['observed_config_signature']
        and secret_signature == CONFIG_STATE['observed_secret_signature']
    ):
        return CONFIG_STATE['values']

    try:
        loaded = load_config_file(path)
        CONFIG_STATE.update({
            'observed_config_signature': loaded['config_signature'],
            'watch_secret_path': loaded['secret_path'],
            'observed_secret_signature': loaded['secret_signature'],
            'values': loaded['values'],
            'has_good': True,
            'reported_error': None,
        })
        config_log('INFO', 'Loaded filesystem configuration: %s', path)
    except ConfigError as error:
        if error.watch_path:
            CONFIG_STATE['watch_secret_path'] = error.watch_path
            secret_signature = observed_signature(error.watch_path)
        CONFIG_STATE['observed_config_signature'] = config_signature
        CONFIG_STATE['observed_secret_signature'] = secret_signature
        error_revision = (
            path, config_signature, CONFIG_STATE['watch_secret_path'],
            secret_signature, to_text(error),
        )
        if CONFIG_STATE['has_good'] and not path_changed:
            if error_revision != CONFIG_STATE['reported_error']:
                config_log(
                    'ERROR',
                    'Rejected configuration reload; keeping last known good values: %s',
                    to_text(error),
                )
        else:
            CONFIG_STATE['values'] = {}
            CONFIG_STATE['has_good'] = False
            if error_revision != CONFIG_STATE['reported_error']:
                config_log(
                    'ERROR',
                    'Rejected filesystem configuration; using Plex preferences: %s',
                    to_text(error),
                )
        CONFIG_STATE['reported_error'] = error_revision
    return CONFIG_STATE['values']


def pref(name, default=None):
    value = raw_pref(name, default)
    if name == 'config_file':
        return value
    overrides = external_config_values()
    return overrides[name] if name in overrides else value


def log(level, message, *args):
    configured = to_text(pref('logging_level', 'INFO')).upper()
    order = {'DEBUG': 10, 'INFO': 20, 'WARN': 30, 'ERROR': 40}
    if order.get(level, 20) < order.get(configured, 20):
        return
    values = ('[%s %s] ' + message, AGENT_NAME, VERSION) + args
    if level == 'DEBUG':
        Log.Debug(*values)
    elif level == 'WARN':
        Log.Warn(*values)
    elif level == 'ERROR':
        Log.Error(*values)
    else:
        Log.Info(*values)


def diagnostic_value(value):
    """Return a single-line quoted value for structured Plex log records."""
    value = to_text(value)
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\r', ' ').replace('\n', ' ')
    return '"%s"' % value


def log_album_search_summary(
    outcome, title, author, provider='', identity='', score=None,
    reason='', author_source='unknown', candidate_count=0,
    catalog_hits=0, audible_queries=0, manual=False, provider_failures=0
):
    fields = [
        'outcome=' + diagnostic_value(outcome),
        'provider=' + diagnostic_value(provider or 'none'),
        'identity=' + diagnostic_value(identity),
        'score=' + diagnostic_value('none' if score is None else score),
        'title=' + diagnostic_value(title),
        'author=' + diagnostic_value(author),
        'author_source=' + diagnostic_value(author_source),
        'candidates=' + diagnostic_value(candidate_count),
        'catalog_hits=' + diagnostic_value(catalog_hits),
        'audible_queries=' + diagnostic_value(audible_queries),
        'provider_failures=' + diagnostic_value(provider_failures),
        'manual=' + diagnostic_value('true' if manual else 'false'),
        'reason=' + diagnostic_value(reason),
    ]
    log('INFO', 'SEARCH_SUMMARY ' + ' '.join(fields))


def contract_v3_tag_count(container):
    count = 0
    for item in container:
        item = to_text(item).strip()
        for prefix in V3_MOOD_PREFIXES:
            if item.startswith(prefix):
                count += 1
                break
    return count


def relationship_tag_count(container, prefix):
    count = 0
    for item in container:
        if to_text(item).strip().startswith(prefix):
            count += 1
    return count


def log_album_update_summary(
    metadata, outcome, provider, reason, title='', forced=False
):
    work_identity = ''
    identities = existing_work_identities(metadata.moods)
    if identities:
        work_identity = identities[0]
    try:
        poster_count = len(metadata.posters)
    except Exception:
        poster_count = 0
    fields = [
        'outcome=' + diagnostic_value(outcome),
        'provider=' + diagnostic_value(provider),
        'identity=' + diagnostic_value(metadata.id),
        'title=' + diagnostic_value(title or metadata.title),
        'work_identity=' + diagnostic_value(work_identity),
        'extended_tags=' + diagnostic_value(
            contract_v3_tag_count(metadata.moods)
        ),
        'series_tags=' + diagnostic_value(
            relationship_tag_count(metadata.moods, SERIES_MOOD_PREFIX)
        ),
        'sequence_tags=' + diagnostic_value(
            relationship_tag_count(metadata.moods, SEQUENCE_MOOD_PREFIX)
        ),
        'posters=' + diagnostic_value(poster_count),
        'forced=' + diagnostic_value('true' if forced else 'false'),
        'reason=' + diagnostic_value(reason),
    ]
    log('INFO', 'UPDATE_SUMMARY ' + ' '.join(fields))


def ValidatePrefs():
    external_config_values(force=True)
    log('INFO', 'Preferences updated')


def Start():
    HTTP.CacheTime = CACHE_1WEEK
    HTTP.Headers['User-Agent'] = 'VocalisMeta.bundle/%s PlexMetadataAgent' % VERSION
    HTTP.Headers['Accept'] = 'application/json'
    HTTP.Headers['Accept-Encoding'] = 'gzip'
    log('INFO', 'Started')


def redact_url(url):
    return API_KEY_RE.sub(r'\1REDACTED', to_text(url))


def set_request_status(request_status, ok, reason, status, attempts):
    if request_status is None:
        return
    request_status['ok'] = bool(ok)
    request_status['reason'] = reason
    request_status['status'] = status
    request_status['attempts'] = attempts


def request_json(url, cache_time=CACHE_1DAY, request_status=None, headers=None):
    last_error = None
    last_reason = 'provider_unavailable'
    last_status = None
    last_attempt = 0
    try:
        attempts = max(1, min(5, int(pref('request_retries', 3))))
    except (TypeError, ValueError):
        attempts = 3
    try:
        timeout = max(10, min(120, int(pref('request_timeout', 45))))
    except (TypeError, ValueError):
        timeout = 45
    effective_cache_time = cache_time
    for attempt in range(1, attempts + 1):
        last_attempt = attempt
        try:
            response = HTTP.Request(
                url, timeout=timeout, cacheTime=effective_cache_time,
                immediate=True, headers=headers or {}
            )
            try:
                body = response.content
            except AttributeError:
                body = str(response)
            try:
                payload = json.loads(body)
            except Exception as error:
                last_error = error
                last_reason = 'invalid_response'
                last_status = None
                if attempt >= attempts:
                    break
                # A second request against the same cached malformed body cannot
                # recover. Bypass Plex's HTTP cache for retries after a JSON
                # decoding failure while retaining the caller's normal cache
                # policy for valid responses.
                effective_cache_time = 0
                delay = backoff_seconds(attempt, error, maximum=30)
                log(
                    'WARN',
                    'Malformed provider response (attempt=%d/%d); '
                    'retrying in %ds: %s',
                    attempt, attempts, delay, redact_url(url)
                )
                if delay:
                    sleep(delay)
                continue
            set_request_status(request_status, True, 'ok', None, attempt)
            return payload
        except Exception as error:
            last_error = error
            status = status_from_error(error)
            last_reason = 'provider_unavailable'
            last_status = status
            if attempt >= attempts or not should_retry(status):
                break
            delay = backoff_seconds(attempt, error, maximum=30)
            log(
                'WARN',
                'Transient request failure (status=%s, attempt=%d/%d); retrying in %ds: %s',
                status if status is not None else 'network', attempt, attempts,
                delay, redact_url(error)
            )
            if delay:
                sleep(delay)
    if last_reason == 'invalid_response':
        log(
            'ERROR', 'Invalid JSON response after %d attempt(s): %s (%s)',
            last_attempt, redact_url(url), redact_url(last_error)
        )
    else:
        log(
            'ERROR', 'Request failed (status=%s, attempts=%d): %s (%s)',
            status_from_error(last_error) if last_error else 'unknown',
            last_attempt, redact_url(url), redact_url(last_error)
        )
    set_request_status(
        request_status, False, last_reason,
        last_status if last_status is not None else (
            'invalid_response' if last_reason == 'invalid_response' else 'network'
        ),
        last_attempt
    )
    return {}


def new_provider_status():
    return {'successes': 0, 'failures': 0, 'reasons': []}


def record_provider_response(provider_status, request_status, schema_valid):
    if provider_status is None:
        return
    request_ok = bool(request_status and request_status.get('ok'))
    if request_ok and schema_valid:
        provider_status['successes'] = provider_status.get('successes', 0) + 1
        return
    provider_status['failures'] = provider_status.get('failures', 0) + 1
    reason = 'invalid_response'
    if request_status and not request_ok:
        reason = request_status.get('reason') or 'provider_unavailable'
    reasons = provider_status.get('reasons') or []
    if reason not in reasons:
        reasons.append(reason)
    provider_status['reasons'] = reasons


def provider_failure_details(provider_states):
    failures = 0
    successes = 0
    providers = []
    reasons = []
    for provider_name, provider_status in provider_states:
        current_failures = provider_status.get('failures', 0)
        failures += current_failures
        successes += provider_status.get('successes', 0)
        if current_failures and provider_name not in providers:
            providers.append(provider_name)
        for reason in provider_status.get('reasons') or []:
            if reason not in reasons:
                reasons.append(reason)
    if not failures:
        return '', '', 0
    provider = providers[0] if len(providers) == 1 else 'multiple'
    if successes:
        reason = 'partial_provider_failure'
    elif reasons == ['invalid_response']:
        reason = 'invalid_provider_response'
    else:
        reason = 'provider_unavailable'
    return provider, reason, failures


def custom_api_base():
    return to_text(pref('api_base_url', '')).strip()


def media_value(media, name):
    try:
        if name == 'album':
            value = media.album
        elif name == 'artist':
            value = media.artist
        elif name == 'filename':
            value = media.filename
        elif name == 'name':
            value = media.name
        elif name == 'parentGUID':
            value = media.parentGUID
        elif name == 'title':
            value = media.title
        elif name == 'year':
            value = media.year
        else:
            return ''
        return to_text(value)
    except Exception:
        return ''


def media_parent_guid(media):
    """Read the parent GUID variants exposed by different Plex builds."""
    try:
        value = media.parentGUID
        if value:
            return to_text(value)
    except Exception:
        pass
    try:
        value = media.parent_guid
        if value:
            return to_text(value)
    except Exception:
        pass
    try:
        value = media.parentGuid
        if value:
            return to_text(value)
    except Exception:
        pass
    return ''


def search_title(media, manual):
    if manual and media_value(media, 'name'):
        return media_value(media, 'name')
    return media_value(media, 'album') or media_value(media, 'title') or media_value(media, 'name')


def media_filename(media):
    direct = media_value(media, 'filename')
    if direct:
        return direct
    try:
        return to_text(media.items[0].parts[0].file)
    except Exception:
        return ''


def media_file_paths(media):
    paths = []
    seen = set()
    try:
        for item in media.items:
            for part in item.parts:
                path = to_text(part.file).strip()
                if path and path not in seen:
                    seen.add(path)
                    paths.append(path)
                    if len(paths) >= MAX_MEDIA_PARTS:
                        return paths
    except Exception:
        pass
    direct = media_value(media, 'filename').strip()
    if direct and direct not in seen and len(paths) < MAX_MEDIA_PARTS:
        paths.append(direct)
    return paths


def media_file_path(media):
    paths = media_file_paths(media)
    return paths[0] if paths else ''


def embedded_identity_from_paths(paths):
    combined = {
        'asin': None, 'librivox_id': None, 'region': None,
        'format': None, 'isbns': [],
        'authors': [], 'narrators': [], 'language': None, 'abridged': None,
        'series': None, 'series_sequence': None,
    }
    formats = []
    for path in paths:
        identity = read_embedded_metadata(path)
        if identity.get('format') and identity.get('format') not in formats:
            formats.append(identity.get('format'))
        if not combined['asin'] and identity.get('asin'):
            combined['asin'] = identity.get('asin')
        if not combined['librivox_id'] and identity.get('librivox_id'):
            combined['librivox_id'] = identity.get('librivox_id')
        if not combined['region'] and identity.get('region'):
            combined['region'] = identity.get('region')
        for isbn in identity.get('isbns') or []:
            if isbn not in combined['isbns']:
                combined['isbns'].append(isbn)
        for author in identity.get('authors') or []:
            if author not in combined['authors']:
                combined['authors'].append(author)
        for narrator in identity.get('narrators') or []:
            if narrator not in combined['narrators']:
                combined['narrators'].append(narrator)
        if not combined['language'] and identity.get('language'):
            combined['language'] = identity.get('language')
        if combined['abridged'] is None and identity.get('abridged') is not None:
            combined['abridged'] = identity.get('abridged')
        if not combined['series'] and identity.get('series'):
            combined['series'] = identity.get('series')
        if not combined['series_sequence'] and identity.get('series_sequence'):
            combined['series_sequence'] = identity.get('series_sequence')
    combined['format'] = '/'.join(formats) if formats else None
    return combined


def number_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def media_duration_minutes(media):
    """Return a non-duplicated total duration from Plex's millisecond fields."""
    total = 0.0
    try:
        for item in media.items:
            part_durations = []
            for part in item.parts:
                try:
                    part_duration = part.duration
                except AttributeError:
                    part_duration = 0
                part_durations.append(number_value(part_duration))
            part_total = 0
            for part_duration_value in part_durations:
                part_total += part_duration_value
            try:
                item_duration = item.duration
            except AttributeError:
                item_duration = 0
            total += part_total or number_value(item_duration)
    except Exception:
        total = 0.0
    if not total:
        try:
            media_duration = media.duration
        except AttributeError:
            media_duration = 0
        total = number_value(media_duration)
    if total > 0:
        return total / 60000.0
    return plex_tree_duration_minutes(media)


def plex_tree_duration_minutes(media):
    """Recover album duration from Plex when AgentKit omits media durations."""
    try:
        identifier = to_text(media.id).strip()
    except Exception:
        identifier = ''
    if not re.match(r'^\d+$', identifier):
        return None
    url = 'http://127.0.0.1:32400/library/metadata/%s/tree' % identifier
    try:
        response = HTTP.Request(url, timeout=10, cacheTime=0)
        try:
            body = response.content
        except Exception:
            body = str(response)
        body = to_text(body)
    except Exception as error:
        log('DEBUG', 'Could not read Plex duration tree for %s: %s', identifier, error)
        return None

    durations = re.findall(
        r'<Track\b[^>]*\bduration=["\']([0-9]+)["\']', body, re.I
    )
    if not durations:
        durations = re.findall(
            r'<Part\b[^>]*\bduration=["\']([0-9]+)["\']', body, re.I
        )
    total = 0.0
    for duration in durations:
        total += number_value(duration)
    return total / 60000.0 if total > 0 else None


def abridged_hint(*values):
    text = ' '.join([to_text(value) for value in values]).lower()
    if re.search(r'\bunabridged\b', text):
        return False
    if re.search(r'(?<!un)\babridged\b', text):
        return True
    return None


def artwork_from_paths(paths):
    # Explicit sidecar covers win over embedded art across the whole book.
    for path in paths:
        cover = find_local_cover(path)
        if cover:
            return cover
    for path in paths:
        cover = read_embedded_cover(path)
        if cover:
            return cover
    return None


def replace_container(container, values):
    container.clear()
    for value in values:
        value = to_text(value).strip()
        if value:
            container.add(value)


def reserved_mood(value):
    value = to_text(value).strip()
    prefixes = (
        SERIES_MOOD_PREFIX, SEQUENCE_MOOD_PREFIX, LANGUAGE_MOOD_PREFIX,
        EDITION_MOOD_PREFIX, WORK_ID_MOOD_PREFIX,
    ) + V3_MOOD_PREFIXES
    for prefix in prefixes:
        if value.startswith(prefix):
            return True
    return False


def existing_relationship_metadata(container):
    """Read the last valid v1 relationship values already stored by Plex."""
    authors = []
    series = []
    indexes = {}
    sequences = {}
    language = ''
    abridged = None
    for item in container:
        item = to_text(item).strip()
        if not item:
            continue
        if item.startswith(SERIES_MOOD_PREFIX):
            title = item[len(SERIES_MOOD_PREFIX):].strip()
            key = normalize_text(title)
            if title and key and key not in indexes:
                indexes[key] = len(series)
                series.append({'title': title, 'sequence': ''})
            continue
        if item.startswith(SEQUENCE_MOOD_PREFIX):
            value = item[len(SEQUENCE_MOOD_PREFIX):].strip()
            if ' #' in value:
                title, sequence = value.rsplit(' #', 1)
                key = normalize_text(title)
                sequence = sequence_label(sequence)
                if key and sequence and key not in sequences:
                    sequences[key] = sequence
            continue
        if item.startswith(LANGUAGE_MOOD_PREFIX):
            if not language:
                language = item[len(LANGUAGE_MOOD_PREFIX):].strip()
            continue
        if item == EDITION_MOOD_PREFIX + 'Abridged':
            abridged = True
            continue
        if item == EDITION_MOOD_PREFIX + 'Unabridged':
            abridged = False
            continue
        if not reserved_mood(item) and item not in authors:
            authors.append(item)
    for entry in series:
        key = normalize_text(entry.get('title'))
        if key in sequences:
            entry['sequence'] = sequences[key]
    return {
        'authors': authors,
        'series': series,
        'language': language,
        'abridged': abridged,
    }


def preserve_relationship_fallbacks(
    metadata, authors, series, language='', abridged=None, provider='provider'
):
    """Keep last-known-good v1 tags when a refresh response is partial."""
    previous = existing_relationship_metadata(metadata.moods)
    preserved = []
    if not authors and previous['authors']:
        authors = previous['authors']
        preserved.append('authors')
    if not series and previous['series']:
        series = previous['series']
        preserved.append('series')
    if not language and previous['language']:
        language = previous['language']
        preserved.append('language')
    if abridged is None and previous['abridged'] is not None:
        abridged = previous['abridged']
        preserved.append('edition')
    if preserved:
        log(
            'INFO',
            'Preserved last-known-good %s metadata because the current %s response omitted it',
            ', '.join(preserved), provider,
        )
    return authors, series, language, abridged


def embedded_series_entries(embedded):
    if not isinstance(embedded, dict) or not embedded.get('series'):
        return []
    return series_entries({'series': [{
        'title': embedded.get('series'),
        'sequence': embedded.get('series_sequence') or '',
    }]})


def sort_title_with_series_fallback(product, title, fallback_entries):
    if series_entries(product):
        return sort_title(product)
    if fallback_entries:
        return sort_title({'title': title, 'series': fallback_entries})
    return title


def work_identity_enabled():
    return as_bool(pref('store_work_identity_as_mood', True), True)


def extended_player_metadata_enabled():
    return as_bool(pref('store_extended_player_metadata', True), True)


def prune_disabled_contract_moods(container):
    """Remove only disabled optional-contract values from Plex Moods."""
    prefixes = []
    if not work_identity_enabled():
        prefixes.append(WORK_ID_MOOD_PREFIX)
    if not extended_player_metadata_enabled():
        prefixes.extend(V3_MOOD_PREFIXES)
    if not prefixes:
        return
    current = [to_text(item).strip() for item in container]
    values = []
    for item in current:
        remove = False
        for prefix in prefixes:
            if item.startswith(prefix):
                remove = True
                break
        if item and not remove:
            values.append(item)
    if values != current:
        replace_container(container, values)


def valid_work_identity(value):
    value = to_text(value).strip()
    if not value.lower().startswith('openlibrary:'):
        return ''
    work_id = openlibrary_normalize_work_id(value.split(':', 1)[1])
    return 'openlibrary:' + work_id if work_id else ''


def existing_work_identities(container):
    values = []
    if not work_identity_enabled():
        return values
    for item in container:
        item = to_text(item).strip()
        if not item.startswith(WORK_ID_MOOD_PREFIX):
            continue
        identity = valid_work_identity(item[len(WORK_ID_MOOD_PREFIX):])
        if identity:
            values.append(identity)
            break
    return values


def replace_work_identity(container, identity):
    values = []
    for item in container:
        item = to_text(item).strip()
        if item and not item.startswith(WORK_ID_MOOD_PREFIX):
            values.append(item)
    identity = valid_work_identity(identity)
    if identity:
        values.append(WORK_ID_MOOD_PREFIX + identity)
    replace_container(container, values)


def existing_v3_enrichment_tags(container):
    values = []
    if not extended_player_metadata_enabled():
        return values
    for item in container:
        item = to_text(item).strip()
        if re.match(r'^Work-Published: [1-9][0-9]{0,3}$', item):
            values.append(item)
        elif re.match(
            r'^Contributor-ID: (?:author|narrator):(?:audible:[A-Z0-9]{10}|librivox:[1-9][0-9]{0,9}|openlibrary:OL[0-9]+A) = .+$',
            item,
        ):
            values.append(item)
        elif item in (
            'Production: Single narrator', 'Production: Multi-narrator',
            'Production: Full cast', 'Production: Dramatized',
            'Production: Community recording',
        ):
            values.append(item)
        elif item == 'Rating-Source: Audible':
            values.append(item)
        elif re.match(r'^Rating-Count: [0-9]+$', item):
            values.append(item)
    return values


def v3_tag_key(value):
    value = to_text(value).strip()
    if value.startswith(CONTRIBUTOR_ID_MOOD_PREFIX) and ' = ' in value:
        return value.split(' = ', 1)[0].lower()
    for prefix in (
        WORK_PUBLISHED_MOOD_PREFIX, PRODUCTION_MOOD_PREFIX,
        RATING_SOURCE_MOOD_PREFIX, RATING_COUNT_MOOD_PREFIX,
    ):
        if value.startswith(prefix):
            return prefix.lower()
    return value.lower()


def merge_v3_tags(existing, current):
    """Prefer current provider evidence, preserving valid omitted values."""
    values = []
    positions = {}
    for item in list(existing or []) + list(current or []):
        item = to_text(item).strip()
        if not item:
            continue
        key = v3_tag_key(item)
        if key in positions:
            values[positions[key]] = item
        else:
            positions[key] = len(values)
            values.append(item)
    return values


def existing_work_publication_year(container):
    for item in existing_v3_enrichment_tags(container):
        if item.startswith(WORK_PUBLISHED_MOOD_PREFIX):
            return item[len(WORK_PUBLISHED_MOOD_PREFIX):]
    return ''


def replace_openlibrary_v3_metadata(container, document):
    if not extended_player_metadata_enabled():
        return
    values = []
    for item in container:
        item = to_text(item).strip()
        if item.startswith(WORK_PUBLISHED_MOOD_PREFIX):
            continue
        if item.startswith(
            CONTRIBUTOR_ID_MOOD_PREFIX + 'author:openlibrary:'
        ):
            continue
        if item:
            values.append(item)
    year = openlibrary_year(document)
    if year:
        values.append(WORK_PUBLISHED_MOOD_PREFIX + to_text(year))
    values.extend(openlibrary_contributor_tags(document))
    replace_container(container, values)


def audible_v3_tags(product):
    if not extended_player_metadata_enabled():
        return []
    values = audible_contributor_tags(product)
    if rating_out_of_ten(product) is not None:
        values.append(RATING_SOURCE_MOOD_PREFIX + 'Audible')
        count = client_rating_count(product)
        if count is not None:
            values.append(RATING_COUNT_MOOD_PREFIX + to_text(count))
    production = client_production_type(product)
    if production:
        values.append(PRODUCTION_MOOD_PREFIX + production)
    return values


def librivox_v3_tags(book):
    if not extended_player_metadata_enabled():
        return []
    values = librivox_contributor_tags(book)
    values.append(PRODUCTION_MOOD_PREFIX + 'Community recording')
    return values


def relationship_moods(
    authors, series, language='', abridged=None, work_identities=None,
    player_tags=None
):
    """Build stable, client-readable relationship tags for Plex Moods."""
    moods = []
    if as_bool(pref('store_authors_as_moods', True), True):
        moods.extend(authors or [])
    if as_bool(pref('series_as_moods', True), True):
        for item in series or []:
            title = text_field(item.get('title'))
            if not title:
                continue
            moods.append(SERIES_MOOD_PREFIX + title)
            sequence = sequence_label(item.get('sequence'))
            if sequence:
                moods.append(SEQUENCE_MOOD_PREFIX + '%s #%s' % (title, sequence))
    visible_language = language_label(language)
    if visible_language:
        moods.append(LANGUAGE_MOOD_PREFIX + visible_language)
    if abridged is True:
        moods.append(EDITION_MOOD_PREFIX + 'Abridged')
    elif abridged is False:
        moods.append(EDITION_MOOD_PREFIX + 'Unabridged')
    if work_identity_enabled():
        for identity in work_identities or []:
            identity = valid_work_identity(identity)
            if identity:
                moods.append(WORK_ID_MOOD_PREFIX + identity)
    if extended_player_metadata_enabled():
        moods.extend(player_tags or [])
    return moods


def append_search_result(results, identifier, name, lang, score, year=None):
    options = {
        'id': identifier,
        'name': name,
        'lang': lang,
        'score': score,
    }
    if year:
        options['year'] = year
    results.Append(MetadataSearchResult(**options))


def set_value(metadata, field, value, force, authoritative=False):
    if value is None or value == '':
        return
    if field == 'summary':
        if authoritative or force or not metadata.summary:
            metadata.summary = value
    elif field == 'studio':
        if authoritative or force or not metadata.studio:
            metadata.studio = value
    elif field == 'title':
        if authoritative or force or not metadata.title:
            metadata.title = value
    elif field == 'title_sort':
        if authoritative or force or not metadata.title_sort:
            metadata.title_sort = value


def artwork_policy():
    policy = to_text(pref('artwork_preference', '')).strip().lower()
    if policy in ('local_first', 'audible_first', 'local_only', 'audible_only'):
        return policy
    # Compatibility with the 1.0 preference if Plex retained it.
    return 'audible_only' if as_bool(pref('replace_artwork', True), True) else 'audible_first'


def maximum_results():
    try:
        return max(1, min(50, int(pref('max_results', 20))))
    except (TypeError, ValueError):
        return 20


def audible_regions(primary):
    primary = to_text(primary).strip().lower()
    if primary not in REGION_TLDS:
        primary = 'us'
    output = [primary]
    raw = to_text(pref('fallback_regions', ''))
    for region in re.split(r'[,;\s]+', raw.lower()):
        if region in REGION_TLDS and region not in output:
            output.append(region)
            if len(output) >= MAX_FALLBACK_REGIONS + 1:
                break
    return output


def openlibrary_enabled():
    return as_bool(pref('openlibrary_enabled', True), True)


def googlebooks_api_key():
    return to_text(pref('googlebooks_api_key', '')).strip()


def googlebooks_request_headers():
    key = googlebooks_api_key()
    return {'X-Goog-Api-Key': key} if key else {}


def googlebooks_enabled():
    return (
        as_bool(pref('googlebooks_enabled', True), True)
        and bool(googlebooks_api_key())
    )


def librivox_enabled():
    return as_bool(pref('librivox_enabled', False), False)


def librivox_mode():
    if not librivox_enabled():
        return 'disabled'
    mode = to_text(pref('librivox_mode', 'fallback')).strip().lower()
    if mode in ('hinted_only', 'fallback', 'preferred'):
        return mode
    return 'fallback'


def embedded_series_enabled():
    return as_bool(pref('embedded_series_fallback', True), True)


def embedded_contributors_enabled():
    return as_bool(pref('embedded_contributor_fallback', True), True)


def enrichment_providers():
    order = to_text(pref('enrichment_order', 'openlibrary_first')).strip().lower()
    if order == 'googlebooks_first':
        return ['googlebooks', 'openlibrary']
    return ['openlibrary', 'googlebooks']


def enrichment_request_limit():
    try:
        return max(1, min(50, int(pref('enrichment_request_budget', 8))))
    except (TypeError, ValueError):
        return 8


def use_enrichment_request(budget, provider):
    if budget is None or budget.take(provider):
        return True
    log(
        'WARN', 'Enrichment request budget exhausted before %s request', provider
    )
    return False


def add_local_poster(metadata, cover, sort_order):
    data = read_cover(cover)
    if not data:
        return None
    key = poster_key(cover)
    metadata.posters[key] = Proxy.Media(data, sort_order=sort_order)
    return key


def add_remote_poster(metadata, image_urls, sort_order):
    try:
        attempts = max(1, min(5, int(pref('request_retries', 3))))
    except (TypeError, ValueError):
        attempts = 3
    try:
        timeout = max(10, min(120, int(pref('request_timeout', 45))))
    except (TypeError, ValueError):
        timeout = 45
    for image_url in image_urls or []:
        for attempt in range(1, attempts + 1):
            try:
                response = HTTP.Request(
                    image_url, timeout=timeout, cacheTime=CACHE_1WEEK, immediate=True
                )
                try:
                    body = response.content
                except AttributeError:
                    body = response
                if not body or len(body) > MAX_COVER_BYTES or not image_type(body[:16]):
                    raise ValueError('response was not a supported image')
                metadata.posters[image_url] = Proxy.Media(body, sort_order=sort_order)
                return image_url
            except Exception as error:
                status = status_from_error(error)
                retryable = status is None or should_retry(status)
                if attempt >= attempts or not retryable:
                    log('WARN', 'Remote artwork candidate failed: %s (%s)', image_url, error)
                    break
                delay = backoff_seconds(attempt, error, maximum=30)
                log(
                    'WARN',
                    'Transient artwork failure (status=%s, attempt=%d/%d); retrying in %ds: %s',
                    status if status is not None else 'network', attempt, attempts, delay, error
                )
                if delay:
                    sleep(delay)
    return None


def apply_artwork(metadata, media, remote_urls):
    policy = artwork_policy()
    local_cover = artwork_from_paths(media_file_paths(media))
    poster_keys = []
    try:
        if policy in ('local_first', 'local_only') and local_cover:
            key = add_local_poster(metadata, local_cover, 0)
            if key:
                poster_keys.append(key)
                log('INFO', 'Using local album artwork: %s', local_cover.get('path'))
        if policy in ('audible_first', 'audible_only') and remote_urls:
            key = add_remote_poster(metadata, remote_urls, 0)
            if key:
                poster_keys.append(key)
        if policy == 'local_first' and remote_urls:
            key = add_remote_poster(metadata, remote_urls, 1 if poster_keys else 0)
            if key:
                poster_keys.append(key)
        if policy == 'audible_first' and local_cover:
            key = add_local_poster(metadata, local_cover, 1 if poster_keys else 0)
            if key:
                poster_keys.append(key)
        if poster_keys:
            metadata.posters.validate_keys(poster_keys)
    except Exception as error:
        log('WARN', 'Could not apply %s artwork policy: %s', policy, error)


def fetch_products(region, params, provider_status=None):
    url = catalog_url(region, params, custom_api_base())
    log('DEBUG', 'Audible request: %s', url)
    exact_lookup = params.get('asins') or params.get('author_asins')
    cache_time = CACHE_1DAY if exact_lookup else AUDIBLE_SEARCH_CACHE_SECONDS
    request_status = {}
    response = request_json(url, cache_time, request_status)
    schema_valid = (
        isinstance(response, dict)
        and isinstance(response.get('products'), list)
    )
    record_provider_response(provider_status, request_status, schema_valid)
    return products_from_response(response)


def fetch_product(asin, region, provider_status=None):
    asin = to_text(asin).strip().upper()
    if not valid_asin(asin):
        return None
    products = fetch_products(region, {'asins': asin}, provider_status)
    for product in products:
        if to_text(product.get('asin')).strip().upper() == asin:
            return product
    return None


def ranked_audible_candidates(candidates, title_variants, author, language,
                              duration, narrators, year, abridged, today):
    ranked = []
    for index, item in enumerate(candidates):
        candidate_region, region_index, product = item
        if (
            not as_bool(pref('include_adult', False))
            and as_bool(product.get('is_adult_product'), False)
        ):
            continue
        if as_bool(pref('exclude_preorders', True), True) and is_preorder(product, today):
            continue
        best_score = 0
        for candidate_title in title_variants:
            score = score_product(
                candidate_title, author, language, product, index,
                duration, narrators, year, abridged,
            ) - min(region_index, 3)
            if score > best_score:
                best_score = score
        if best_score >= 45:
            ranked.append((best_score, candidate_region, product))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def has_acceptable_audible_candidate(ranked, threshold):
    for item in ranked:
        if item[0] >= threshold:
            return True
    return False


def log_unmatched_audible(title, author, ranked, threshold, candidate_count=0):
    if ranked:
        descriptions = []
        for item in ranked[:3]:
            descriptions.append('%s (%s, score %d)' % (
                display_title(item[2]), item[1].upper(), item[0]
            ))
        log(
            'INFO',
            'No acceptable Audible match for "%s" by "%s" '
            '(required score %d); best rejected candidates: %s',
            title, author, threshold, '; '.join(descriptions),
        )
    elif candidate_count:
        log(
            'INFO',
            'Audible returned %d catalog candidate(s) for "%s" by "%s", '
            'but none passed the minimum scoring checks',
            candidate_count, title, author,
        )
    else:
        log(
            'INFO',
            'No Audible catalog candidates for "%s" by "%s" after title variants',
            title, author,
        )


def fetch_author(asin, region):
    asin = to_text(asin).strip().upper()
    if not valid_asin(asin):
        return None
    products = fetch_products(region, {
        'author_asins': asin,
        'num_results': 10,
        'products_sort_by': 'Relevance',
    })
    for author in unique_authors(products):
        if to_text(author.get('asin')).strip().upper() == asin:
            return author
    return None


def fetch_openlibrary_documents(title, author='', language='', limit=10, budget=None):
    if not openlibrary_enabled():
        return []
    if not use_enrichment_request(budget, 'Open Library'):
        return []
    url = openlibrary_search_url(title, author, language, limit)
    log('DEBUG', 'Open Library request: %s', url)
    return openlibrary_documents(request_json(url, BOOK_SEARCH_CACHE_SECONDS))


def fetch_openlibrary_isbn(isbn, budget=None):
    url = openlibrary_isbn_search_url(isbn, 10)
    if not url or not openlibrary_enabled():
        return []
    if not use_enrichment_request(budget, 'Open Library'):
        return []
    log('DEBUG', 'Open Library ISBN enrichment request: %s', isbn)
    return openlibrary_documents(request_json(url, BOOK_SEARCH_CACHE_SECONDS))


def fetch_openlibrary_work(document, budget=None):
    url = openlibrary_work_url(document)
    if not url or not openlibrary_enabled():
        return {}
    if not use_enrichment_request(budget, 'Open Library'):
        return {}
    log('DEBUG', 'Open Library Work description request: %s', url)
    response = request_json(url, CACHE_1WEEK)
    return response if isinstance(response, dict) else {}


def best_openlibrary_document(
    product, title, author, language, embedded_isbns=None, budget=None
):
    isbns = []
    for value in list(embedded_isbns or []) + product_isbns(product):
        for isbn in openlibrary_equivalent_isbns(value):
            if isbn not in isbns:
                isbns.append(isbn)
    for isbn in isbns:
        if budget is not None and budget.remaining <= 0:
            break
        for document in fetch_openlibrary_isbn(isbn, budget):
            if isbn in openlibrary_isbns(document):
                log('DEBUG', 'Open Library enrichment matched edition ISBN %s', isbn)
                return document
    if budget is not None and budget.remaining <= 0:
        return None
    ranked = []
    for index, document in enumerate(
        fetch_openlibrary_documents(title, author, language, 10, budget)
    ):
        score = score_openlibrary_document(title, author, language, document, index)
        if score >= 45:
            ranked.append((score, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] >= 80 else None


def fetch_googlebooks_isbn(isbn, budget=None):
    url = googlebooks_isbn_url(isbn, googlebooks_api_key(), 10)
    if not url or not googlebooks_enabled():
        return []
    if not use_enrichment_request(budget, 'Google Books'):
        return []
    log('DEBUG', 'Google Books ISBN enrichment request: %s', isbn)
    return googlebooks_volumes(request_json(
        url, BOOK_SEARCH_CACHE_SECONDS,
        headers=googlebooks_request_headers()
    ))


def fetch_googlebooks_volumes(
    title, author='', language='', limit=10, budget=None
):
    if not googlebooks_enabled():
        return []
    url = googlebooks_search_url(
        title, author, googlebooks_api_key(), language, limit
    )
    if not url:
        return []
    if not use_enrichment_request(budget, 'Google Books'):
        return []
    log('DEBUG', 'Google Books title enrichment request: %s', title)
    return googlebooks_volumes(request_json(
        url, BOOK_SEARCH_CACHE_SECONDS,
        headers=googlebooks_request_headers()
    ))


def fetch_librivox_book(book_id, provider_status=None):
    url = librivox_book_url(book_id)
    if not url:
        return None
    log('DEBUG', 'LibriVox exact project request: %s', book_id)
    request_status = {}
    response = request_json(url, CACHE_1WEEK, request_status)
    record_provider_response(
        provider_status, request_status, valid_librivox_response(response)
    )
    for book in librivox_books(response):
        if librivox_book_id(book) == to_text(book_id).strip():
            return book
    return None


def fetch_librivox_books(title, author='', limit=20, provider_status=None):
    if not librivox_enabled():
        return []
    url = librivox_search_url(title, author, limit)
    if not url:
        return []
    log('DEBUG', 'LibriVox fallback search: %s', title)
    request_status = {}
    response = request_json(
        url, LIBRIVOX_SEARCH_CACHE_SECONDS, request_status
    )
    if not valid_librivox_response(response):
        log(
            'WARN',
            'Malformed LibriVox search response; retrying without HTTP cache: %s',
            title,
        )
        request_status = {}
        response = request_json(url, 0, request_status)
    record_provider_response(
        provider_status, request_status, valid_librivox_response(response)
    )
    return librivox_books(response)


def ranked_librivox_matches(
    title, author, language, duration, narrators, year, threshold,
    provider_status=None
):
    candidates = fetch_librivox_books(
        title, author if author not in UNKNOWN_VALUES else '', maximum_results(),
        provider_status
    )
    fallback_title = primary_title(title)
    if not candidates:
        if fallback_title != title:
            candidates = fetch_librivox_books(
                fallback_title, '', maximum_results(), provider_status
            )
        elif author and author not in UNKNOWN_VALUES:
            candidates = fetch_librivox_books(
                title, '', maximum_results(), provider_status
            )
    ranked = []
    for index, book in enumerate(candidates):
        score = score_librivox_book(
            title, author, language, book, index,
            duration, narrators, year
        )
        if score >= threshold:
            ranked.append((score, book))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def append_librivox_results(results, ranked, lang, manual):
    for score, book in ranked:
        append_search_result(
            results, make_librivox_id(librivox_book_id(book)),
            librivox_result_label(book), lang, score,
            librivox_year(book)
        )
        if not manual:
            break


def append_local_search_result(
    results, title, author, duration, embedded, abridged, lang
):
    local_id = book_identity(
        title, author, duration, embedded.get('language'),
        abridged, embedded.get('isbns')
    )
    local_kind, local_value = split_book_identity(local_id)
    local_name = '"%s"' % title
    if author and author not in UNKNOWN_VALUES:
        local_name += ' by ' + author
    if local_kind == 'isbn':
        local_name += ' — Local metadata · ISBN ' + local_value
        local_score = 95
    else:
        local_name += ' — Local metadata'
        local_score = 85
    append_search_result(results, local_id, local_name, lang, local_score)
    log('INFO', 'Using stable %s fallback identity %s', local_kind, local_id)
    return local_id


def local_metadata_title(value):
    """Recover the book title if Plex echoes our local search-result label."""
    value = to_text(value).strip()
    marker = ' — Local metadata'
    if marker not in value:
        return value
    if value.startswith('"'):
        closing_quote = value.find('"', 1)
        if closing_quote > 1:
            return value[1:closing_quote].strip()
    return value.split(marker, 1)[0].strip('" ')


def is_local_metadata_search_label(value):
    """Return True only for a presentation label created by this agent."""
    return ' — Local metadata' in to_text(value).strip()


def defer_provider_search(
    title, author, author_source, manual, provider_states,
    candidate_count=0, catalog_hits=0, audible_queries=0, score=None
):
    provider, reason, failure_count = provider_failure_details(provider_states)
    if not reason:
        return False
    log(
        'WARN',
        'Remote provider failure prevented local fallback for "%s" by '
        '"%s" (provider=%s, reason=%s, failures=%d); Plex may retry later',
        title, author, provider, reason, failure_count,
    )
    log_album_search_summary(
        'deferred', title, author, provider=provider, score=score,
        reason=reason, author_source=author_source,
        candidate_count=candidate_count, catalog_hits=catalog_hits,
        audible_queries=audible_queries, manual=manual,
        provider_failures=failure_count,
    )
    return True


def best_googlebooks_volume(
    product, title, author, language, embedded_isbns=None, budget=None
):
    isbns = []
    for value in list(embedded_isbns or []) + product_isbns(product):
        for isbn in openlibrary_equivalent_isbns(value):
            if isbn not in isbns:
                isbns.append(isbn)
    for isbn in isbns:
        if budget is not None and budget.remaining <= 0:
            break
        for volume in fetch_googlebooks_isbn(isbn, budget):
            if isbn in googlebooks_isbns(volume):
                log('DEBUG', 'Google Books enrichment matched edition ISBN %s', isbn)
                return volume
    if budget is not None and budget.remaining <= 0:
        return None
    ranked = []
    for index, volume in enumerate(
        fetch_googlebooks_volumes(title, author, language, 10, budget)
    ):
        score = score_googlebooks_volume(title, author, language, volume, index)
        if score >= 45:
            ranked.append((score, volume))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] >= 80 else None


def append_unique_urls(target, values):
    for value in values or []:
        if value not in target:
            target.append(value)


def needs_regular_book_enrichment(metadata, keep_existing_genres, include_cover):
    return (
        not metadata.summary
        or not metadata.originally_available_at
        or (not keep_existing_genres and not metadata.genres)
        or include_cover
    )


def needs_book_enrichment(
    metadata, keep_existing_genres, include_cover, include_work_identity=False,
    include_work_publication=False, refresh_work_relationships=False
):
    return (
        needs_regular_book_enrichment(
            metadata, keep_existing_genres, include_cover
        )
        or (
            include_work_identity
            and (
                refresh_work_relationships
                or not existing_work_identities(metadata.moods)
            )
        )
        or (
            include_work_publication
            and (
                refresh_work_relationships
                or not existing_work_publication_year(metadata.moods)
            )
        )
    )


def work_relationship_refresh_required(previous_title, title, force=False):
    if force:
        return True
    previous = normalize_text(previous_title)
    current = normalize_text(title)
    return bool(previous and current and previous != current)


def apply_openlibrary_enrichment(
    metadata, product, title, author, language, embedded_isbns,
    keep_existing_genres, include_cover, image_urls, budget
):
    document = best_openlibrary_document(
        product, title, author, language, embedded_isbns, budget
    )
    if not document:
        return False
    if work_identity_enabled():
        identity = openlibrary_work_identity(document)
        if identity:
            replace_work_identity(metadata.moods, identity)
    replace_openlibrary_v3_metadata(metadata.moods, document)
    if not metadata.summary:
        work = fetch_openlibrary_work(document, budget)
        description = (
            openlibrary_work_description(work) or openlibrary_summary(document)
        )
        set_value(metadata, 'summary', description, False)
    if not metadata.originally_available_at:
        year = openlibrary_year(document)
        if year:
            try:
                metadata.originally_available_at = Datetime.ParseDate(
                    '%04d-01-01' % year
                ).date()
            except Exception as error:
                log('WARN', 'Could not parse Open Library year %s: %s', year, error)
    if not keep_existing_genres and not metadata.genres:
        fallback_genres = openlibrary_subjects(document, 8)
        if fallback_genres:
            replace_container(metadata.genres, fallback_genres)
    if include_cover:
        append_unique_urls(image_urls, openlibrary_cover_urls(document))
    return True


def apply_googlebooks_enrichment(
    metadata, product, title, author, language, embedded_isbns,
    keep_existing_genres, include_cover, image_urls, budget
):
    volume = best_googlebooks_volume(
        product, title, author, language, embedded_isbns, budget
    )
    if not volume:
        return
    if not metadata.summary:
        set_value(metadata, 'summary', googlebooks_description(volume), False)
    if not metadata.originally_available_at:
        date_value = googlebooks_date(volume)
        if date_value:
            try:
                metadata.originally_available_at = Datetime.ParseDate(
                    date_value
                ).date()
            except Exception as error:
                log(
                    'WARN', 'Could not parse Google Books date %s: %s',
                    date_value, error
                )
    if not keep_existing_genres and not metadata.genres:
        fallback_genres = googlebooks_categories(volume, 8)
        if fallback_genres:
            replace_container(metadata.genres, fallback_genres)
    if include_cover:
        append_unique_urls(image_urls, googlebooks_cover_urls(volume))


def enrich_and_apply_book_artwork(
    metadata, media, identity_product, title, authors, language,
    matched_image_urls, embedded=None, refresh_work_relationships=False
):
    image_urls = list(matched_image_urls or [])
    keep_existing_genres = as_bool(pref('keep_existing_genres', False))
    policy = artwork_policy()
    local_cover_available = bool(artwork_from_paths(media_file_paths(media)))
    needs_fallback_cover = (
        policy != 'local_only'
        and not image_urls
        and not metadata.posters
        and not (local_cover_available and policy != 'audible_only')
    )
    active_providers = [
        provider for provider in enrichment_providers()
        if (
            (provider == 'openlibrary' and openlibrary_enabled())
            or (provider == 'googlebooks' and googlebooks_enabled())
        )
    ]
    include_work_identity = work_identity_enabled() and openlibrary_enabled()
    include_work_publication = (
        extended_player_metadata_enabled() and openlibrary_enabled()
    )
    if refresh_work_relationships:
        if include_work_identity:
            replace_work_identity(metadata.moods, '')
        if include_work_publication:
            replace_openlibrary_v3_metadata(metadata.moods, {})
    if active_providers and needs_book_enrichment(
        metadata, keep_existing_genres, needs_fallback_cover,
        include_work_identity, include_work_publication,
        refresh_work_relationships
    ):
        embedded = embedded or embedded_identity_from_paths(media_file_paths(media))
        embedded_isbns = embedded.get('isbns')
        budget = RequestBudget(enrichment_request_limit())
        for provider in active_providers:
            if budget.remaining <= 0:
                break
            if not needs_book_enrichment(
                metadata, keep_existing_genres, needs_fallback_cover,
                include_work_identity, include_work_publication,
                refresh_work_relationships
            ):
                break
            if provider == 'openlibrary':
                apply_openlibrary_enrichment(
                    metadata, identity_product, title,
                    ', '.join(authors), language, embedded_isbns,
                    keep_existing_genres, needs_fallback_cover,
                    image_urls, budget
                )
            elif provider == 'googlebooks':
                if not needs_regular_book_enrichment(
                    metadata, keep_existing_genres, needs_fallback_cover
                ):
                    continue
                apply_googlebooks_enrichment(
                    metadata, identity_product, title,
                    (authors or [''])[0], language, embedded_isbns,
                    keep_existing_genres, needs_fallback_cover,
                    image_urls, budget
                )
        log(
            'DEBUG', 'Enrichment requests used: %d/%d',
            budget.used, budget.limit
        )
    apply_artwork(metadata, media, image_urls)


class VocalisMetaArtist(Agent.Artist):
    name = AGENT_NAME
    languages = [Locale.Language.English, 'de', 'es', 'fr', 'it', 'ja']
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    def search(self, results, media, lang, manual):
        wanted = media_value(media, 'title') or media_value(media, 'artist') or media_value(media, 'name')
        if not wanted or wanted in UNKNOWN_VALUES:
            return
        region = find_region(to_text(pref('region', 'us')), wanted)
        quick_asin = find_asin(wanted)
        if quick_asin:
            author = fetch_author(quick_asin, region)
            if author:
                append_search_result(
                    results, make_id(quick_asin, region), author.get('name'), lang, 100
                )
                return
            log('WARN', 'Author ASIN %s was not found in region %s', quick_asin, region)
            wanted = strip_identity_hints(wanted)
            if not wanted:
                return

        products = fetch_products(region, {
            'author': wanted,
            'num_results': maximum_results(),
            'products_sort_by': 'Relevance',
        })
        authors = unique_authors(products)
        ranked = sorted(
            [(score_author(wanted, author, index), author) for index, author in enumerate(authors)],
            key=lambda item: item[0], reverse=True
        )
        exact_provider_match = False
        for score, author in ranked:
            if score < 45:
                continue
            append_search_result(
                results,
                make_author_id(author.get('asin'), author.get('name'), region),
                author.get('name'), lang, score
            )
            if score >= 98:
                exact_provider_match = True
                if not manual:
                    break

        # Audible usually treats a compound album artist as separate people,
        # so a query such as "Isaac Asimov & Robert Silverberg" may not return
        # one exact contributor. Keep the exact Plex display name as a stable
        # VocalisMeta parent identity instead of leaving the artist local://.
        if not exact_provider_match:
            append_search_result(
                results, make_author_id(None, wanted, region), wanted, lang, 100
            )
            log(
                'DEBUG', 'Using name-backed author identity for "%s"', wanted
            )

    def update(self, metadata, media, lang, force):
        identifier, region = split_id(metadata.id, to_text(pref('region', 'us')))
        name = author_name_from_id(metadata.id) or media_value(media, 'title') or media_value(media, 'artist')
        products = []
        if identifier and not identifier.startswith('name:'):
            products = fetch_products(region, {
                'author_asins': identifier,
                'num_results': 10,
                'products_sort_by': 'Relevance',
            })
            for author in unique_authors(products):
                if author.get('asin') == identifier:
                    name = author.get('name')
                    break
        elif name:
            products = fetch_products(region, {
                'author': name,
                'num_results': 10,
                'products_sort_by': 'Relevance',
            })

        set_value(metadata, 'title', name, force, True)
        if name:
            parts = name.rsplit(' ', 1)
            metadata.title_sort = '%s, %s' % (parts[1], parts[0]) if len(parts) == 2 else name
        if as_bool(pref('author_genres', True), True):
            all_genres = []
            for product in products:
                for genre in genres(product, 8):
                    if genre not in all_genres:
                        all_genres.append(genre)
            if all_genres and (force or not metadata.genres):
                replace_container(metadata.genres, all_genres[:8])
        log('INFO', 'Updated author "%s" (%s)', name, metadata.id)


class VocalisMetaAlbum(Agent.Album):
    name = AGENT_NAME
    languages = [Locale.Language.English, 'de', 'es', 'fr', 'it', 'ja']
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    def search(self, results, media, lang, manual):
        title = search_title(media, manual).strip()
        author = media_value(media, 'artist').strip()
        author_source = 'track' if author and author not in UNKNOWN_VALUES else 'unknown'
        audible_queries = 0
        audible_catalog_hits = 0
        audible_provider_status = new_provider_status()
        librivox_provider_status = new_provider_status()
        filename = media_filename(media)
        file_paths = media_file_paths(media)
        if not title or (title in UNKNOWN_VALUES and not manual):
            log('WARN', 'Skipping album search without a usable title')
            log_album_search_summary(
                'skipped', title, author, reason='missing_title',
                author_source=author_source, manual=manual,
            )
            return

        embedded = embedded_identity_from_paths(file_paths)
        parent_guid = media_parent_guid(media)
        parent_author = author_name_from_guid(parent_guid)
        if not parent_author and (not author or author in UNKNOWN_VALUES):
            parent_identifier, parent_region = author_id_from_guid(parent_guid)
            if valid_asin(parent_identifier):
                parent_record = fetch_author(parent_identifier, parent_region)
                if parent_record:
                    parent_author = text_field(parent_record.get('name'))
        if parent_author:
            author = parent_author
            author_source = 'matched_parent'
            log(
                'DEBUG', 'Using matched parent author for album search: %s',
                author,
            )
        elif embedded.get('authors'):
            author = '; '.join(embedded.get('authors'))
            author_source = 'embedded'
            log(
                'DEBUG', 'Using embedded author for album search: %s',
                author,
            )
        else:
            directory_author = filename_author(filename, title)
            directory_name = normalize_text(directory_author)
            existing_name = normalize_text(author)
            directory_is_existing_credit = (
                directory_name and existing_name
                and directory_name in existing_name
            )
            if (
                directory_author and directory_author != author
                and not directory_is_existing_credit
            ):
                log(
                    'INFO',
                    'Using Author/Book directory author "%s" instead of '
                    'track Artist "%s" for "%s"',
                    directory_author, author, title,
                )
                author = directory_author
                author_source = 'directory'
        identity_hints = [title, author, filename] + file_paths
        explicit_asin = find_asin(*identity_hints)
        explicit_librivox = find_librivox_id(*identity_hints)
        quick_librivox = explicit_librivox
        if not quick_librivox and not explicit_asin and not embedded.get('asin'):
            quick_librivox = embedded.get('librivox_id')
        if quick_librivox:
            if librivox_enabled():
                if not explicit_librivox:
                    log(
                        'INFO', 'Embedded %s LibriVox project ID detected: %s',
                        embedded.get('format'), quick_librivox
                    )
                book = fetch_librivox_book(
                    quick_librivox, librivox_provider_status
                )
                if book:
                    librivox_identity = make_librivox_id(quick_librivox)
                    append_search_result(
                        results, librivox_identity,
                        librivox_result_label(book), lang, 100,
                        librivox_year(book)
                    )
                    log_album_search_summary(
                        'results', title, author, provider='librivox',
                        identity=librivox_identity, score=100,
                        reason='exact_librivox_id',
                        author_source=author_source, candidate_count=1,
                        manual=manual,
                    )
                    return
                else:
                    provider, failure_reason, failure_count = (
                        provider_failure_details([
                            ('librivox', librivox_provider_status),
                        ])
                    )
                    if failure_reason:
                        log(
                            'WARN',
                            'LibriVox project lookup failed for %s '
                            '(reason=%s, failures=%d)',
                            quick_librivox, failure_reason, failure_count,
                        )
                    else:
                        log(
                            'WARN', 'LibriVox project %s was not found',
                            quick_librivox,
                        )
                    if manual:
                        if defer_provider_search(
                            title, author, author_source, manual,
                            [('librivox', librivox_provider_status)]
                        ):
                            return
                        log_album_search_summary(
                            'no_match', title, author, provider='librivox',
                            identity=make_librivox_id(quick_librivox),
                            reason='librivox_id_not_found',
                            author_source=author_source, manual=manual,
                        )
                        return
                    title = strip_librivox_id_hint(title)
                    author = strip_librivox_id_hint(author)
                    if not title or title in UNKNOWN_VALUES:
                        log_album_search_summary(
                            'no_match', title, author, provider='librivox',
                            reason='librivox_id_not_found_no_title',
                            author_source=author_source, manual=manual,
                        )
                        return
            elif explicit_librivox:
                log_album_search_summary(
                    'no_match', title, author, provider='librivox',
                    identity=make_librivox_id(quick_librivox),
                    reason='librivox_disabled',
                    author_source=author_source, manual=manual,
                )
                return

        default_region = to_text(pref('region', 'us'))
        explicit_region = find_region_override(*identity_hints)
        region = explicit_region or embedded.get('region') or find_region(default_region)
        regions = audible_regions(region)
        quick_asin = explicit_asin or embedded.get('asin')
        if embedded.get('asin'):
            log('INFO', 'Embedded %s ASIN detected: %s', embedded.get('format'), embedded.get('asin'))
        if embedded.get('region') and not explicit_region:
            log('INFO', 'Using embedded Audible region: %s', embedded.get('region'))
        if quick_asin:
            for candidate_region in regions:
                audible_queries += 1
                product = fetch_product(
                    quick_asin, candidate_region, audible_provider_status
                )
                if product:
                    audible_identity = make_id(quick_asin, candidate_region)
                    append_search_result(
                        results, audible_identity,
                        search_result_label(product, candidate_region), lang, 100,
                        self.product_year(product)
                    )
                    log_album_search_summary(
                        'results', title, author, provider='audible',
                        identity=audible_identity, score=100,
                        reason='exact_asin', author_source=author_source,
                        candidate_count=1, catalog_hits=1,
                        audible_queries=audible_queries,
                        manual=manual,
                    )
                    return
            log(
                'WARN',
                'ASIN %s was not found in regions %s; attempting title fallback',
                quick_asin, ','.join(regions)
            )
            title = strip_identity_hints(title)
            author = strip_identity_hints(author)
            # An ASIN-only Fix Match must not turn into an unbounded search.
            if not title or title in UNKNOWN_VALUES:
                if defer_provider_search(
                    title, author, author_source, manual,
                    [('audible', audible_provider_status)],
                    audible_queries=audible_queries,
                ):
                    return
                log_album_search_summary(
                    'no_match', title, author, provider='audible',
                    identity=make_id(quick_asin, region),
                    reason='asin_not_found_no_title',
                    author_source=author_source,
                    audible_queries=audible_queries, manual=manual,
                )
                return

        title_variants = search_title_variants(title, filename)
        if not title_variants:
            title_variants = [title]
        constrained_author = author if author not in UNKNOWN_VALUES else ''
        audible_candidates = []
        seen = set()
        today = datetime.date.today().isoformat()
        wanted_duration = media_duration_minutes(media)
        if wanted_duration:
            log(
                'DEBUG', 'Using %.1f minutes of Plex runtime evidence for "%s"',
                wanted_duration, title,
            )
        wanted_language = embedded.get('language') or lang
        wanted_year = media_value(media, 'year')
        wanted_abridged = embedded.get('abridged')
        if wanted_abridged is None:
            wanted_abridged = abridged_hint(title, filename)
        audible_threshold = 45 if manual else 80
        ranked = []
        librivox_path_hint = (
            librivox_enabled()
            and not explicit_asin and not embedded.get('asin')
            and has_librivox_source_hint(filename, *file_paths)
        )

        if librivox_path_hint:
            log(
                'INFO',
                'LibriVox source hint detected in media path; searching '
                'LibriVox before Audible for "%s"',
                title,
            )
            librivox_ranked = ranked_librivox_matches(
                title, author, wanted_language, wanted_duration,
                embedded.get('narrators'), wanted_year, audible_threshold,
                librivox_provider_status
            )
            append_librivox_results(results, librivox_ranked, lang, manual)
            if librivox_ranked:
                best_librivox = librivox_ranked[0]
                log_album_search_summary(
                    'results', title, author, provider='librivox',
                    identity=make_librivox_id(
                        librivox_book_id(best_librivox[1])
                    ),
                    score=best_librivox[0], reason='librivox_path_hint',
                    author_source=author_source,
                    candidate_count=len(librivox_ranked), manual=manual,
                )
                return
            log(
                'WARN',
                'LibriVox source hint was present but no acceptable LibriVox '
                'match was found for "%s" by "%s"; refusing Audible '
                'cross-match',
                title, author,
            )
            if defer_provider_search(
                title, author, author_source, manual,
                [('librivox', librivox_provider_status)]
            ):
                return
            local_id = append_local_search_result(
                results, title, author, wanted_duration, embedded,
                wanted_abridged, lang
            )
            log_album_search_summary(
                'local_fallback', title, author, provider='local',
                identity=local_id, reason='librivox_hint_no_match',
                author_source=author_source, manual=manual,
            )
            return

        if librivox_mode() == 'preferred':
            log(
                'DEBUG', 'Preferred LibriVox search before Audible for "%s"',
                title,
            )
            librivox_ranked = ranked_librivox_matches(
                title, author, wanted_language, wanted_duration,
                embedded.get('narrators'), wanted_year, audible_threshold,
                librivox_provider_status
            )
            append_librivox_results(results, librivox_ranked, lang, manual)
            if librivox_ranked:
                best_librivox = librivox_ranked[0]
                log_album_search_summary(
                    'results', title, author, provider='librivox',
                    identity=make_librivox_id(
                        librivox_book_id(best_librivox[1])
                    ),
                    score=best_librivox[0], reason='librivox_preferred',
                    author_source=author_source,
                    candidate_count=len(librivox_ranked), manual=manual,
                )
                return

        # Most books need only the first exact title/author request. If that
        # does not produce an acceptable candidate, try both sides of common
        # separators and a clean filename title. Finally remove the author
        # constraint, which Audible can over-constrain for joint contributors.
        search_groups = [([title_variants[0]], constrained_author)]
        if len(title_variants) > 1:
            search_groups.append((title_variants[1:], constrained_author))
        if constrained_author:
            search_groups.append((title_variants, ''))

        for group_titles, group_author in search_groups:
            if has_acceptable_audible_candidate(ranked, audible_threshold):
                break
            for query_title in group_titles:
                for region_index, candidate_region in enumerate(regions):
                    params = {
                        'title': query_title,
                        'author': group_author or None,
                        'num_results': maximum_results(),
                        'products_sort_by': 'Relevance',
                    }
                    audible_queries += 1
                    products = fetch_products(
                        candidate_region, params, audible_provider_status
                    )
                    audible_catalog_hits += len(products)
                    for product in products:
                        if (
                            not group_author and constrained_author
                            and author_ratio(author, product) < 0.55
                        ):
                            log(
                                'DEBUG',
                                'Rejected title-only Audible candidate "%s" '
                                'because its author does not match "%s"',
                                display_title(product), author,
                            )
                            continue
                        asin = to_text(product.get('asin')).upper()
                        if valid_asin(asin) and asin not in seen:
                            seen.add(asin)
                            audible_candidates.append(
                                (candidate_region, region_index, product)
                            )
            ranked = ranked_audible_candidates(
                audible_candidates, title_variants, author, wanted_language,
                wanted_duration, embedded.get('narrators'), wanted_year,
                wanted_abridged, today,
            )

        for score, candidate_region, product in ranked:
            if not manual and score < audible_threshold:
                continue
            append_search_result(
                results, make_id(product.get('asin'), candidate_region),
                search_result_label(product, candidate_region),
                lang, score, self.product_year(product)
            )
            if not manual and score >= 98:
                break

        audible_acceptable = has_acceptable_audible_candidate(
            ranked, audible_threshold
        )
        if audible_acceptable:
            best_audible = ranked[0]
            log_album_search_summary(
                'results', title, author, provider='audible',
                identity=make_id(
                    best_audible[2].get('asin'), best_audible[1]
                ),
                score=best_audible[0], reason='ranked_audible',
                author_source=author_source,
                candidate_count=len(audible_candidates),
                catalog_hits=audible_catalog_hits,
                audible_queries=audible_queries, manual=manual,
            )
            return

        librivox_ranked = []
        if librivox_mode() == 'fallback':
            librivox_ranked = ranked_librivox_matches(
                title, author, wanted_language, wanted_duration,
                embedded.get('narrators'), wanted_year, audible_threshold,
                librivox_provider_status
            )
            append_librivox_results(results, librivox_ranked, lang, manual)
            if librivox_ranked:
                best_librivox = librivox_ranked[0]
                log_album_search_summary(
                    'results', title, author, provider='librivox',
                    identity=make_librivox_id(
                        librivox_book_id(best_librivox[1])
                    ),
                    score=best_librivox[0], reason='librivox_fallback',
                    author_source=author_source,
                    candidate_count=len(librivox_ranked),
                    catalog_hits=audible_catalog_hits,
                    audible_queries=audible_queries, manual=manual,
                )
                return

        if defer_provider_search(
            title, author, author_source, manual,
            [
                ('audible', audible_provider_status),
                ('librivox', librivox_provider_status),
            ],
            candidate_count=len(audible_candidates),
            catalog_hits=audible_catalog_hits,
            audible_queries=audible_queries,
            score=ranked[0][0] if ranked else None,
        ):
            return

        log_unmatched_audible(
            title, author, ranked, audible_threshold,
            audible_catalog_hits,
        )
        local_id = append_local_search_result(
            results, title, author, wanted_duration, embedded,
            wanted_abridged, lang
        )
        log_album_search_summary(
            'local_fallback', title, author, provider='local',
            identity=local_id,
            score=ranked[0][0] if ranked else None,
            reason=(
                'audible_below_threshold' if ranked else
                'audible_candidates_rejected' if audible_catalog_hits else
                'audible_no_candidates'
            ),
            author_source=author_source,
            candidate_count=len(audible_candidates),
            catalog_hits=audible_catalog_hits,
            audible_queries=audible_queries, manual=manual,
        )

    def update(self, metadata, media, lang, force):
        # Preference changes must take effect even when a later provider lookup
        # fails. Remove only optional contract namespaces owned by VocalisMeta;
        # author Moods and custom user values remain untouched.
        prune_disabled_contract_moods(metadata.moods)
        librivox_id = split_librivox_id(metadata.id)
        if librivox_id:
            self.update_librivox(metadata, media, lang, force, librivox_id)
            return
        local_kind, local_value = split_book_identity(metadata.id)
        if local_kind:
            self.update_local(
                metadata, media, lang, force, local_kind, local_value
            )
            return
        if to_text(metadata.id).strip().lower().startswith('ol:'):
            log(
                'WARN',
                'Open Library match IDs are no longer supported; use Fix Match to select an Audible edition'
            )
            log_album_update_summary(
                metadata, 'preserved', 'legacy_openlibrary',
                'unsupported_legacy_identity', forced=force
            )
            return
        asin, region = split_id(metadata.id, to_text(pref('region', 'us')))
        asin = to_text(asin).strip().upper()
        if not valid_asin(asin):
            log('ERROR', 'Refusing metadata update with malformed ASIN: %s', asin)
            log_album_update_summary(
                metadata, 'rejected', 'audible', 'malformed_identity',
                forced=force
            )
            return
        product = fetch_product(asin, region)
        if not product:
            log(
                'ERROR',
                'No exact Audible product found for ASIN %s in region %s; existing metadata was preserved',
                asin, region
            )
            log_album_update_summary(
                metadata, 'preserved', 'audible', 'product_not_found',
                forced=force
            )
            return

        include_subtitle = as_bool(pref('include_subtitle', True), True)
        previous_title = to_text(metadata.title).strip()
        title = display_title(product, include_subtitle)
        if as_bool(pref('simplify_title', False)):
            title = primary_title(product.get('title'))
        embedded = embedded_identity_from_paths(media_file_paths(media))
        remote_series = series_entries(product)
        local_series = (
            embedded_series_entries(embedded)
            if embedded_series_enabled() and not remote_series else []
        )
        active_series = remote_series or local_series
        provider_authors = people(product, 'authors')
        provider_narrators = people(product, 'narrators')
        local_authors = (
            embedded.get('authors') if embedded_contributors_enabled() else []
        )
        local_narrators = (
            embedded.get('narrators') if embedded_contributors_enabled() else []
        )
        active_authors = provider_authors or local_authors
        active_narrators = provider_narrators or local_narrators
        active_language = (
            text_field(product.get('language')) or embedded.get('language')
        )
        active_abridged = product_abridged(product)
        if active_abridged is None:
            active_abridged = embedded.get('abridged')
        active_authors, active_series, active_language, active_abridged = (
            preserve_relationship_fallbacks(
                metadata, active_authors, active_series, active_language,
                active_abridged, 'Audible'
            )
        )
        set_value(metadata, 'title', title, force, True)
        set_value(
            metadata, 'title_sort',
            sort_title_with_series_fallback(
                product, display_title(product, False), active_series
            ), force, True
        )
        set_value(
            metadata, 'studio', text_field(product.get('publisher_name')),
            force, True
        )
        set_value(metadata, 'summary', summary(product), force, True)

        date_value = release_date(product)
        if date_value:
            try:
                metadata.originally_available_at = Datetime.ParseDate(date_value).date()
            except Exception as error:
                log('WARN', 'Could not parse release date %s: %s', date_value, error)

        rating = rating_out_of_ten(product)
        if rating is not None:
            metadata.rating = rating

        book_genres = genres(product, 8)
        if book_genres and not as_bool(pref('keep_existing_genres', False)):
            replace_container(metadata.genres, book_genres)

        if active_narrators:
            replace_container(metadata.styles, active_narrators)

        previous_work_identities = existing_work_identities(metadata.moods)
        player_tags = merge_v3_tags(
            existing_v3_enrichment_tags(metadata.moods),
            audible_v3_tags(product),
        )
        moods = relationship_moods(
            active_authors, active_series,
            active_language,
            active_abridged, previous_work_identities, player_tags
        )
        replace_container(metadata.moods, moods)

        enrich_and_apply_book_artwork(
            metadata, media, product, display_title(product, False),
            active_authors, lang,
            image_candidates(product, pref('image_size', 2000)), embedded,
            work_relationship_refresh_required(
                previous_title, title, force
            )
        )

        log('INFO', 'Updated audiobook "%s" (%s)', title, metadata.id)
        log_album_update_summary(
            metadata, 'updated', 'audible', 'ok', title, force
        )

    def update_librivox(self, metadata, media, lang, force, book_id):
        book = fetch_librivox_book(book_id)
        if not book:
            log(
                'ERROR',
                'No exact LibriVox project found for ID %s; existing metadata was preserved',
                book_id
            )
            log_album_update_summary(
                metadata, 'preserved', 'librivox', 'project_not_found',
                forced=force
            )
            return
        previous_title = to_text(metadata.title).strip()
        title = text_field(book.get('title'))
        embedded = embedded_identity_from_paths(media_file_paths(media))
        local_series = (
            embedded_series_entries(embedded)
            if embedded_series_enabled() else []
        )
        book_authors = librivox_authors(book)
        book_readers = librivox_readers(book)
        if embedded_contributors_enabled():
            book_authors = book_authors or embedded.get('authors') or []
            book_readers = book_readers or embedded.get('narrators') or []
        active_language = librivox_language(book) or embedded.get('language')
        active_abridged = embedded.get('abridged')
        book_authors, local_series, active_language, active_abridged = (
            preserve_relationship_fallbacks(
                metadata, book_authors, local_series, active_language,
                active_abridged, 'LibriVox'
            )
        )
        set_value(metadata, 'title', title, force, True)
        set_value(
            metadata, 'title_sort',
            sort_title_with_series_fallback(book, title, local_series),
            force, True
        )
        set_value(metadata, 'studio', 'LibriVox', force, True)
        set_value(
            metadata, 'summary', librivox_description(book), force, True
        )

        year = librivox_year(book)
        if year:
            try:
                metadata.originally_available_at = Datetime.ParseDate(
                    '%04d-01-01' % year
                ).date()
            except Exception as error:
                log('WARN', 'Could not parse LibriVox year %s: %s', year, error)

        if force:
            metadata.rating = None
        book_genres = librivox_genres(book, 8)
        if book_genres and not as_bool(pref('keep_existing_genres', False)):
            replace_container(metadata.genres, book_genres)
        if book_readers:
            replace_container(metadata.styles, book_readers)
        previous_work_identities = existing_work_identities(metadata.moods)
        player_tags = merge_v3_tags(
            existing_v3_enrichment_tags(metadata.moods),
            librivox_v3_tags(book),
        )
        moods = relationship_moods(
            book_authors, local_series,
            active_language, active_abridged,
            previous_work_identities, player_tags
        )
        replace_container(metadata.moods, moods)

        enrich_and_apply_book_artwork(
            metadata, media, book, title, book_authors,
            librivox_language(book) or lang, librivox_cover_urls(book), embedded,
            work_relationship_refresh_required(
                previous_title, title, force
            )
        )
        log('INFO', 'Updated LibriVox audiobook "%s" (%s)', title, metadata.id)
        log_album_update_summary(
            metadata, 'updated', 'librivox', 'ok', title, force
        )

    def update_local(
        self, metadata, media, lang, force, identity_kind, identity_value
    ):
        """Preserve local metadata and enrich only fields that are missing."""
        previous_title = to_text(metadata.title).strip()
        embedded = embedded_identity_from_paths(media_file_paths(media))
        title = (
            media_value(media, 'album') or media_value(media, 'title')
            or media_value(media, 'name') or metadata.title
        ).strip()
        title = local_metadata_title(title)
        author = author_name_from_guid(media_parent_guid(media))
        if not author and embedded.get('authors'):
            author = '; '.join(embedded.get('authors'))
        if not author:
            author = media_value(media, 'artist').strip()
        filename = media_filename(media)
        directory_author = filename_author(filename, title)
        if directory_author:
            directory_name = normalize_text(directory_author)
            author_name = normalize_text(author)
            if not author_name or directory_name not in author_name:
                author = directory_author

        if identity_kind == 'isbn' and identity_value:
            isbns = list(embedded.get('isbns') or [])
            if identity_value not in isbns:
                isbns.insert(0, identity_value)
            embedded['isbns'] = isbns

        local_series = (
            embedded_series_entries(embedded)
            if embedded_series_enabled() else []
        )
        active_authors = embedded.get('authors') or ([author] if author else [])
        active_language = embedded.get('language')
        active_abridged = embedded.get('abridged')
        active_authors, local_series, active_language, active_abridged = (
            preserve_relationship_fallbacks(
                metadata, active_authors, local_series, active_language,
                active_abridged, 'embedded metadata'
            )
        )
        # Plex can persist the selected MetadataSearchResult.name as the album
        # title before calling update().  Local results intentionally include
        # author and source context for the Fix Match screen, but that label is
        # not album metadata.  Replace only labels owned by VocalisMeta; retain
        # every other existing title so user-entered values remain untouched.
        replace_local_title = is_local_metadata_search_label(previous_title)
        set_value(metadata, 'title', title, False, replace_local_title)
        previous_title_sort = to_text(metadata.title_sort).strip()
        set_value(
            metadata, 'title_sort',
            sort_title_with_series_fallback({}, title, local_series), False,
            is_local_metadata_search_label(previous_title_sort)
        )
        local_narrators = (
            embedded.get('narrators') if embedded_contributors_enabled() else []
        )
        if local_narrators and not metadata.styles:
            replace_container(metadata.styles, local_narrators)
        previous_work_identities = existing_work_identities(metadata.moods)
        player_tags = existing_v3_enrichment_tags(metadata.moods)
        moods = relationship_moods(
            active_authors, local_series, active_language, active_abridged,
            previous_work_identities, player_tags
        )
        if moods:
            replace_container(metadata.moods, moods)

        enrich_and_apply_book_artwork(
            metadata, media, {}, title, [author] if author else [],
            embedded.get('language') or '', [], embedded,
            work_relationship_refresh_required(
                previous_title, title, force
            )
        )
        log(
            'INFO', 'Updated local audiobook "%s" (%s:%s)',
            title, identity_kind, identity_value
        )
        log_album_update_summary(
            metadata, 'updated', 'local', 'ok', title, force
        )

    @staticmethod
    def product_year(product):
        value = release_date(product or {})
        try:
            return int(value[:4])
        except (TypeError, ValueError):
            return None
