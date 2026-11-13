#!/usr/bin/env python3
"""Offline doctor, metadata reports, change previews, and portable export."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'VocalisMeta.bundle/Contents/Code'))
from config_core import ConfigError, load_config_file
from sidecar_core import load_sidecar
from embedded_tags import read_embedded_metadata
from multipart_core import conflicts
from artwork_core import inspect_image, DECODER, MAX_BYTES
from metadata_tools_core import changes, export_sidecar


def read_text(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('input exceeds 32 MiB')
    with path.open('rb') as stream:
        data = stream.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('input exceeds 32 MiB')
    return data.decode('utf-8-sig')


def read_record(path):
    text = read_text(path)
    if not text.lstrip().startswith('<'):
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError('input must be one snapshot or report object')
        if 'after' in value and not isinstance(value['after'], dict):
            raise ValueError('report.after must be a snapshot object')
        return value
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML entity declarations are not supported')
    root = ET.fromstring(text)
    albums = [root] if root.tag == 'Directory' else root.findall('Directory')
    albums = [item for item in albums if item.get('type') == 'album']
    if len(albums) != 1:
        raise ValueError('XML must describe exactly one album')
    item = albums[0]
    guid = item.get('guid', '')
    for candidate in item.findall('Guid'):
        value = candidate.get('id', '')
        if value.startswith('com.plexapp.agents.spokenmeta://'):
            guid = value
            break
    result = {'id': guid, 'title': item.get('title'), 'summary': item.get('summary'),
              'studio': item.get('studio'), 'originally_available_at': item.get('originallyAvailableAt'),
              'primary_author': item.get('parentTitle')}
    for tag, field in (('Genre', 'genres'), ('Style', 'styles'), ('Mood', 'moods')):
        result[field] = [child.get('tag') for child in item.findall(tag) if child.get('tag')]
    if item.get('parentTitle') and not result['moods']:
        result['moods'].append(item.get('parentTitle'))
    return result


def write_result(value, destination, overwrite=False):
    text = json.dumps(value, indent=2, ensure_ascii=False) + '\n'
    if destination is None or str(destination) == '-':
        print(text, end='')
    else:
        # Exclusive creation by default; never silently replace a book override.
        with destination.open('w' if overwrite else 'x', encoding='utf-8') as stream:
            stream.write(text)


def audio_paths(path):
    if path.is_file():
        return [str(path)]
    if not path.is_dir():
        raise ValueError('book path does not exist')
    result = []
    for item in sorted(path.rglob('*')):
        if item.is_file() and item.suffix.lower() in ('.mp3', '.m4b', '.m4a', '.mp4', '.flac', '.ogg', '.oga', '.opus', '.wv'):
            result.append(str(item))
            if len(result) > 256:
                raise ValueError('book contains more than 256 audio files; narrow the path')
    if not result:
        # Allows validation of a sidecar before the audio has been copied over.
        result = [str(path / 'book.m4b')]
    return result


def doctor(args):
    results = []
    def add(level, subject, message):
        results.append({'level': level, 'subject': subject, 'message': message})
    if args.config:
        try:
            load_config_file(str(args.config.resolve()))
            add('ok', 'configuration', 'Schema and referenced secret files are valid; values withheld.')
        except (ConfigError, OSError) as error:
            add('error', 'configuration', str(error))
    if args.release_config:
        try:
            import release
            settings = release.configuration(args.release_config)
            for service in release.SERVICES:
                if not settings[service]:
                    add('warning', service, 'Release destination is not configured.')
                else:
                    release.git_destination(settings, service)
                    add('ok', service, 'Repository URL and Git destination agree.')
                spec = settings['credentials'].get(service, {})
                if spec.get('provider', 'env') == 'env' and not os.environ.get(spec.get('variable', service.upper() + '_TOKEN')):
                    add('warning', service, 'API token environment reference is not currently set; no credential lookup attempted.')
                elif spec.get('provider') == '1password':
                    add('warning', service, '1Password reference syntax validated; secret lookup and remote permissions not tested.')
        except (ValueError, OSError) as error:
            add('error', 'release settings', str(error))
    for path in args.book:
        try:
            paths = audio_paths(path)
            overrides = load_sidecar(paths)
            add('ok', str(path), 'Per-book settings valid.' if overrides else 'No per-book overrides; normal matching applies.')
            issues = conflicts([(p, read_embedded_metadata(p)) for p in paths])
            for issue in issues:
                add('warning', str(path), 'Conflicting multipart field: ' + issue['field'])
            if not issues:
                add('ok', str(path), 'No contradictory nonempty multipart tags detected.')
        except (ValueError, ConfigError, OSError) as error:
            add('error', str(path), str(error))
    for path in args.artwork:
        try:
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Artwork exceeds 32 MiB')
            with path.open('rb') as stream:
                data = stream.read(MAX_BYTES + 1)
            info = inspect_image(data, require_decode=True)
            if not info:
                raise ValueError('Image cannot be decoded or fails size/aspect/structure limits' if DECODER else
                                 'Full decoding unavailable: install Pillow for this Python interpreter')
            add('warning' if info['low_resolution'] else 'ok', str(path),
                '%dx%d image decoded successfully%s' % (info['width'], info['height'],
                    '; resolution below 200 pixels on one axis' if info['low_resolution'] else ''))
        except (ValueError, OSError) as error:
            add('error', str(path), str(error))
    if not (args.book or args.config or args.release_config or args.artwork):
        from build_provenance import version
        try:
            add('ok', 'bundle version', version(ROOT))
        except (ValueError, OSError) as error:
            add('error', 'bundle version', str(error))
        add('ok' if DECODER else 'warning', 'image decoder', 'Pillow/PIL available.' if DECODER else
            'Pillow/PIL unavailable; plugin uses structural validation. Install Pillow for full offline decoding.')
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for item in results:
            print('%s %s: %s' % (item['level'].upper(), item['subject'], item['message']))
    return 1 if any(item['level'] == 'error' for item in results) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('doctor', help='Read-only local validation; no network or secret lookup')
    check.add_argument('--config', type=Path)
    check.add_argument('--release-config', type=Path)
    check.add_argument('--book', type=Path, action='append', default=[])
    check.add_argument('--artwork', type=Path, action='append', default=[])
    check.add_argument('--json', action='store_true')
    preview = sub.add_parser('preview', help='Compare two saved snapshots without applying changes')
    preview.add_argument('--before', type=Path, required=True)
    preview.add_argument('--after', type=Path, required=True)
    preview.add_argument('--output', type=Path)
    report = sub.add_parser('report', help='Extract the latest album report from a local agent log')
    report.add_argument('--log', type=Path, required=True)
    report.add_argument('--id', help='Optional album metadata identity filter')
    report.add_argument('--output', type=Path)
    export = sub.add_parser('export', help='Export a snapshot/report or saved single-album Plex XML')
    export.add_argument('--input', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            return doctor(args)
        if args.command == 'preview':
            before, after = read_record(args.before), read_record(args.after)
            before, after = before.get('after', before), after.get('after', after)
            write_result({'before': before, 'after': after, 'changes': changes(before, after)}, args.output)
        elif args.command == 'report':
            latest = None
            for line in read_text(args.log).splitlines():
                if 'METADATA_REPORT ' not in line:
                    continue
                try:
                    value = json.loads(line.split('METADATA_REPORT ', 1)[1])
                    if isinstance(value, dict) and isinstance(value.get('after'), dict) and (
                        not args.id or value['after'].get('id') == args.id):
                        latest = value
                except ValueError:
                    continue
            if latest is None:
                raise ValueError('No matching metadata report; enable previews or metadata reports and refresh an album')
            write_result(latest, args.output)
        else:
            value = export_sidecar(read_record(args.input))
            # Exercise exactly the production schema before writing a portable override.
            with tempfile.TemporaryDirectory() as folder:
                (Path(folder) / 'vocalismeta.json').write_text(json.dumps(value))
                load_sidecar([str(Path(folder) / 'book.m4b')])
            write_result(value, args.output, args.overwrite)
        return 0
    except (ValueError, ConfigError, OSError, ET.ParseError) as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
