# coding: utf-8
"""Compare candidate image bytes with the agent's last observed digests."""
from __future__ import unicode_literals
import re


def known_hashes(keys, saved):
    result = {}
    if not isinstance(saved, dict):
        saved = {}
    for key in keys:
        value = saved.get(key)
        try:
            valid = re.match(r'^[0-9a-f]{64}$', value) if value else None
        except TypeError:
            valid = False
        result[key] = value if valid else None
    return result


def artwork_updates(before, candidates, after_keys):
    updates = {}
    for key in after_keys:
        if key not in candidates:
            continue
        previous = before.get(key)
        current = candidates[key]
        state = ('added' if key not in before else 'unknown' if not previous
                 else 'unchanged' if previous == current else 'changed')
        updates[key] = {'before_sha256': previous, 'after_sha256': current,
                        'content_change': state, 'same_key': key in before}
    return updates
