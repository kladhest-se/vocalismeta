# coding: utf-8
"""Small dependency-free readers for audiobook identity tags.

Only textual identity metadata is parsed. Audio frames and cover art are never
loaded, keeping reads bounded even for very large audiobook files.
"""

from __future__ import unicode_literals

import os
import io
import re
import struct

from audible_core import REGION_TLDS, find_asin, text_type, to_text


MAX_TAG_BYTES = 16 * 1024 * 1024
ASIN_KEYS = set([
    'ASIN', 'AUDIBLEASIN', 'AMAZONASIN', 'AUDIBLEPRODUCTID', 'PRODUCTID'
])
LIBRIVOX_ID_KEYS = set([
    'LIBRIVOXID', 'LIBRIVOXBOOKID', 'LIBRIVOXPROJECTID'
])
ISBN_KEYS = set(['ISBN', 'ISBN10', 'ISBN13', 'BOOKISBN'])
REGION_KEYS = set([
    'REGION', 'AUDIBLEREGION', 'AUDIBLEMARKETPLACE', 'MARKETPLACE',
    'WWWAUDIOFILE', 'PURL', 'URL'
])
AUTHOR_KEYS = set([
    'AUTHOR', 'AUTHORS', 'BOOKAUTHOR', 'BOOKAUTHORS',
    'ALBUMARTIST', 'ALBUMARTISTS', 'TPE2', 'AART'
])
NARRATOR_KEYS = set([
    'NARRATOR', 'NARRATORS', 'NARRATEDBY', 'READBY', 'READER', 'READERS',
    'NRT', 'TPE3', 'COMPOSER', 'TCOM'
])
LANGUAGE_KEYS = set(['LANGUAGE', 'LANG', 'TLAN'])
ABRIDGED_KEYS = set(['ABRIDGED', 'ISABRIDGED', 'AUDIBLEABRIDGED', 'FORMATTYPE'])
SERIES_KEYS = set([
    'SERIES', 'SERIESTITLE', 'BOOKSERIES', 'CONTENTGROUP', 'TIT1',
    'GROUPING', 'GRP', 'GRP1', 'MOVEMENTNAME', 'MVN', 'MVNM'
])
SERIES_SEQUENCE_KEYS = set([
    'SERIESPART', 'SERIESNUMBER', 'SERIESINDEX', 'BOOKNUMBER',
    'MOVEMENT', 'MOVEMENTNUMBER', 'MOVEMENTINDEX', 'MVI', 'MVIN'
])
CONTAINER_ATOMS = set([b'moov', b'udta', b'ilst'])
TLD_REGIONS = dict([(value, key) for key, value in REGION_TLDS.items()])
LIBRIVOX_ID_RE = re.compile(r'^[1-9]\d{0,9}$')
LIBRIVOX_HINT_RE = re.compile(
    r'\b(?:librivox|lv)\s*[:#]\s*([1-9]\d{0,9})\b', re.I
)
LIBRIVOX_API_RE = re.compile(
    r'https?://(?:www\.)?librivox\.org/api/feed/audiobooks/?[^\s#]*'
    r'[?&]id=([1-9]\d{0,9})(?:\b|&)', re.I
)


def normalize_key(value):
    return re.sub(r'[^A-Z0-9]', '', to_text(value).upper())


def normalize_librivox_id(value):
    value = to_text(value).strip()
    return value if LIBRIVOX_ID_RE.match(value) else ''


def librivox_id_from_text(value, allow_bare=False):
    value = to_text(value).strip()
    if allow_bare:
        direct = normalize_librivox_id(value)
        if direct:
            return direct
    for pattern in (LIBRIVOX_HINT_RE, LIBRIVOX_API_RE):
        match = pattern.search(value)
        if match:
            return match.group(1)
    return ''


def decode_bytes(value, encoding='utf-8'):
    if isinstance(value, text_type):
        return to_text(value)
    for codec in (encoding, 'utf-8', 'latin-1'):
        try:
            return value.decode(codec).strip('\x00\ufeff')
        except (AttributeError, UnicodeDecodeError, LookupError):
            pass
    try:
        return value.decode('latin-1', 'replace').strip('\x00')
    except AttributeError:
        return to_text(value)


