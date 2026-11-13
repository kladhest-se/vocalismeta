# coding: utf-8
"""Run on Python 2.7 or Python 3; no Plex runtime or external dependencies."""
from __future__ import unicode_literals

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'VocalisMeta.bundle', 'Contents', 'Code'))
import ljudboksarkivet_core as core


class UnicodeEntities(unittest.TestCase):
    def test_decimal_and_hex_above_byte_range(self):
        self.assertEqual(core.decode_entities('Lagerl&#246;f&#8217;s &#x2014; bok'),
                         'Lagerlöf\u2019s \u2014 bok')

    def test_named_and_ascii_entities(self):
        self.assertEqual(core.decode_entities('&quot;A&amp;B&quot; &#65; &#x42; &nbsp;'),
                         '"A&B" A B  ')

    def test_non_bmp_entity(self):
        self.assertEqual(core.decode_entities('&#x1f600;'), '\U0001f600')

    def test_invalid_scalar_values_do_not_abort_parsing(self):
        self.assertEqual(core.decode_entities('&#0; &#55296; &#xDFFF; &#1114112;'),
                         '\ufffd \ufffd \ufffd \ufffd')
        self.assertEqual(core.decode_entities('&#999999999999999999999999999;'), '\ufffd')

    def test_narrow_python2_character_range(self):
        original = core.unicode_character
        def narrow_character(point):
            if point > 0xffff:
                raise ValueError('outside narrow build range')
            return original(point)
        try:
            core.unicode_character = narrow_character
            result = core.decode_entities('&#128512;')
            self.assertEqual([ord(c) for c in result], [0xd83d, 0xde00])
        finally:
            core.unicode_character = original

    def test_provider_record_decodes_names_and_description(self):
        record = {'@type': 'Audiobook', 'name': 'Boken &#8212; del 1',
                  'author': {'name': 'Selma Lagerl&#246;f'},
                  'description': 'Text med &#x2019; och &#x110000;.'}
        html = '<script type="application/ld+json">' + json.dumps(record) + '</script>'
        parsed = core.audiobook_from_html(html)
        self.assertEqual(parsed['title'], 'Boken \u2014 del 1')
        self.assertEqual(parsed['authors'], ['Selma Lagerlöf'])
        self.assertEqual(parsed['description'], 'Text med \u2019 och \ufffd.')


if __name__ == '__main__':
    unittest.main()
