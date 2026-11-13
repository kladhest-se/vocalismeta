#!/usr/bin/env python3
"""Summarize VocalisMeta candidate diagnostics from a local Plex agent log."""
import argparse
import json
import shlex


def candidates(lines):
    for line in lines:
        if 'MATCH_CANDIDATE ' not in line:
            continue
        try:
            pairs = shlex.split(line.split('MATCH_CANDIDATE ', 1)[1])
            record = dict(pair.split('=', 1) for pair in pairs)
            if all(key in record for key in ('title', 'provider', 'score', 'reason')):
                yield record
        except ValueError:
            continue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', help='Path to a Plex agent log captured with DEBUG logging')
    parser.add_argument('--json', action='store_true', help='Output structured JSON')
    args = parser.parse_args()
    with open(args.log, encoding='utf-8', errors='replace') as stream:
        records = list(candidates(stream))
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for item in records:
            values = dict(region='none', threshold='?', title_agreement='unknown',
                          author_agreement='unknown', runtime_difference_minutes='unknown')
            values.update(item)
            print('{provider} / {region}: {title} — score {score}/{threshold}; {reason}; '
                  'title agreement {title_agreement}, author agreement {author_agreement}, '
                  'runtime difference {runtime_difference_minutes} minutes'.format(**values))
        if not records:
            print('No candidate diagnostics found. Enable DEBUG logging and repeat the match.')


if __name__ == '__main__':
    main()