def byte_value(data, index):
    value = data[index]
    return value if isinstance(value, int) else ord(value)


def byte_values(data):
    return [byte_value(data, index) for index in range(len(data))]


def region_from_text(value):
    value = to_text(value).strip().lower()
    direct = value.lstrip('.')
    aliases = {
        'gb': 'uk', 'en-gb': 'uk', 'en_gb': 'uk',
        'en-us': 'us', 'en_us': 'us',
        'en-au': 'au', 'en_au': 'au',
        'en-ca': 'ca', 'en_ca': 'ca',
    }
    if direct in REGION_TLDS:
        return direct
    if direct in aliases:
        return aliases[direct]
    if direct in TLD_REGIONS:
        return TLD_REGIONS[direct]
    match = re.search(r'(?:^|[./])audible\.(com\.au|co\.uk|co\.jp|com|ca|de|es|fr|in|it)(?:[/:]|$)', value)
    if match:
        return TLD_REGIONS.get(match.group(1))
    return None


def normalize_isbn(value):
    value = re.sub(r'[^0-9Xx]', '', to_text(value)).upper()
    if len(value) == 10:
        if not re.match(r'^\d{9}[\dX]$', value):
            return ''
        total = 0
        for index, char in enumerate(value):
            total += (10 - index) * (10 if char == 'X' else int(char))
        return value if total % 11 == 0 else ''
    if len(value) == 13 and value.isdigit():
        total = 0
        for index, char in enumerate(value):
            total += int(char) * (1 if index % 2 == 0 else 3)
        return value if total % 10 == 0 else ''
    return ''


def isbn_values(value):
    output = []
    for item in re.split(r'[,;|\n]+', to_text(value)):
        isbn = normalize_isbn(item)
        if isbn and isbn not in output:
            output.append(isbn)
    return output


def split_names(value):
    return [
        item.strip() for item in re.split(r'[;|\n\x00]+', to_text(value))
        if item.strip()
    ]


def abridged_value(value):
    text = to_text(value).strip().lower()
    if 'unabridged' in text or text in ('0', 'false', 'no', 'full'):
        return False
    if re.search(r'\babridged\b', text) or text in ('1', 'true', 'yes'):
        return True
    return None


def metadata_from_tags(tags):
    """Return validated identity and edition hints from textual tags."""
    normalized = []
    for key, value in tags:
        key = normalize_key(key)
        if isinstance(value, (list, tuple)):
            values = value
        else:
            values = [value]
        for item in values:
            text = to_text(item).strip()
            if text:
                normalized.append((key, text))

    asin = None
    librivox_id = None
    region = None
    isbns = []
    authors = []
    narrators = []
    language = None
    abridged = None
    series = None
    series_sequence = None
    for key, value in normalized:
        if not asin and key in ASIN_KEYS:
            asin = find_asin(value)
        if not librivox_id and key in LIBRIVOX_ID_KEYS:
            librivox_id = librivox_id_from_text(value, True) or None
        if not region and key in REGION_KEYS:
            region = region_from_text(value)
        if key in ISBN_KEYS:
            for isbn in isbn_values(value):
                if isbn not in isbns:
                    isbns.append(isbn)
        if key in AUTHOR_KEYS:
            for author in split_names(value):
                if author not in authors:
                    authors.append(author)
        if key in NARRATOR_KEYS:
            for narrator in split_names(value):
                if narrator not in narrators:
                    narrators.append(narrator)
        if not language and key in LANGUAGE_KEYS:
            language = value
        if abridged is None and key in ABRIDGED_KEYS:
            abridged = abridged_value(value)
        if not series and key in SERIES_KEYS:
            series = re.sub(r'\s+', ' ', value).strip()[:200] or None
        if not series_sequence and key in SERIES_SEQUENCE_KEYS:
            series_sequence = re.sub(r'\s+', ' ', value).strip()[:64] or None
    for unused_key, value in normalized:
        del unused_key
        lower = value.lower()
        if not region:
            region = region_from_text(value)
        if not asin and ('audible.' in lower or 'amazon.' in lower):
            asin = find_asin(value)
        if not librivox_id:
            librivox_id = librivox_id_from_text(value) or None
    return {
        'asin': asin,
        'librivox_id': librivox_id,
        'region': region,
        'isbns': isbns,
        'authors': authors,
        'narrators': narrators,
        'language': language,
        'abridged': abridged,
        'series': series,
        'series_sequence': series_sequence,
    }


