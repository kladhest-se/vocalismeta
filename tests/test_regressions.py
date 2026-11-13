"""Offline regression and published-contract checks; no Plex/network required."""
import ast
import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / 'VocalisMeta.bundle/Contents/Code'
sys.path.insert(0, str(CODE))
import audible_core
import config_core
import identity_core
import ljudboksarkivet_core


class Tags(list):
    def add(self, value):
        self.append(value)


def agent():
    g = {'Agent': SimpleNamespace(Artist=object, Album=object),
         'Locale': SimpleNamespace(Language=SimpleNamespace(English='en')),
         'CACHE_1DAY': 86400, 'CACHE_1WEEK': 604800}
    path = CODE / '__init__.py'
    exec(compile(path.read_text(), str(path), 'exec'), g)
    g['pref'] = lambda key, default=None: default
    g['log'] = lambda *args, **kwargs: None
    return g


class Matching(unittest.TestCase):
    def test_author_conflict_cannot_auto_match(self):
        product = {'asin': 'B000000001', 'title': 'The Journey',
                   'authors': [{'name': 'Bob Jones'}], 'language': 'english'}
        score = audible_core.score_product('The Journey', 'Alice Smith', 'en', product)
        self.assertLess(score, 80)
        self.assertGreaterEqual(score, 45)  # still available for manual review

    def test_matching_compound_author_and_missing_author(self):
        p = {'asin': 'B000000001', 'title': 'Book', 'authors': [{'name': 'Neil Gaiman'}]}
        self.assertGreaterEqual(audible_core.score_product('Book', 'Terry Pratchett & Neil Gaiman', '', p), 80)
        p['authors'] = []
        self.assertLess(audible_core.score_product('Book', 'Neil Gaiman', '', p), 80)
        self.assertGreaterEqual(audible_core.score_product('Book', '', '', p), 80)

    def test_unknown_scanner_author_does_not_block_match(self):
        g = agent()
        p = {'asin': 'B000000001', 'title': 'Book', 'authors': [{'name': 'Author'}]}
        ranked = g['ranked_audible_candidates']([('us', 0, p)], ['Book'],
            '[Unknown Artist]', '', None, [], None, None, '2026-11-12')
        self.assertGreaterEqual(ranked[0][0], 80)


