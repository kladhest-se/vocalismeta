import base64
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_regressions import ROOT, agent, Tags
from test_features import Store
import artwork_core
import local_artwork
import embedded_artwork
import multipart_core
import metadata_tools_core
import search_runtime
from sidecar_core import load_sidecar

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


def metadata():
    return SimpleNamespace(id='B000000001_us', title='Old', title_sort='Old', summary='Summary',
        studio='Publisher', rating=7.0, originally_available_at=None, genres=Tags(['Fiction']),
        styles=Tags(['Reader']), moods=Tags(['Author']), posters={'old-poster': object()})


class Multipart(unittest.TestCase):
    def test_conflicting_parts_report_each_field(self):
        records = [('a.mp3', {'asin':'B000000001', 'isbns':['9780593135204'], 'language':'sv', 'series':'A', 'series_sequence':'1'}),
                   ('b.mp3', {'asin':'B000000002', 'isbns':['9780140328721'], 'language':'en', 'series':'B', 'series_sequence':'2'})]
        self.assertEqual({r['field'] for r in multipart_core.conflicts(records)},
                         {'asin','isbns','language','series','series_sequence'})

    def test_equivalent_isbn_missing_tags_and_language_aliases(self):
        records = [('a', {'isbns':['0140328726'], 'language':'eng', 'series_sequence':'2.0'}),
                   ('b', {'isbns':['9780140328721'], 'language':'en-US', 'series_sequence':'2'}), ('c', {})]
        self.assertEqual(multipart_core.conflicts(records), [])

    def test_shared_isbn_is_not_a_conflict(self):
        self.assertFalse(multipart_core.conflicts([('a', {'isbns':['9780593135204','9780140328721']}),
                                                 ('b', {'isbns':['9780140328721']})]))

    def test_agent_does_not_merge_conflicting_identity(self):
        g = agent()
        g['read_embedded_metadata'] = lambda p: {'asin': 'B000000001' if p == 'a' else 'B000000002'}
        result = g['embedded_identity_from_paths'](['a','b'])
        self.assertIsNone(result['asin'])
        self.assertEqual(result['conflicts'][0]['field'], 'asin')

    def test_automatic_search_stops_before_provider_requests(self):
        g = agent()
        g['embedded_identity_from_paths'] = lambda p: {'conflicts':[{'field':'asin'}]}
        g['fetch_products'] = lambda *a: self.fail('must not query on conflicting tags')
        results = []
        g['append_search_result'] = lambda *a: results.append(a)
        g['VocalisMetaAlbum']().search(None, SimpleNamespace(album='Book', artist='Author'), 'en', False)
        self.assertFalse(results)


class Preview(unittest.TestCase):
    def setUp(self):
        search_runtime.CONTEXT.preview = False
        search_runtime.CONTEXT.sidecar = {}
        self.addCleanup(setattr, search_runtime.CONTEXT, 'preview', False)
        self.addCleanup(setattr, search_runtime.CONTEXT, 'sidecar', {})

    def test_preview_isolates_scalars_lists_posters_and_persistent_selection(self):
        g = agent()
        g['Dict'] = Store()
        g['pref'] = lambda key, default=None: True if key == 'preview_updates' else default
        g['read_book_sidecar'] = lambda media: {}
        records = []
        g['log'] = lambda level, fmt, *args: records.append(fmt % args)
        before = metadata()
        original = metadata_tools_core.snapshot(before)
        def update(self, draft, media, lang, force):
            draft.title = 'New'
            draft.styles.clear();draft.styles.add('New Reader')
            draft.posters.clear();draft.posters['new-poster'] = object()
            g['selection_write']('test', {'selected':'should-not-save'})
        g['book_update_overrides'](update)(None, before, SimpleNamespace(id='1'), 'en', False)
        self.assertEqual(metadata_tools_core.snapshot(before), original)
        self.assertFalse(g['Dict'])
        report = json.loads(next(line.split('METADATA_REPORT ',1)[1] for line in records if 'METADATA_REPORT ' in line))
        self.assertTrue(report['preview'])
        self.assertEqual(report['changes']['title'], {'before':'Old', 'after':'New'})
        self.assertIn('styles', report['changes'])
        self.assertFalse(search_runtime.preview())

    def test_apply_mode_mutates_metadata_and_can_report(self):
        g = agent()
        g['pref'] = lambda key, default=None: True if key == 'metadata_reports' else default
        g['read_book_sidecar'] = lambda media: {}
        m = metadata()
        def update(self, target, *args): target.title = 'Applied'
        g['book_update_overrides'](update)(None, m, SimpleNamespace(id='1'), 'en', False)
        self.assertEqual(m.title, 'Applied')

    def test_exception_does_not_leak_preview_context(self):
        g = agent()
        g['pref'] = lambda key, default=None: True if key == 'preview_updates' else default
        g['read_book_sidecar'] = lambda media: {}
        def update(*args): raise RuntimeError('fixture')
        with self.assertRaises(RuntimeError):
            g['book_update_overrides'](update)(None, metadata(), None, 'en', False)
        self.assertFalse(search_runtime.preview())