def identity_from_tags(tags):
    """Return the legacy (asin, region) tuple for compatibility."""
    metadata = metadata_from_tags(tags)
    return metadata['asin'], metadata['region']


def synchsafe(raw):
    value = 0
    for byte in byte_values(raw):
        value = (value << 7) | (byte & 0x7f)
    return value


def id3_terminator(data, encoding):
    if encoding in (1, 2):
        for index in range(0, len(data) - 1, 2):
            if data[index:index + 2] == b'\x00\x00':
                return index, 2
        return len(data), 0
    index = data.find(b'\x00')
    return (index, 1) if index >= 0 else (len(data), 0)


def decode_id3(data, encoding):
    codecs = {0: 'latin-1', 1: 'utf-16', 2: 'utf-16-be', 3: 'utf-8'}
    return decode_bytes(data, codecs.get(encoding, 'utf-8')).strip('\x00')


def parse_id3(path):
    tags = []
    with io.open(path, 'rb') as handle:
        header = handle.read(10)
        if len(header) != 10 or header[:3] != b'ID3' or byte_value(header, 3) not in (2, 3, 4):
            return tags
        major = byte_value(header, 3)
        tag_size = min(synchsafe(header[6:10]), MAX_TAG_BYTES)
        data = handle.read(tag_size)
    flags = byte_value(header, 5)
    if flags & 0x80:
        data = data.replace(b'\xff\x00', b'\xff')

    position = 0
    if major in (3, 4) and flags & 0x40 and len(data) >= 4:
        extended = synchsafe(data[:4]) if major == 4 else struct.unpack('>I', data[:4])[0]
        position = min(len(data), extended + (0 if major == 4 else 4))

    while position < len(data):
        if major == 2:
            if position + 6 > len(data):
                break
            frame_id = data[position:position + 3]
            frame_size = struct.unpack('>I', b'\x00' + data[position + 3:position + 6])[0]
            header_size = 6
        else:
            if position + 10 > len(data):
                break
            frame_id = data[position:position + 4]
            raw_size = data[position + 4:position + 8]
            frame_size = synchsafe(raw_size) if major == 4 else struct.unpack('>I', raw_size)[0]
            header_size = 10
        if not frame_id.strip(b'\x00') or frame_size <= 0:
            break
        payload_start = position + header_size
        payload_end = payload_start + frame_size
        if payload_end > len(data):
            break
        payload = data[payload_start:payload_end]
        frame_name = decode_bytes(frame_id, 'latin-1')
        if payload and frame_name in ('TXXX', 'TXX'):
            encoding = byte_value(payload, 0)
            raw = payload[1:]
            split_at, width = id3_terminator(raw, encoding)
            tags.append((decode_id3(raw[:split_at], encoding), decode_id3(raw[split_at + width:], encoding)))
        elif payload and frame_name in ('WXXX', 'WXX'):
            encoding = byte_value(payload, 0)
            raw = payload[1:]
            split_at, width = id3_terminator(raw, encoding)
            tags.append((decode_id3(raw[:split_at], encoding), decode_bytes(raw[split_at + width:], 'latin-1')))
        elif payload and (
            frame_name.startswith('T')
            or frame_name in ('GRP1', 'MVNM', 'MVIN')
        ):
            tags.append((frame_name, decode_id3(payload[1:], byte_value(payload, 0))))
        elif payload and frame_name in ('COMM', 'COM') and len(payload) > 4:
            encoding = byte_value(payload, 0)
            raw = payload[4:]
            split_at, width = id3_terminator(raw, encoding)
            tags.append(('COMMENT', decode_id3(raw[split_at + width:], encoding)))
        position = payload_end
    return tags


