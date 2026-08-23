#!/usr/bin/env python3
"""Find a Plex audiobook by title and inspect its current album metadata."""

import argparse
import difflib
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


DEFAULT_PLEX_URL = 'http://127.0.0.1:32400'
AGENT_ID = 'com.plexapp.agents.spokenmeta'
DEFAULT_PREFERENCES = (
    '/var/lib/plexmediaserver/Library/Application Support/'
    'Plex Media Server/Preferences.xml'
)
PAGE_SIZE = 250


class ToolError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Resolve the current Plex album rating key for an audiobook and '
            'show the detailed metadata exposed to audiobook clients.'
        ),
    )
    parser.add_argument(
        'title',
        nargs='?',
        help='book title to find (not required with --rating-key)',
    )
    parser.add_argument(
        '--author',
        help='expected author; strongly recommended for short/common titles',
    )
    parser.add_argument(
        '--library',
        help='limit matching to this Plex library name',
    )
    parser.add_argument(
        '--rating-key',
        help='inspect a known rating key without searching first',
    )
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='request a forced Plex metadata refresh before inspection',
    )
    parser.add_argument(
        '--wait',
        type=float,
        default=5.0,
        metavar='SECONDS',
        help='time to wait after --refresh (default: %(default)s)',
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        '--json',
        action='store_true',
        help='print machine-readable JSON',
    )
    output.add_argument(
        '--xml',
        action='store_true',
        help='print the raw per-item Plex XML',
    )
    parser.add_argument(
        '--plex-url',
        default=os.environ.get('PLEX_URL', DEFAULT_PLEX_URL),
        help='Plex server URL (default: %(default)s)',
    )
    parser.add_argument(
        '--preferences',
        help='path to Plex Preferences.xml for local token discovery',
    )
    parser.add_argument(
        '--token-file',
        help='path to a file containing only a Plex authentication token',
    )
    args = parser.parse_args(argv)
    if not args.rating_key and not args.title:
        parser.error('provide a title or --rating-key')
    if args.wait < 0:
        parser.error('--wait cannot be negative')
    return args


def preferences_candidates(explicit_path=None):
    paths = []
    if explicit_path:
        paths.append(explicit_path)
    data_dir = os.environ.get('PLEX_MEDIA_SERVER_DATA_DIR')
    if data_dir:
        paths.append(os.path.join(data_dir, 'Preferences.xml'))
    paths.append(DEFAULT_PREFERENCES)
    result = []
    for path in paths:
        if path not in result:
            result.append(path)
    return result


def read_token_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            token = handle.read().strip()
    except OSError as error:
        raise ToolError('Cannot read Plex token file %s: %s' % (path, error))
    if not token:
        raise ToolError('Plex token file is empty: %s' % path)
    return token


