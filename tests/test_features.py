"""Offline integration coverage for local overrides, stable selections and limits."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_regressions import agent, Tags
import sidecar_core
import search_runtime
from config_core import ConfigError, load_config_file


class Store(dict):
    def Save(self):
        pass


class Selections(unittest.TestCase):
    def setUp(self):
        self.g = agent()
        self.store = Store()
        self.g['Dict'] = self.store
        self.media = SimpleNamespace(id='100')
        self.book = {'title': 'Boken', 'authors': ['Author'], 'narrators': ['Reader'],
                     'isbn': '9780593135204', '_vocalismeta_slug': 'boken-reader'}
        self.identity = self.g['ljudboksarkivet_identity'](self.book)
        self.called = []
        self.updater = SimpleNamespace(update_ljudboksarkivet=lambda *args: self.called.append(args))

    def update(self, label='Boken'):
        kind, value = self.identity.split(':', 1)
        return self.g['update_saved_ljudboksarkivet'](self.updater,
            SimpleNamespace(title=label), self.media, 'sv', False, {}, kind, value)

    def test_selection_survives_new_agent_namespace(self):
        self.g['remember_ljudboksarkivet_candidates'](self.media, [(99, self.book)])
        self.g = agent()  # process restart: only the persisted Dict survives
        self.g['Dict'] = self.store
        slugs = []
        self.g['fetch_ljudboksarkivet_book'] = lambda slug: slugs.append(slug) or self.book
        self.assertTrue(self.update())
        self.assertEqual(slugs, ['boken-reader'])
        self.assertEqual(len(self.called), 1)
        self.assertEqual(next(iter(self.store.values()))['selected'], 'boken-reader')

    def test_same_isbn_candidates_resolve_selected_label(self):
        other = dict(self.book, narrators=['Other'], _vocalismeta_slug='boken-other')
        self.g['remember_ljudboksarkivet_candidates'](self.media, [(99, self.book), (98, other)])
        self.g['fetch_ljudboksarkivet_book'] = lambda slug: other if slug == 'boken-other' else self.book
        self.update(self.g['ljudboksarkivet_result_label'](other))
        self.assertEqual(self.called[0][-2]['narrators'], ['Other'])

    def test_outage_does_not_fall_back_to_search(self):
        self.g['save_ljudboksarkivet_selection'](self.media, self.identity, self.book)
        self.g['fetch_ljudboksarkivet_book'] = lambda slug: None
        self.assertTrue(self.update())
        self.assertFalse(self.called)
        self.assertEqual(next(iter(self.store.values()))['selected'], 'boken-reader')

    def test_changed_identity_rejected(self):
        self.g['save_ljudboksarkivet_selection'](self.media, self.identity, self.book)
        self.g['fetch_ljudboksarkivet_book'] = lambda slug: dict(self.book, isbn='9780140328721')
        self.assertTrue(self.update())
        self.assertFalse(self.called)

    def test_media_scoping(self):
        self.g['save_ljudboksarkivet_selection'](self.media, self.identity, self.book)
        self.media = SimpleNamespace(id='101')
        self.assertFalse(self.update())

    def test_ambiguous_selection_preserves_metadata(self):
        other = dict(self.book, narrators=['Other'], _vocalismeta_slug='other')
        self.g['remember_ljudboksarkivet_candidates'](self.media, [(99, self.book), (98, other)])
        self.assertTrue(self.update('Unrecognised title'))
        self.assertFalse(self.called)

    def test_explicit_rematch_overrides_saved_locator(self):
        self.g['save_ljudboksarkivet_selection'](self.media, self.identity, self.book)
        other = dict(self.book, narrators=['Other'], _vocalismeta_slug='other')
        self.g['remember_ljudboksarkivet_candidates'](self.media, [(99, other)])
        self.g['fetch_ljudboksarkivet_book'] = lambda slug: other
        self.update(self.g['ljudboksarkivet_result_label'](other))
        self.assertEqual(next(iter(self.store.values()))['selected'], 'other')


class Sidecars(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.audio = str(self.folder / 'book.m4b')
        self.g = agent()
        self.addCleanup(setattr, search_runtime.CONTEXT, 'sidecar', {})

    def load(self, document):
        (self.folder / 'vocalismeta.json').write_text(json.dumps(document))
        return sidecar_core.load_sidecar([self.audio])

    def test_absent_sidecar(self):
        self.assertEqual(sidecar_core.load_sidecar([self.audio]), {})

    def test_strict_schema_and_invalid_identity(self):
        for document in ({'schema_version': True}, {'schema_version': 1, 'typo': 2},
            {'schema_version': 1, 'identity': {'provider': 'isbn', 'id': '123'}},
            {'schema_version': 1, 'metadata': {'release_date': '2026-02-30'}},
            {'schema_version': 1, 'identity': {'provider': 'local', 'id': 'ignored'}},
            {'schema_version': 1, 'metadata': {'authors': [' ']}}):
            with self.subTest(document=document), self.assertRaises(ConfigError):
                self.load(document)

    def test_artwork_cannot_escape_book_directory(self):
        for path in ('../cover.jpg', '/tmp/cover.jpg', 'https://example.com/a.jpg'):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                self.load({'schema_version': 1, 'artwork': {'file': path}})

    def test_multipart_conflict_rejected(self):
        self.load({'schema_version': 1, 'metadata': {'title': 'First'}})
        second = self.folder / 'part2'
        second.mkdir()
        (second / 'vocalismeta.json').write_text(json.dumps({'schema_version': 1, 'metadata': {'title': 'Other'}}))
        with self.assertRaises(ConfigError):
            sidecar_core.load_sidecar([self.audio, str(second / 'track.mp3')])

    def test_oversize_rejected(self):
        (self.folder / 'vocalismeta.json').write_bytes(b' ' * (256 * 1024 + 1))
        with self.assertRaises(ConfigError):
            sidecar_core.load_sidecar([self.audio])

    def test_metadata_overrides_replace_old_contributors(self):
        search_runtime.CONTEXT.sidecar = self.load({'schema_version': 1, 'metadata': {
            'title': 'Correct title', 'authors': ['Correct Author'], 'narrators': ['Correct Reader'],
            'series': [{'title': 'Series', 'sequence': '2'}], 'genres': ['Fiction']}})
        m = SimpleNamespace(title='Old', title_sort='', moods=Tags(['Old Author',
            'Contributor-ID: narrator:audible:B000000001 = Old Reader']), styles=Tags(['Old Reader']), genres=Tags())
        self.g['apply_book_sidecar'](m)
        self.assertEqual(m.title, 'Correct title')
        self.assertEqual(m.styles, ['Correct Reader'])
        self.assertIn('Correct Author', m.moods)
        self.assertIn('Sequence: Series #2', m.moods)
        self.assertNotIn('Old Author', m.moods)
        self.assertFalse(any('Old Reader' in tag for tag in m.moods))
        self.assertEqual(m.genres, ['Fiction'])

    def test_explicit_isbn_search_preserves_portable_identity(self):
        search_runtime.CONTEXT.sidecar = self.load({'schema_version': 1,
            'identity': {'provider': 'isbn', 'id': '9780593135204'}})
        results = []
        self.g['append_search_result'] = lambda *args: results.append(args)
        self.assertTrue(self.g['sidecar_search_result'](None, None, 'Book', 'Author', 'en'))
        self.assertEqual(results[0][1], 'isbn:9780593135204')

    def test_unavailable_explicit_record_does_not_choose_other_book(self):
        search_runtime.CONTEXT.sidecar = self.load({'schema_version': 1,
            'identity': {'provider': 'audible', 'id': 'B000000001'}})
        self.g['fetch_product'] = lambda *args: None
        self.g['append_search_result'] = lambda *args: self.fail('unrelated fallback')
        self.assertTrue(self.g['sidecar_search_result'](None, None, 'Book', 'Author', 'en'))

    def test_valid_local_cover(self):
        import base64
        (self.folder / 'cover.jpg').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
        loaded = self.load({'schema_version': 1, 'artwork': {'file': 'cover.jpg'}})
        self.assertEqual(loaded['cover'], str((self.folder / 'cover.jpg').resolve()))


class Budgets(unittest.TestCase):
    def setUp(self):
        search_runtime.FAILURES.clear()
        search_runtime.CONTEXT.window = None
        search_runtime.CONTEXT.sidecar = {}
        self.addCleanup(setattr, search_runtime.CONTEXT, 'window', None)
        self.addCleanup(search_runtime.FAILURES.clear)
        self.g = agent()

    def test_request_and_time_limits(self):
        now = [0]
        w = search_runtime.SearchWindow(2, 10, clock=lambda: now[0])
        self.assertEqual(w.allowance(45), 10)
        now[0] = 9
        self.assertEqual(w.allowance(45), 1)
        self.assertIsNone(w.allowance(45))
        self.assertTrue(w.exhausted)
        w = search_runtime.SearchWindow(10, 10, clock=lambda: now[0])
        now[0] = 20
        self.assertIsNone(w.allowance(45))

    def test_json_retries_count_against_window(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            raise IOError('offline')
        self.g['HTTP'] = SimpleNamespace(Request=request)
        search_runtime.CONTEXT.window = search_runtime.SearchWindow(2, 90)
        status = {}
        with patch.object(search_runtime, 'pause'):
            self.assertEqual(self.g['request_json']('https://test.invalid/book', request_status=status), {})
        self.assertEqual(len(calls), 2)
        self.assertEqual(status['reason'], 'search_budget_exhausted')

    def test_text_respects_expired_window_without_http(self):
        self.g['HTTP'] = SimpleNamespace(Request=lambda *a, **k: self.fail('network after expiry'))
        search_runtime.CONTEXT.window = search_runtime.SearchWindow(1, 0)
        status = {}
        self.assertEqual(self.g['request_text']('https://test.invalid', request_status=status), '')
        self.assertEqual(status['reason'], 'search_budget_exhausted')

    def test_provider_cooldown_and_recovery(self):
        with patch.object(search_runtime.time, 'time', return_value=100):
            for unused in range(3):
                search_runtime.response('https://test.invalid/books', False)
            self.assertEqual(search_runtime.allowance('https://test.invalid/other', 45)[1], 'provider_cooldown')
            self.assertEqual(search_runtime.allowance('https://other.invalid', 45), (45, ''))
        with patch.object(search_runtime.time, 'time', return_value=161):
            self.assertEqual(search_runtime.allowance('https://test.invalid', 45), (45, ''))
        search_runtime.response('https://test.invalid', True)
        self.assertFalse(search_runtime.FAILURES)

    def test_context_restored_after_exception(self):
        previous = search_runtime.SearchWindow()
        search_runtime.CONTEXT.window = previous
        self.g['read_book_sidecar'] = lambda media: {}
        def fail(*args):
            raise ValueError('test')
        with self.assertRaises(ValueError):
            self.g['bounded_book_search'](fail)(None, None, None, 'en', False)
        self.assertIs(search_runtime.window(), previous)

    def test_search_windows_are_thread_local(self):
        search_runtime.CONTEXT.window = search_runtime.SearchWindow(1, 90)
        seen = []
        worker = threading.Thread(target=lambda: seen.append(search_runtime.window()))
        worker.start()
        worker.join()
        self.assertEqual(seen, [None])
        self.assertIsNotNone(search_runtime.window())

    def test_network_config_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'schema_version': 1, 'network': {
                'search_request_budget': 24, 'search_timeout_seconds': 60}}))
            values = load_config_file(str(path))['values']
            self.assertEqual(values['search_request_budget'], 24)
            self.assertEqual(values['search_timeout'], 60)

    def test_diagnostics_include_matching_evidence(self):
        logs = []
        self.g['log'] = lambda *args: logs.append(args)
        self.g['log_match_evidence']('audible', {'title': 'Book', 'authors': [{'name': 'Other'}],
            'runtime_length_min': 120}, ['Book'], 'Author', 100, 79, 80, 'us')
        rendered = logs[0][1] % logs[0][2:]
        self.assertIn('title_agreement=1.000', rendered)
        self.assertIn('runtime_difference_minutes=20.0', rendered)
        self.assertIn('reason=author_conflict', rendered)

class DiagnosticReport(unittest.TestCase):
    def test_report_cli_round_trips_quoted_title(self):
        import subprocess
        import sys
        from test_regressions import ROOT
        g = agent()
        records = []
        g['log'] = lambda level, fmt, *args: records.append(fmt % args)
        g['log_match_evidence']('audible', {'title': 'Book "A"', 'authors': [{'name': 'Author'}]},
            ['Book "A"'], 'Author', None, 100, 80, 'us')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'agent.log'
            path.write_text('\n'.join(records))
            command = [sys.executable, str(ROOT / 'scripts/explain-matches.py'), str(path)]
            human = subprocess.run(command, check=True, text=True, capture_output=True).stdout
            data = json.loads(subprocess.run(command + ['--json'], check=True, text=True, capture_output=True).stdout)
            self.assertIn('Book "A"', human)
            self.assertEqual(data[0]['title'], 'Book "A"')

    def test_explicit_sidecar_isbn_flows_through_album_search(self):
        from test_regressions import ROOT
        g = agent()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'vocalismeta.json'
            path.write_text(json.dumps({'schema_version': 1,
                'identity': {'provider': 'isbn', 'id': '9780593135204'},
                'metadata': {'title': 'Exact book', 'authors': ['Author']}}))
            g['HTTP'] = SimpleNamespace(Request=lambda *a, **k: self.fail('network should not run'))
            result = []
            g['append_search_result'] = lambda *args: result.append(args)
            media = SimpleNamespace(filename=str(Path(folder) / 'book.m4b'), album='Wrong scanner title', artist='Other')
            g['VocalisMetaAlbum']().search(None, media, 'en', False)
            self.assertEqual(result[0][1], 'isbn:9780593135204')
            self.assertEqual(result[0][2], '"Exact book" — Local metadata')

class LegacySelectionIdentity(unittest.TestCase):
    def test_legacy_local_identity_can_pin_provider_without_changing_guid(self):
        g = agent()
        g['Dict'] = Store()
        media = SimpleNamespace(id='500')
        book = {'title': 'Book', 'authors': ['Author'], 'isbn': '9780593135204',
                '_vocalismeta_slug': 'book'}
        identity = 'local:0123456789abcdef'
        g['save_ljudboksarkivet_selection'](media, identity, book)
        g['fetch_ljudboksarkivet_book'] = lambda slug: book
        updates = []
        updater = SimpleNamespace(update_ljudboksarkivet=lambda *args: updates.append(args))
        self.assertTrue(g['update_saved_ljudboksarkivet'](updater,
            SimpleNamespace(title='Book'), media, 'en', False, {}, 'local', '0123456789abcdef'))
        self.assertEqual(len(updates), 1)
        self.assertEqual(next(iter(g['Dict'].values()))['provider_identity'], 'isbn:9780593135204')