def iter_atoms(handle, start, end):
    atoms = []
    position = start
    while position + 8 <= end:
        handle.seek(position)
        header = handle.read(8)
        if len(header) != 8:
            break
        size = struct.unpack('>I', header[:4])[0]
        atom_type = header[4:8]
        header_size = 8
        if size == 1:
            extended = handle.read(8)
            if len(extended) != 8:
                break
            size = struct.unpack('>Q', extended)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            break
        atoms.append((atom_type, position + header_size, position + size))
        position += size
    return atoms


def parse_mp4_item(handle, item_type, start, end, key_name=None):
    values = {}
    for atom_type, payload_start, atom_end in iter_atoms(handle, start, end):
        handle.seek(payload_start)
        payload = handle.read(min(atom_end - payload_start, MAX_TAG_BYTES))
        if atom_type == b'data':
            values['data'] = decode_bytes(payload[8:] if len(payload) >= 8 else payload)
        elif atom_type in (b'name', b'mean'):
            values[decode_bytes(atom_type, 'latin-1')] = decode_bytes(payload[4:] if len(payload) >= 4 else payload)
    if item_type == b'----':
        return values.get('name', '----'), values.get('data', '')
    return key_name or decode_bytes(item_type, 'latin-1'), values.get('data', '')


def parse_mp4_keys(handle, start, end):
    handle.seek(start)
    data = handle.read(min(end - start, MAX_TAG_BYTES))
    if len(data) < 8:
        return {}
    count = min(struct.unpack('>I', data[4:8])[0], 10000)
    position = 8
    output = {}
    for index in range(1, count + 1):
        if position + 8 > len(data):
            break
        size = struct.unpack('>I', data[position:position + 4])[0]
        if size < 8 or position + size > len(data):
            break
        output[index] = decode_bytes(data[position + 8:position + size])
        position += size
    return output


def parse_mp4(path):
    tags = []
    file_size = os.path.getsize(path)
    with io.open(path, 'rb') as handle:
        def walk(start, end, in_ilst=False, depth=0, key_map=None):
            if depth > 8:
                return
            for atom_type, payload_start, atom_end in iter_atoms(handle, start, end):
                if in_ilst:
                    key_index = struct.unpack('>I', atom_type)[0]
                    key_name = key_map.get(key_index) if key_map else None
                    tags.append(parse_mp4_item(
                        handle, atom_type, payload_start, atom_end, key_name
                    ))
                elif atom_type == b'meta':
                    meta_start = payload_start + 4
                    meta_keys = {}
                    for child_type, child_start, child_end in iter_atoms(handle, meta_start, atom_end):
                        if child_type == b'keys':
                            meta_keys = parse_mp4_keys(handle, child_start, child_end)
                            break
                    walk(meta_start, atom_end, False, depth + 1, meta_keys)
                elif atom_type == b'ilst':
                    walk(payload_start, atom_end, True, depth + 1, key_map)
                elif atom_type in CONTAINER_ATOMS:
                    walk(payload_start, atom_end, False, depth + 1, key_map)
        walk(0, file_size)
    return tags


def parse_vorbis_block(data):
    tags = []
    if len(data) < 8:
        return tags
    position = 0
    vendor_size = struct.unpack('<I', data[position:position + 4])[0]
    position += 4 + vendor_size
    if position + 4 > len(data):
        return tags
    count = min(struct.unpack('<I', data[position:position + 4])[0], 10000)
    position += 4
    for unused in range(count):
        del unused
        if position + 4 > len(data):
            break
        size = struct.unpack('<I', data[position:position + 4])[0]
        position += 4
        if size > MAX_TAG_BYTES or position + size > len(data):
            break
        comment = decode_bytes(data[position:position + size])
        position += size
        if '=' in comment:
            tags.append(tuple(comment.split('=', 1)))
    return tags


def parse_flac(path):
    tags = []
    with io.open(path, 'rb') as handle:
        if handle.read(4) != b'fLaC':
            return tags
        last = False
        while not last:
            header = handle.read(4)
            if len(header) != 4:
                break
            first = byte_value(header, 0)
            last = bool(first & 0x80)
            block_type = first & 0x7f
            size = struct.unpack('>I', b'\x00' + header[1:4])[0]
            if size > MAX_TAG_BYTES:
                handle.seek(size, 1)
                continue
            data = handle.read(size)
            if block_type == 4:
                tags.extend(parse_vorbis_block(data))
    return tags


