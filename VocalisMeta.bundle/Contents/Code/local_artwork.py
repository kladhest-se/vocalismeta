# coding: utf-8
"""Locate and safely load local audiobook cover files."""

from __future__ import unicode_literals

import hashlib
import io
import os
import re
from artwork_core import inspect_image


MAX_COVER_BYTES = 32 * 1024 * 1024
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
PREFERRED_STEMS = ('cover', 'folder', 'front')


def image_type(header):
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    return None


def inspect_cover(path):
    try:
        size = os.path.getsize(path)
        if size <= 0 or size > MAX_COVER_BYTES:
            return None
        with io.open(path, 'rb') as handle:
            data = handle.read(MAX_COVER_BYTES + 1)
        info = inspect_image(data)
        if not info:
            return None
        info.update({'path': path, 'size': len(data)})
        return info
    except (IOError, OSError):
        return None


def find_local_cover(audio_path):
    if not audio_path:
        return None
    directory = os.path.dirname(audio_path)
    audio_stem = os.path.splitext(os.path.basename(audio_path))[0].lower()
    if not directory or not os.path.isdir(directory):
        return None
    try:
        names = os.listdir(directory)
    except (IOError, OSError):
        return None
    by_lower = dict([(name.lower(), name) for name in names])
    candidates = []
    for stem in PREFERRED_STEMS + (audio_stem,):
        for extension in IMAGE_EXTENSIONS:
            name = by_lower.get(stem + extension)
            if name:
                candidates.append(os.path.join(directory, name))
    for candidate in candidates:
        cover = inspect_cover(candidate)
        if cover:
            return cover
    return None


def read_cover(cover):
    if not cover:
        return None
    embedded = cover.get('data')
    if embedded is not None:
        if 0 < len(embedded) <= MAX_COVER_BYTES and inspect_image(embedded):
            return embedded
        return None
    if not cover.get('path'):
        return None
    try:
        if os.path.getsize(cover['path']) > MAX_COVER_BYTES:
            return None
        with io.open(cover['path'], 'rb') as handle:
            data = handle.read(MAX_COVER_BYTES + 1)
        return data if inspect_image(data) else None
    except (IOError, OSError):
        return None


def poster_key(cover):
    path = cover.get('path', '') if cover else ''
    source = cover.get('source', '') if cover else ''
    identity = '%s\x00%s' % (source, path)
    digest = hashlib.sha1(identity.encode('utf-8')).hexdigest()
    basename = re.sub(r'[^A-Za-z0-9._-]+', '-', os.path.basename(path))
    scheme = 'embedded-artwork' if source else 'local-artwork'
    return '%s://%s/%s' % (scheme, digest, basename or 'cover')