class Artwork(unittest.TestCase):
    def test_png_structure_dimensions_and_crc(self):
        info = artwork_core.inspect_image(PNG)
        self.assertIsNotNone(info)
        self.assertEqual((info['width'],info['height']), (1,1))
        self.assertTrue(info['low_resolution'])
        self.assertIsNone(artwork_core.inspect_image(PNG[:-5]))
        self.assertIsNone(artwork_core.inspect_image(PNG[:35] + b'bad' + PNG[38:]))

    def test_fake_headers_rejected_at_every_entrypoint(self):
        for data in (b'\xff\xd8\xff'+b'\x00'*20, b'\x89PNG\r\n\x1a\n'+b'\x00'*20,
                     b'RIFF'+b'\x00'*4+b'WEBP'+b'\x00'*20):
            self.assertIsNone(artwork_core.inspect_image(data))
            self.assertIsNone(embedded_artwork.valid_cover(data,'fixture','book'))
            self.assertIsNone(local_artwork.read_cover({'data':data}))

    def test_png_fallback_is_explicit_without_decoder(self):
        with patch.object(artwork_core, 'DECODER', None):
            self.assertFalse(artwork_core.inspect_image(PNG)['decoded'])
            self.assertIsNone(artwork_core.inspect_image(PNG, require_decode=True))

    def test_size_and_aspect_limits(self):
        for dims in ((0,1),(10001,1),(6000,6000),(1000,100),(100,1000)):
            self.assertFalse(artwork_core.dimensions_ok(*dims))
        self.assertTrue(artwork_core.dimensions_ok(600,900))

    @unittest.skipIf(artwork_core.DECODER is None, 'Install requirements-dev.txt for decoder cases')
    def test_real_jpeg_png_webp_decode_and_truncation(self):
        for kind in ('JPEG','PNG','WEBP'):
            with self.subTest(kind=kind):
                image = artwork_core.DECODER.new('RGB',(300,400),'blue')
                stream = io.BytesIO();image.save(stream,format=kind)
                data = stream.getvalue()
                info = artwork_core.inspect_image(data, require_decode=True)
                self.assertTrue(info['decoded'])
                self.assertEqual((info['width'],info['height']), (300,400))
                self.assertIsNone(artwork_core.inspect_image(data[:len(data)//2], require_decode=True))

    def test_valid_cover_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cover.png';path.write_bytes(PNG)
            cover = local_artwork.inspect_cover(str(path))
            self.assertEqual(cover['width'],1)
            self.assertEqual(local_artwork.read_cover(cover),PNG)


class ToolsCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/vocalismeta.py')]+list(args),
                              text=True,capture_output=True)

    def test_doctor_valid_invalid_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)/'config.json'
            key = Path(folder)/'secret';key.write_text('private-fixture-secret')
            config.write_text(json.dumps({'schema_version':1, 'providers':{'google_books':{'api_key_file':'secret'}}}))
            good = self.run_cli('doctor','--config',str(config),'--json')
            self.assertEqual(good.returncode,0,good.stderr)
            self.assertNotIn('private-fixture-secret',good.stdout+good.stderr)
            config.write_text('{bad json')
            self.assertEqual(self.run_cli('doctor','--config',str(config)).returncode,1)

    def test_report_preview_and_export_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            before=metadata_tools_core.snapshot(metadata())
            after=dict(before,title='New',moods=['Author','Series: Saga','Sequence: Saga #2','Language: English'])
            a=base/'before.json';a.write_text(json.dumps(before))
            b=base/'after.json';b.write_text(json.dumps(after))
            preview=self.run_cli('preview','--before',str(a),'--after',str(b))
            report=json.loads(preview.stdout)
            self.assertEqual(report['changes']['title']['after'],'New')
            log=base/'agent.log';log.write_text('prefix METADATA_REPORT '+json.dumps(report)+'\n')
            reportfile=base/'report.json'
            result=self.run_cli('report','--log',str(log),'--output',str(reportfile))
            self.assertEqual(result.returncode,0,result.stderr)
            output=base/'vocalismeta.json'
            result=self.run_cli('export','--input',str(reportfile),'--output',str(output))
            self.assertEqual(result.returncode,0,result.stderr)
            sidecar=load_sidecar([str(base/'book.m4b')])
            self.assertEqual(sidecar['metadata']['title'],'New')
            self.assertEqual(sidecar['metadata']['series'][0]['sequence'],'2')
            self.assertEqual(sidecar['identity']['provider'],'audible')
            self.assertEqual(self.run_cli('export','--input',str(reportfile),'--output',str(output)).returncode,1)

    def test_export_single_album_xml_and_reject_entities(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'album.xml'
            path.write_text('<MediaContainer><Directory type="album" title="Book" guid="com.plexapp.agents.spokenmeta://librivox:123?lang=en"><Mood tag="Author"/><Style tag="Reader"/></Directory></MediaContainer>')
            out=Path(folder)/'vocalismeta.json'
            result=self.run_cli('export','--input',str(path),'--output',str(out))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(out.read_text())['identity'],{'provider':'librivox','id':'123'})
            path.write_text('<!DOCTYPE x [<!ENTITY x "secret">]><Directory type="album"/>')
            self.assertEqual(self.run_cli('export','--input',str(path),'--output','-').returncode,1)

    def test_export_does_not_invent_authors_from_reserved_moods(self):
        value=metadata_tools_core.export_sidecar({'id':'local:0123456789abcdef',
            'title':'Book','moods':['Work-ID: openlibrary:OL1W','Contributor-ID: author:audible:B000000001 = Person']})
        self.assertNotIn('authors',value['metadata'])
        self.assertNotIn('artwork',value)

    @unittest.skipIf(artwork_core.DECODER is None, 'Install Pillow for full doctor image checks')
    def test_doctor_rejects_corrupt_artwork(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cover.png';path.write_bytes(PNG[:-8])
            result=self.run_cli('doctor','--artwork',str(path))
            self.assertEqual(result.returncode,1)

class InvalidSnapshots(unittest.TestCase):
    def test_malformed_nested_records_rejected(self):
        for record in ({'after':[]}, {'title':['not text']}, {'moods':'not an array'}, {'moods':[None]}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                metadata_tools_core.export_sidecar(record)