def parse_ogg(path):
    tags = []
    packets = []
    current = []
    consumed = 0
    with io.open(path, 'rb') as handle:
        while len(packets) < 4 and consumed < MAX_TAG_BYTES:
            header = handle.read(27)
            if len(header) != 27 or header[:4] != b'OggS':
                break
            segment_count = byte_value(header, 26)
            lacing = handle.read(segment_count)
            lacing_values = byte_values(lacing)
            body_size = 0
            for lacing_value in lacing_values:
                body_size += lacing_value
            body = handle.read(body_size)
            consumed += 27 + segment_count + body_size
            offset = 0
            for size in lacing_values:
                current.append(body[offset:offset + size])
                offset += size
                if size < 255:
                    packets.append(b''.join(current))
                    current = []
                    if len(packets) >= 4:
                        break
    for packet in packets:
        if packet.startswith(b'\x03vorbis'):
            tags.extend(parse_vorbis_block(packet[7:]))
        elif packet.startswith(b'OpusTags'):
            tags.extend(parse_vorbis_block(packet[8:]))
    return tags


def parse_apev2(path):
    tags = []
    file_size = os.path.getsize(path)
    if file_size < 32:
        return tags
    with io.open(path, 'rb') as handle:
        handle.seek(file_size - 32)
        footer = handle.read(32)
        if footer[:8] != b'APETAGEX':
            return tags
        tag_size = struct.unpack('<I', footer[12:16])[0]
        item_count = min(struct.unpack('<I', footer[16:20])[0], 10000)
        if tag_size < 32 or tag_size > min(file_size, MAX_TAG_BYTES):
            return tags
        start = file_size - tag_size
        handle.seek(start)
        if handle.read(8) == b'APETAGEX':
            handle.seek(start + 32)
        else:
            handle.seek(start)
        limit = file_size - 32
        for unused in range(item_count):
            del unused
            if handle.tell() + 8 > limit:
                break
            value_size, flags = struct.unpack('<II', handle.read(8))
            key_data = []
            while handle.tell() < limit and len(key_data) < 1024:
                byte = handle.read(1)
                if not byte or byte == b'\x00':
                    break
                key_data.append(byte)
            if value_size > MAX_TAG_BYTES or handle.tell() + value_size > limit:
                break
            value = handle.read(value_size)
            if ((flags >> 1) & 3) == 0:
                tags.append((decode_bytes(b''.join(key_data)), decode_bytes(value)))
    return tags


def read_embedded_metadata(path):
    result = {
        'asin': None, 'librivox_id': None, 'region': None,
        'format': None, 'isbns': [],
        'authors': [], 'narrators': [], 'language': None, 'abridged': None,
        'series': None, 'series_sequence': None,
    }
    if not path or not os.path.isfile(path):
        return result
    extension = os.path.splitext(path)[1].lower()
    readers = {
        '.mp3': ('ID3', parse_id3),
        '.m4a': ('MP4', parse_mp4),
        '.m4b': ('MP4', parse_mp4),
        '.mp4': ('MP4', parse_mp4),
        '.flac': ('FLAC', parse_flac),
        '.ogg': ('Ogg', parse_ogg),
        '.oga': ('Ogg', parse_ogg),
        '.opus': ('Opus', parse_ogg),
    }
    tags = []
    try:
        if extension in readers:
            result['format'], reader = readers[extension]
            tags.extend(reader(path))
        # APEv2 may coexist with MP3/FLAC and is the primary tag for WavPack.
        ape_tags = parse_apev2(path)
        if ape_tags:
            result['format'] = result['format'] or 'APEv2'
            tags.extend(ape_tags)
        metadata = metadata_from_tags(tags)
        result.update(metadata)
    except (IOError, OSError, ValueError, struct.error, OverflowError):
        return result
    return result


def read_embedded_identity(path):
    """Return the original compact identity result for existing callers."""
    metadata = read_embedded_metadata(path)
    return dict([
        (key, metadata.get(key)) for key in ('asin', 'region', 'format')
    ])