def token_from_preferences(path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    return (root.attrib.get('PlexOnlineToken') or '').strip() or None


def discover_token(args):
    token = (os.environ.get('PLEX_TOKEN') or '').strip()
    if token:
        return token
    if args.token_file:
        return read_token_file(args.token_file)
    for path in preferences_candidates(args.preferences):
        token = token_from_preferences(path)
        if token:
            return token
    raise ToolError(
        'No Plex token found. Set PLEX_TOKEN, use --token-file, or run as '
        'a user that can read Plex Preferences.xml.'
    )


def normalize(value):
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(character for character in value
                    if not unicodedata.combining(character))
    return ' '.join(''.join(
        character.casefold() if character.isalnum() else ' '
        for character in value
    ).split())


def album_author(album):
    return (
        album.attrib.get('parentTitle')
        or album.attrib.get('grandparentTitle')
        or album.attrib.get('originalTitle')
        or ''
    )


def album_library(album):
    return album.attrib.get('librarySectionTitle') or ''


def candidate_score(album, title, author=None, library=None):
    wanted_title = normalize(title)
    actual_title = normalize(album.attrib.get('title'))
    if not wanted_title or not actual_title:
        return None
    ratio = difflib.SequenceMatcher(None, wanted_title, actual_title).ratio()
    if actual_title == wanted_title:
        score = 1000
    elif actual_title.startswith(wanted_title) or wanted_title.startswith(actual_title):
        score = 700
    elif wanted_title in actual_title or actual_title in wanted_title:
        score = 550
    elif ratio >= 0.55:
        score = int(ratio * 400)
    else:
        return None

    if author:
        wanted_author = normalize(author)
        actual_author = normalize(album_author(album))
        author_ratio = difflib.SequenceMatcher(
            None, wanted_author, actual_author,
        ).ratio()
        if actual_author == wanted_author:
            score += 500
        elif wanted_author in actual_author or actual_author in wanted_author:
            score += 300
        elif author_ratio >= 0.60:
            score += int(author_ratio * 200)
        else:
            return None

    if library:
        if normalize(album_library(album)) != normalize(library):
            return None
        score += 100
    return score


def deduplicate_albums(albums):
    result = []
    seen = set()
    for album in albums:
        rating_key = album.attrib.get('ratingKey')
        if not rating_key or rating_key in seen:
            continue
        seen.add(rating_key)
        result.append(album)
    return result


def choose_album(albums, title, author=None, library=None):
    ranked = []
    for album in deduplicate_albums(albums):
        score = candidate_score(album, title, author, library)
        if score is not None:
            ranked.append((score, album))
    ranked.sort(key=lambda item: (
        -item[0],
        normalize(item[1].attrib.get('title')),
        item[1].attrib.get('ratingKey') or '',
    ))
    if not ranked:
        raise ToolError(
            'No Plex audiobook album matched %r%s%s.' % (
                title,
                ' by %r' % author if author else '',
                ' in %r' % library if library else '',
            )
        )
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        lines = ['Multiple equally good Plex albums matched:']
        for score, album in ranked[:10]:
            lines.append(
                '  ratingKey=%s | %s | %s | %s | score=%s' % (
                    album.attrib.get('ratingKey') or '?',
                    album.attrib.get('title') or '?',
                    album_author(album) or '?',
                    album_library(album) or '?',
                    score,
                )
            )
        lines.append('Add --author, --library, or use --rating-key.')
        raise ToolError('\n'.join(lines))
    return ranked[0][1]


class PlexApi(object):
    def __init__(self, base_url, token):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ToolError('Invalid Plex URL: %s' % base_url)
        self.base_url = base_url.rstrip('/')
        self.token = token

    def request(self, path, method='GET', allow_empty=False):
        request = urllib.request.Request(
            self.base_url + path,
            headers={
                'Accept': 'application/xml',
                'X-Plex-Client-Identifier': 'vocalismeta-book-inspector',
                'X-Plex-Product': 'VocalisMeta book inspector',
                'X-Plex-Token': self.token,
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404 and path.startswith('/library/metadata/'):
                raise ToolError(
                    'Plex rating key no longer exists on this server: %s' % (
                        path.split('/')[3].split('?')[0],
                    )
                )
            raise ToolError(
                'Plex returned HTTP %s for %s' % (error.code, path.split('?')[0])
            )
        except urllib.error.URLError as error:
            raise ToolError('Cannot reach Plex: %s' % error.reason)
        if not payload:
            if allow_empty:
                return None, b''
            raise ToolError('Plex returned an empty response for %s' % path)
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise ToolError('Plex returned invalid XML: %s' % error)
        return root, payload

    def identity(self):
        root, _payload = self.request('/identity')
        return root

    def sections(self):
        root, _payload = self.request('/library/sections')
        return list(root.findall('Directory'))

    def search(self, query):
        path = '/search?' + urllib.parse.urlencode({
            'query': query,
            'limit': '100',
        })
        try:
            root, _payload = self.request(path)
        except ToolError as error:
            if 'HTTP 404' not in str(error):
                raise
            return []
        return [item for item in root.iter()
                if item.attrib.get('type') == 'album']

    def albums(self, section_key):
        start = 0
        albums = []
        while True:
            path = '/library/sections/%s/all?%s' % (
                urllib.parse.quote(str(section_key), safe=''),
                urllib.parse.urlencode({
                    'type': '9',
                    'X-Plex-Container-Start': str(start),
                    'X-Plex-Container-Size': str(PAGE_SIZE),
                }),
            )
            root, _payload = self.request(path)
            page = [item for item in root.iter()
                    if item.attrib.get('type') == 'album']
            albums.extend(page)
            total = int(root.attrib.get('totalSize') or len(albums))
            page_size = int(root.attrib.get('size') or len(page))
            start += page_size
            if not page or start >= total:
                break
        return albums

    def find_albums(self, title, library=None):
        albums = self.search(title)
        section_candidates = []
        for section in self.sections():
            if section.attrib.get('type') != 'artist':
                continue
            if section.attrib.get('agent') != AGENT_ID:
                continue
            if library and normalize(section.attrib.get('title')) != normalize(library):
                continue
            section_candidates.append(section)
        if not section_candidates:
            if library:
                raise ToolError(
                    'No VocalisMeta Music library named %r was found.' % library
                )
            raise ToolError(
                'No Plex Music libraries using the VocalisMeta Agent were found.'
            )

        allowed_sections = set(
            str(section.attrib.get('key')) for section in section_candidates
        )
        albums = [
            album for album in albums
            if not album.attrib.get('librarySectionID')
            or str(album.attrib.get('librarySectionID')) in allowed_sections
        ]

        if library:
            # A global search result is not guaranteed to identify its source
            # section. Use the named section as the authoritative candidate set.
            albums = []

        # Search responses vary between Plex versions and may omit section names.
        # Enumerating selected Music sections is the reliable fallback and also
        # supplies librarySectionTitle for deterministic disambiguation.
        if not albums or library:
            for section in section_candidates:
                for album in self.albums(section.attrib.get('key')):
                    album.attrib.setdefault(
                        'librarySectionTitle', section.attrib.get('title') or '',
                    )
                    albums.append(album)
        return deduplicate_albums(albums)

    def metadata(self, rating_key):
        path = '/library/metadata/%s?%s' % (
            urllib.parse.quote(str(rating_key), safe=''),
            urllib.parse.urlencode({'includeGuids': '1'}),
        )
        root, payload = self.request(path)
        item = next((entry for entry in root.iter()
                     if entry.attrib.get('type') == 'album'), None)
        if item is None:
            raise ToolError(
                'Rating key %s is not a Plex album.' % rating_key
            )
        return root, item, payload

    def refresh(self, rating_key):
        path = '/library/metadata/%s/refresh?%s' % (
            urllib.parse.quote(str(rating_key), safe=''),
            urllib.parse.urlencode({'force': '1'}),
        )
        self.request(path, method='PUT', allow_empty=True)


def child_tags(item, name):
    return [child.attrib.get('tag') for child in item.findall(name)
            if child.attrib.get('tag')]


def metadata_record(identity, item):
    guid = item.attrib.get('guid') or ''
    guids = [child.attrib.get('id') for child in item.findall('Guid')
             if child.attrib.get('id')]
    return {
        'server': {
            'machine_identifier': identity.attrib.get('machineIdentifier') or '',
            'version': identity.attrib.get('version') or '',
        },
        'book': {
            'rating_key': item.attrib.get('ratingKey') or '',
            'title': item.attrib.get('title') or '',
            'author': album_author(item),
            'library': album_library(item),
            'guid': guid,
            'guids': guids,
            'year': item.attrib.get('year') or '',
            'narrators': child_tags(item, 'Style'),
            'genres': child_tags(item, 'Genre'),
            'moods': child_tags(item, 'Mood'),
        },
    }


def print_text(record, output=None):
    output = output or sys.stdout
    server = record['server']
    book = record['book']
    print('Server: %s%s' % (
        server['machine_identifier'] or 'unknown',
        ' (Plex %s)' % server['version'] if server['version'] else '',
    ), file=output)
    print('Library: %s' % (book['library'] or 'unknown'), file=output)
    print('Rating key: %s' % book['rating_key'], file=output)
    print('Title: %s' % book['title'], file=output)
    print('Author: %s' % (book['author'] or '-'), file=output)
    print('GUID: %s' % (book['guid'] or '-'), file=output)
    if book['guids']:
        print('Additional GUIDs: %s' % ', '.join(book['guids']), file=output)
    print('Year: %s' % (book['year'] or '-'), file=output)
    print('Narrators (Style): %s' % (
        ', '.join(book['narrators']) if book['narrators'] else '-',
    ), file=output)
    print('Genres: %s' % (
        ', '.join(book['genres']) if book['genres'] else '-',
    ), file=output)
    print('Mood tags:', file=output)
    if book['moods']:
        for mood in book['moods']:
            print('  - %s' % mood, file=output)
    else:
        print('  -', file=output)


def main(argv=None):
    args = parse_args(argv)
    try:
        token = discover_token(args)
        api = PlexApi(args.plex_url, token)
        identity = api.identity()
        if args.rating_key:
            rating_key = args.rating_key
        else:
            albums = api.find_albums(args.title, args.library)
            selected = choose_album(
                albums, args.title, args.author, args.library,
            )
            rating_key = selected.attrib.get('ratingKey')
        if args.refresh:
            api.refresh(rating_key)
            if not args.json and not args.xml:
                print('Forced metadata refresh requested for rating key %s.' % (
                    rating_key,
                ))
            if args.wait:
                time.sleep(args.wait)
        _root, item, payload = api.metadata(rating_key)
        if args.xml:
            sys.stdout.buffer.write(payload)
            if not payload.endswith(b'\n'):
                sys.stdout.buffer.write(b'\n')
            return 0
        record = metadata_record(identity, item)
        if args.json:
            print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print_text(record)
    except ToolError as error:
        print('Error: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
