# coding: utf-8
"""Bounded image structure/dimension checks and optional real PIL decoding."""
from __future__ import unicode_literals
import binascii
import io
import struct
import zlib
try:
    from PIL import Image as DECODER
except ImportError:
    try:
        import Image as DECODER
    except ImportError:
        DECODER = None

MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 25000000
MAX_DIMENSION = 10000


def byte(data, index):
    value = data[index]
    return value if isinstance(value, int) else ord(value)


def little24(data):
    return byte(data, 0) | (byte(data, 1) << 8) | (byte(data, 2) << 16)


def png_size(data):
    offset, width, height = 8, 0, 0
    compressed = []
    seen_end = False
    chunks = 0
    depth, color, interlace = 0, 0, 0
    while offset + 12 <= len(data):
        chunks += 1
        if chunks > 65536:
            return None
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            return None
        payload = data[offset + 8:end - 4]
        crc = struct.unpack('>I', data[end - 4:end])[0]
        if (binascii.crc32(kind + payload) & 0xffffffff) != crc:
            return None
        if chunks == 1:
            if kind != b'IHDR' or size != 13:
                return None
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if compression or filtering or interlace not in (0, 1):
                return None
        elif kind == b'IHDR':
            return None
        if kind == b'IDAT':
            compressed.append(payload)
        if kind == b'IEND':
            if size or end != len(data):
                return None
            seen_end = True
            break
        offset = end
    if not seen_end or not compressed or not dimensions_ok(width, height):
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if not channels or depth not in (1, 2, 4, 8, 16):
        return None
    if color in (2, 4, 6) and depth not in (8, 16):
        return None
    if color == 3 and depth == 16:
        return None
    passes = [(0, 0, 1, 1)] if interlace == 0 else [
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
    rows = []
    expected = 0
    for x, y, dx, dy in passes:
        w = max(0, (width - x + dx - 1) // dx)
        h = max(0, (height - y + dy - 1) // dy)
        if w and h:
            row = (w * channels * depth + 7) // 8 + 1
            rows.append((row, h))
            expected += row * h
    if expected > 128 * 1024 * 1024:
        return None
    decoder = zlib.decompressobj()
    raw = decoder.decompress(b''.join(compressed), expected + 1)
    if len(raw) != expected or decoder.unconsumed_tail or decoder.unused_data:
        return None
    # The checksum/trailer must be complete, not just enough decoded pixels.
    try:
        if not decoder.eof:
            return None
    except AttributeError:  # Python 2 zlib lacks eof; validate the complete stream.
        if zlib.decompress(b''.join(compressed)) != raw:
            return None
    offset = 0
    for row, count in rows:
        for unused in range(count):
            if byte(raw, offset) > 4:
                return None
            offset += row
    return width, height


def jpeg_size(data):
    offset = 2
    size = None
    frames = (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf)
    while offset + 4 <= len(data):
        if byte(data, offset) != 0xff:
            return None
        while offset < len(data) and byte(data, offset) == 0xff:
            offset += 1
        if offset >= len(data):
            return None
        marker = byte(data, offset)
        offset += 1
        length = struct.unpack('>H', data[offset:offset + 2])[0]
        if length < 2 or offset + length > len(data):
            return None
        if marker in frames:
            if length < 8:
                return None
            height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
            size = (width, height)
        if marker == 0xda:
            # Decoder verifies entropy data when PIL is available.
            return size if size and data.endswith(b'\xff\xd9') else None
        offset += length
    return None


def webp_size(data):
    if struct.unpack('<I', data[4:8])[0] + 8 != len(data):
        return None
    offset, size = 12, None
    frame = False
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        count = struct.unpack('<I', data[offset + 4:offset + 8])[0]
        end = offset + 8 + count
        if end > len(data):
            return None
        payload = data[offset + 8:end]
        if kind in (b'ANIM', b'ANMF'):
            return None
        if kind == b'VP8 ':
            if count < 10 or payload[3:6] != b'\x9d\x01\x2a':
                return None
            w, h = struct.unpack('<HH', payload[6:10])
            size, frame = (w & 0x3fff, h & 0x3fff), True
        elif kind == b'VP8L':
            if count < 5 or byte(payload, 0) != 0x2f:
                return None
            bits = struct.unpack('<I', payload[1:5])[0]
            size, frame = ((bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1), True
        offset = end + count % 2
    return size if frame and offset == len(data) else None


def dimensions_ok(width, height):
    return (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION
            and width * height <= MAX_PIXELS and 0.33 <= float(width) / height <= 3.0)


def inspect_image(data, require_decode=False):
    if not data or len(data) > MAX_BYTES:
        return None
    try:
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime, size = 'image/png', png_size(data)
        elif data.startswith(b'\xff\xd8\xff'):
            mime, size = 'image/jpeg', jpeg_size(data)
        elif len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            mime, size = 'image/webp', webp_size(data)
        else:
            return None
        if not size or not dimensions_ok(size[0], size[1]):
            return None
        decoded = False
        if DECODER is not None:
            image = DECODER.open(io.BytesIO(data))
            if image.size != size or image.format not in ('PNG', 'JPEG', 'WEBP'):
                return None
            image.verify()
            image = DECODER.open(io.BytesIO(data))
            image.load()
            decoded = True
        elif require_decode:
            return None
        return {'mime_type': mime, 'width': size[0], 'height': size[1], 'decoded': decoded,
                'low_resolution': min(size) < 200}
    except Exception:
        return None
