# coding: utf-8
"""Unicode scalar iteration independent of Python's narrow/wide string storage."""
from __future__ import unicode_literals


def codepoints(value):
    points = []
    index = 0
    while index < len(value):
        point = ord(value[index])
        if 0xd800 <= point <= 0xdbff and index + 1 < len(value):
            low = ord(value[index + 1])
            if 0xdc00 <= low <= 0xdfff:
                point = 0x10000 + ((point - 0xd800) << 10) + low - 0xdc00
                index += 1
        points.append(point)
        index += 1
    return points


def fingerprint(value):
    checksum = 14695981039346656037
    modulus = 18446744073709551616
    for point in codepoints(value):
        checksum = (checksum ^ point) * 1099511628211 % modulus
    return '%016x' % checksum