class Refresh(unittest.TestCase):
    def setUp(self):
        self.g = agent()

    def test_replace_narrator_namespace_and_rating_source(self):
        old = ['Contributor-ID: narrator:name:0123456789abcdef = Old',
               'Contributor-ID: author:openlibrary:OL1A = Author',
               'Rating-Source: Audible', 'Rating-Count: 100']
        new = ['Contributor-ID: narrator:audible:B000000002 = New',
               'Rating-Source: Ljudboksarkivet']
        merged = self.g['merge_v3_tags'](old, new)
        self.assertNotIn(old[0], merged)
        self.assertNotIn('Rating-Count: 100', merged)
        self.assertIn(old[1], merged)
        self.assertIn(new[0], merged)

    def test_partial_response_preserves_omitted_namespaces(self):
        old = ['Contributor-ID: narrator:audible:B000000001 = Old', 'Rating-Source: Audible', 'Rating-Count: 100']
        self.assertEqual(self.g['merge_v3_tags'](old, []), old)
        merged = self.g['merge_v3_tags'](old, ['Rating-Source: Audible'])
        self.assertIn('Rating-Count: 100', merged)

    def test_multiple_new_contributors_replace_old_source(self):
        old = ['Contributor-ID: author:audible:B000000001 = Old']
        new = ['Contributor-ID: author:audible:B000000002 = One',
               'Contributor-ID: author:audible:B000000003 = Two']
        self.assertEqual(self.g['merge_v3_tags'](old, new), new)

    def metadata(self):
        return SimpleNamespace(moods=Tags(['Work-ID: openlibrary:OL1W', 'Work-Published: 1900',
            'Contributor-ID: author:openlibrary:OL1A = Author']), summary='Summary',
            originally_available_at=datetime.date(2000, 1, 1), genres=['Fiction'], posters={})

    def test_failed_forced_enrichment_preserves_work_tags(self):
        g = self.g
        m = self.metadata()
        old = list(m.moods)
        g['artwork_from_paths'] = lambda paths: None
        g['media_file_paths'] = lambda media: []
        g['apply_openlibrary_enrichment'] = lambda *args: False
        g['apply_artwork'] = lambda *args: None
        g['enrich_and_apply_book_artwork'](m, None, {}, 'Book', ['Author'], 'en', ['cover'], {}, True)
        self.assertEqual(m.moods, old)

    def test_successful_enrichment_replaces_work_tags(self):
        g = self.g
        m = self.metadata()
        g['best_openlibrary_document'] = lambda *args: {'key': '/works/OL2W',
            'first_publish_year': 1950, 'author_key': ['OL2A'], 'author_name': ['New Author']}
        g['apply_openlibrary_enrichment'](m, {}, 'Book', 'Author', 'en', [], False, False, [], None)
        self.assertIn('Work-ID: openlibrary:OL2W', m.moods)
        self.assertIn('Work-Published: 1950', m.moods)
        self.assertNotIn('Work-ID: openlibrary:OL1W', m.moods)

    def test_implausible_work_still_removed(self):
        g = self.g
        m = self.metadata()
        g['best_openlibrary_document'] = lambda *args: {'key': '/works/OL2W', 'first_publish_year': 2100}
        g['apply_openlibrary_enrichment'](m, {}, 'Book', 'Author', 'en', [], False, False, [], None)
        self.assertFalse(m.moods)

    def test_provider_label_recovered_when_lookup_unavailable(self):
        g = self.g
        label = ljudboksarkivet_core.search_result_label({'title': 'Boken', 'authors': ['Författare']})
        g['embedded_identity_from_paths'] = lambda paths: {}
        g['media_file_paths'] = lambda media: []
        g['enrich_and_apply_book_artwork'] = lambda *args: None
        g['log_album_update_summary'] = lambda *args: None
        m = SimpleNamespace(title=label, title_sort=label, moods=Tags(), styles=Tags())
        g['VocalisMetaAlbum']().update_local(m, SimpleNamespace(album='Boken', artist='Författare'), 'sv', False, 'local', '0123456789abcdef')
        self.assertEqual(m.title, 'Boken')
        self.assertEqual(m.title_sort, 'Boken')

    def test_custom_title_preserved(self):
        self.assertFalse(self.g['is_local_metadata_search_label']('My custom title'))
        self.assertEqual(self.g['local_metadata_title']('My custom title'), 'My custom title')


class CatalogueCache(unittest.TestCase):
    def setUp(self):
        self.g = agent()
        self.now = 100
        self.calls = []
        self.failed = False
        self.slug = 'old'
        self.g['time'] = lambda: self.now
        def request(url, cache, status, headers):
            self.calls.append(url)
            status.update(ok=not self.failed)
            if self.failed:
                return ''
            if url.endswith('/sitemap.xml'):
                return '<loc>https://ljudboksarkivet.se/sitemap-books-1.xml</loc>'
            return '<loc>https://ljudboksarkivet.se/ljudbok/%s</loc>' % self.slug
        self.g['request_text'] = request

    def test_expiry_refreshes_catalogue(self):
        f = self.g['fetch_ljudboksarkivet_slugs']
        self.assertEqual(f(), ['old'])
        f()
        self.assertEqual(len(self.calls), 2)
        self.now += 604801
        self.slug = 'new'
        self.assertEqual(f(), ['new'])
        self.assertEqual(len(self.calls), 4)

    def test_failed_reload_preserves_complete_index(self):
        f = self.g['fetch_ljudboksarkivet_slugs']
        f()
        self.now += 604801
        self.failed = True
        self.assertEqual(f(), ['old'])
        self.failed = False
        self.slug = 'new'
        self.assertEqual(f(), ['new'])

    def test_partial_load_is_not_cached_as_complete(self):
        calls = []
        def request(url, cache, status, headers):
            calls.append(url)
            status.update(ok=True)
            if url.endswith('/sitemap.xml'):
                return ''.join('<loc>https://ljudboksarkivet.se/sitemap-books-%d.xml</loc>' % i for i in (1, 2))
            if url.endswith('-2.xml'):
                return ''
            return '<loc>https://ljudboksarkivet.se/ljudbok/one</loc>'
        self.g['request_text'] = request
        self.assertEqual(self.g['fetch_ljudboksarkivet_slugs'](), ['one'])
        self.assertIsNone(self.g['LJUDBOKSARKIVET_INDEX_STATE']['slugs'])
        self.g['fetch_ljudboksarkivet_slugs']()
        self.assertEqual(len(calls), 6)


