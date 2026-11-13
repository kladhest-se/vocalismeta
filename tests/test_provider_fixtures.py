import json
from pathlib import Path
import unittest
from test_regressions import agent, ROOT
import audible_core
import openlibrary_core
import googlebooks_core
import librivox_core
import ljudboksarkivet_core

FIXTURES = ROOT / 'tests/fixtures/providers'


class ProviderFixtures(unittest.TestCase):
    def test_normal_partial_and_malformed_envelopes(self):
        parsers = {'audible': audible_core.products_from_response,
                   'openlibrary': openlibrary_core.documents_from_response,
                   'googlebooks': googlebooks_core.volumes_from_response,
                   'librivox': librivox_core.books_from_response}
        for provider, parse in parsers.items():
            data = json.loads((FIXTURES / (provider + '.json')).read_text())
            with self.subTest(provider=provider):
                self.assertEqual(len(parse(data['normal'])), 1)
                self.assertEqual(len(parse(data['partial'])), 1)
                for malformed in data['malformed']:
                    self.assertEqual(parse(malformed), [])

    def test_audible_fixture_preserves_missing_relationships(self):
        data = json.loads((FIXTURES / 'audible.json').read_text())
        g = agent()
        full = audible_core.products_from_response(data['normal'])[0]
        partial = audible_core.products_from_response(data['partial'])[0]
        old = g['audible_v3_tags'](full)
        self.assertEqual(g['merge_v3_tags'](old, g['audible_v3_tags'](partial)), old)

    def test_swedish_graph_and_malformed_html(self):
        html = (FIXTURES / 'ljudboksarkivet.html').read_text()
        book = ljudboksarkivet_core.audiobook_from_html(html)
        self.assertEqual(book['title'], 'Fixture Book — edition')
        self.assertEqual(book['duration_minutes'], 120)
        self.assertEqual(book['narrators'], ['Fixture Reader'])
        for malformed in ('', '<html>unavailable</html>',
            '<script type="application/ld+json">{broken}</script>',
            '<script type="application/ld+json">{"@type":"Audiobook","name":"No author"}</script>'):
            self.assertIsNone(ljudboksarkivet_core.audiobook_from_html(malformed))
