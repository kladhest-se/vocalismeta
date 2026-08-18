# coding: utf-8
"""Dependency-free, bounded readers for embedded audiobook cover artwork."""

from __future__ import unicode_literals

import base64
import binascii
import io
import os
import struct

from local_artwork import MAX_COVER_BYTES, image_type


MAX_ENCODED_COVER_BYTES = ((MAX_COVER_BYTES + 2) // 3) * 4 + 4096
MAX_SCAN_BYTES = MAX_ENCODED_COVER_BYTES + (4 * 1024 * 1024)
MP4_CONTAINERS = set([b'moov', b'udta'])


def byte_value(data, index):
    value = data[index]
    return value if isinstance(value, int) else ord(value)


def byte_values(data):
    return [byte_value(data, index) for index in range(len(data))]


def synchsafe(raw):
    value = 0
    for byte in byte_values(raw):
        value = (value << 7) | (byte & 0x7f)
    return value


def valid_cover(data, source, path):
    if not data or len(data) > MAX_COVER_BYTES:
        return None
    mime_type = image_type(data[:16])
    if not mime_type:
        return None
    return {
        'data': data,
        'mime_type': mime_type,
        'path': path,
        'size': len(data),
        'source': source,
    }


def encoded_terminator(data, encoding):
    if encoding in (1, 2):
        for index in range(0, len(data) - 1, 2):
            if data[index:index + 2] == b'\x00\x00':
                return index + 2
        return len(data)
    index = data.find(b'\x00')
    return index + 1 if index >= 0 else len(data)


def id3_picture(payload, legacy=False):
    if len(payload) < (6 if legacy else 5):
        return None, None
    encoding = byte_value(payload, 0)
    if legacy:
        picture_type = byte_value(payload, 4)
        description_start = 5
    else:
        mime_end = payload.find(b'\x00', 1)
        if mime_end < 0 or mime_end + 1 >= len(payload):
            return None, None
        picture_type = byte_value(payload, mime_end + 1)
        description_start = mime_end + 2
    image_start = description_start + encoded_terminator(payload[description_start:], encoding)
    if image_start >= len(payload):
        return None, None
    return picture_type, payload[image_start:]


def read_id3_cover(path):
    candidates = []
    with io.open(path, 'rb') as handle:
        header = handle.read(10)
        if len(header) != 10 or header[:3] != b'ID3':
            return None
        major = byte_value(header, 3)
        if major not in (2, 3, 4):
            return None
        tag_size = synchsafe(header[6:10])
        if tag_size <= 0 or tag_size > MAX_SCAN_BYTES:
            return None
        data = handle.read(tag_size)
    if byte_value(header, 5) & 0x80:
        data = data.replace(b'\xff\x00', b'\xff')
    position = 0
    if major in (3, 4) and byte_value(header, 5) & 0x40 and len(data) >= 4:
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
        start = position + header_size
        end = start + frame_size
        if end > len(data):
            break
        if frame_id in (b'APIC', b'PIC') and frame_size <= MAX_COVER_BYTES + 4096:
            picture_type, picture = id3_picture(data[start:end], frame_id == b'PIC')
            cover = valid_cover(picture, 'ID3 APIC', path)
            if cover:
                candidates.append((picture_type == 3, cover))
        position = end
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


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


def read_mp4_cover(path):
    file_size = os.path.getsize(path)
    with io.open(path, 'rb') as handle:
        def walk(start, end, in_ilst=False, depth=0):
            if depth > 8:
                return None
            for atom_type, payload_start, atom_end in iter_atoms(handle, start, end):
                if in_ilst and atom_type == b'covr':
                    for child_type, child_start, child_end in iter_atoms(handle, payload_start, atom_end):
                        if child_type != b'data':
                            continue
                        size = child_end - child_start
                        if size < 8 or size - 8 > MAX_COVER_BYTES:
                            continue
                        handle.seek(child_start + 8)
                        cover = valid_cover(handle.read(size - 8), 'MP4 covr', path)
                        if cover:
                            return cover
                elif atom_type == b'meta':
                    cover = walk(payload_start + 4, atom_end, False, depth + 1)
                    if cover:
                        return cover
                elif atom_type == b'ilst':
                    cover = walk(payload_start, atom_end, True, depth + 1)
                    if cover:
                        return cover
                elif atom_type in MP4_CONTAINERS:
                    cover = walk(payload_start, atom_end, False, depth + 1)
                    if cover:
                        return cover
            return None
        return walk(0, file_size)


def parse_flac_picture(data, source, path):
    if len(data) < 32:
        return None, None
    position = 0
    picture_type = struct.unpack('>I', data[position:position + 4])[0]
    position += 4
    mime_size = struct.unpack('>I', data[position:position + 4])[0]
    position += 4
    if mime_size > 1024 or position + mime_size + 4 > len(data):
        return None, None
    position += mime_size
    description_size = struct.unpack('>I', data[position:position + 4])[0]
    position += 4
    if description_size > 1024 * 1024 or position + description_size + 20 > len(data):
        return None, None
    position += description_size + 16
    image_size = struct.unpack('>I', data[position:position + 4])[0]
    position += 4
    if image_size <= 0 or image_size > MAX_COVER_BYTES or position + image_size > len(data):
        return None, None
    return picture_type, valid_cover(data[position:position + image_size], source, path)


def picture_from_comments(data, source, path):
    if len(data) < 8:
        return None
    position = 0
    vendor_size = struct.unpack('<I', data[:4])[0]
    position = 4 + vendor_size
    if vendor_size > MAX_SCAN_BYTES or position + 4 > len(data):
        return None
    count = min(struct.unpack('<I', data[position:position + 4])[0], 10000)
    position += 4
    candidates = []
    for unused in range(count):
        del unused
        if position + 4 > len(data):
            break
        size = struct.unpack('<I', data[position:position + 4])[0]
        position += 4
        if size > MAX_ENCODED_COVER_BYTES or position + size > len(data):
            break
        comment = data[position:position + size]
        position += size
        if b'=' not in comment:
            continue
        key, encoded = comment.split(b'=', 1)
        if key.strip().upper() != b'METADATA_BLOCK_PICTURE':
            continue
        if not encoded or len(encoded) > MAX_ENCODED_COVER_BYTES:
            continue
        try:
            picture = base64.b64decode(encoded)
        except (TypeError, ValueError, binascii.Error):
            continue
        picture_type, cover = parse_flac_picture(picture, source, path)
        if cover:
            candidates.append((picture_type == 3, cover))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def read_flac_cover(path):
    native = []
    comment_cover = None
    with io.open(path, 'rb') as handle:
        if handle.read(4) != b'fLaC':
            return None
        last = False
        while not last:
            header = handle.read(4)
            if len(header) != 4:
                break
            first = byte_value(header, 0)
            last = bool(first & 0x80)
            block_type = first & 0x7f
            size = struct.unpack('>I', b'\x00' + header[1:4])[0]
            if size > MAX_SCAN_BYTES:
                handle.seek(size, 1)
                continue
            data = handle.read(size)
            if len(data) != size:
                break
            if block_type == 6:
                picture_type, cover = parse_flac_picture(data, 'FLAC picture', path)
                if cover:
                    native.append((picture_type == 3, cover))
            elif block_type == 4 and not comment_cover:
                comment_cover = picture_from_comments(
                    data, 'Vorbis METADATA_BLOCK_PICTURE', path
                )
    if native:
        native.sort(key=lambda item: item[0], reverse=True)
        return native[0][1]
    return comment_cover


def read_ogg_cover(path):
    packets = []
    current = []
    current_size = 0
    consumed = 0
    with io.open(path, 'rb') as handle:
        while len(packets) < 4 and consumed < MAX_SCAN_BYTES:
            header = handle.read(27)
            if len(header) != 27 or header[:4] != b'OggS':
                break
            segment_count = byte_value(header, 26)
            lacing = handle.read(segment_count)
            lacing_values = byte_values(lacing)
            body_size = 0
            for lacing_value in lacing_values:
                body_size += lacing_value
            if consumed + 27 + segment_count + body_size > MAX_SCAN_BYTES:
                break
            body = handle.read(body_size)
            if len(body) != body_size:
                break
            consumed += 27 + segment_count + body_size
            offset = 0
            for size in lacing_values:
                current.append(body[offset:offset + size])
                current_size += size
                offset += size
                if current_size > MAX_SCAN_BYTES:
                    return None
                if size < 255:
                    packets.append(b''.join(current))
                    current = []
                    current_size = 0
                    if len(packets) >= 4:
                        break
    for packet in packets:
        if packet.startswith(b'\x03vorbis'):
            cover = picture_from_comments(
                packet[7:], 'Vorbis METADATA_BLOCK_PICTURE', path
            )
        elif packet.startswith(b'OpusTags'):
            cover = picture_from_comments(
                packet[8:], 'Vorbis METADATA_BLOCK_PICTURE', path
            )
        else:
            cover = None
        if cover:
            return cover
    return None


def read_embedded_cover(path):
    """Return a validated embedded cover dictionary, or None."""
    if not path or not os.path.isfile(path):
        return None
    extension = os.path.splitext(path)[1].lower()
    readers = {
        '.mp3': read_id3_cover,
        '.m4a': read_mp4_cover,
        '.m4b': read_mp4_cover,
        '.mp4': read_mp4_cover,
        '.flac': read_flac_cover,
        '.ogg': read_ogg_cover,
        '.oga': read_ogg_cover,
        '.opus': read_ogg_cover,
    }
    reader = readers.get(extension)
    if not reader:
        return None
    try:
        return reader(path)
    except (IOError, OSError, ValueError, struct.error, OverflowError, MemoryError):
        return None