class PublishedContracts(unittest.TestCase):
    def vectors(self, version, key):
        return json.loads((ROOT / ('client-contract/test-vectors-v%d.json' % version)).read_text())[key]

    def test_v1_identities(self):
        for v in self.vectors(1, 'identity_vectors'):
            with self.subTest(v['name']):
                self.assertEqual(identity_core.client_identity(v['input']), v['expected_parsed'])
                self.assertEqual(identity_core.canonical_client_key(v['input']) or None, v['expected_canonical_key'])

    def test_v1_relationships(self):
        g = agent()
        for v in self.vectors(1, 'relationship_vectors'):
            with self.subTest(v['name']):
                p = g['existing_relationship_metadata'](v['moods'])
                self.assertEqual(p['authors'], v['expected']['additional_authors'])
                self.assertEqual([{'name': s['title'], 'position': s['sequence'] or None} for s in p['series']], v['expected']['series'])
                self.assertEqual([p['language']] if p['language'] else [], v['expected']['languages'])
                self.assertEqual(['Abridged' if p['abridged'] else 'Unabridged'] if p['abridged'] is not None else [], v['expected']['editions'])
                self.assertEqual(v['styles'], v['expected']['narrators'])

    def test_v2_work_identity(self):
        g = agent()
        for v in self.vectors(2, 'work_identity_vectors'):
            with self.subTest(v['name']):
                identities = g['existing_work_identities'](v['moods'])
                identity = identities[0] if identities else None
                self.assertEqual(identity, v['expected_work_identity'])
                self.assertEqual('spokenmeta:work:' + identity if identity else None, v['expected_canonical_work_key'])
                self.assertEqual(g['existing_relationship_metadata'](v['moods'])['authors'], v['expected_additional_authors'])

    def test_v3_extended_metadata(self):
        g = agent()
        for v in self.vectors(3, 'extended_metadata_vectors'):
            with self.subTest(v['name']):
                actual = dict(additional_authors=g['existing_relationship_metadata'](v['moods'])['authors'],
                    contributors=[], work_published=None, production=None, rating_source=None, rating_count=None)
                for tag in g['existing_v3_enrichment_tags'](v['moods']):
                    prefix, value = tag.split(': ', 1)
                    if prefix == 'Contributor-ID':
                        identity, name = value.split(' = ', 1)
                        role, source, identifier = identity.split(':')
                        actual['contributors'].append(dict(role=role, source=source, id=identifier,
                            name=name, key='spokenmeta:contributor:' + identity))
                    else:
                        field = {'Work-Published': 'work_published', 'Production': 'production',
                                 'Rating-Source': 'rating_source', 'Rating-Count': 'rating_count'}[prefix]
                        actual[field] = int(value) if field in ('work_published', 'rating_count') else value
                self.assertEqual(actual, v['expected'])

    def test_example_configuration(self):
        loaded = config_core.load_config_file(str(ROOT / 'config.example.json'))
        self.assertEqual(loaded['values']['request_retries'], 3)

    def test_installer_compatibility_checks(self):
        script = (ROOT / 'scripts/install-on-plex.sh').read_text()
        check = script.split("python3 - \"$bundle_source/Contents/Code\" <<'PY'\n", 1)[1].split('\nPY', 1)[0]
        previous = sys.argv
        try:
            sys.argv = ['installer-check', str(CODE)]
            exec(compile(check, 'installer-check', 'exec'), {})
        finally:
            sys.argv = previous


if __name__ == '__main__':
    unittest.main()
