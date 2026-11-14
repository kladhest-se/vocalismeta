# coding: utf-8
from __future__ import unicode_literals
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from test_regressions import ROOT, agent
from test_tools_and_artwork import metadata, PNG
from test_features import Store
import artwork_report_core
import metadata_tools_core
import search_runtime
import unicode_identity_core


class DoctorSettings(unittest.TestCase):
    def run_doctor(self, path):
        return subprocess.run([sys.executable, '-B', str(ROOT/'scripts/vocalismeta.py'),
            'doctor','--release-config',str(path),'--json'],text=True,capture_output=True)

    def test_missing_explicit_release_file_is_error(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_doctor(Path(folder)/'missing.json')
            self.assertEqual(result.returncode,1)
            self.assertEqual(json.loads(result.stdout)[0]['level'],'error')
            self.assertIn('does not exist',result.stdout)

    def test_directory_is_not_a_release_settings_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.run_doctor(folder).returncode,1)

    def test_valid_settings_can_warn_about_unset_token(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'release.json'
            path.write_text(json.dumps({'github':'https://github.com/org/project'}))
            result=self.run_doctor(path)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('"level": "error"',result.stdout)


class ArtworkReports(unittest.TestCase):
    def setUp(self):
        self.g=agent()
        self.g['Dict']=Store()
        self.g['read_book_sidecar']=lambda media: {}
        self.logs=[]
        self.g['log']=lambda level,fmt,*args:self.logs.append(fmt%args)
        self.m=metadata()
        self.m.posters=metadata_tools_core.Posters(self.m.posters)
        self.media=SimpleNamespace(id='123')
        self.g['Proxy']=SimpleNamespace(Media=lambda data,**kwargs: {'data':data})
        self.cover={'data':PNG,'path':'/book/cover.png','source':'fixture'}
        self.poster=self.g['poster_key'](self.cover)
        search_runtime.CONTEXT.preview=False
        search_runtime.CONTEXT.artwork_candidates=None
        self.addCleanup(setattr,search_runtime.CONTEXT,'preview',False)
        self.addCleanup(setattr,search_runtime.CONTEXT,'artwork_candidates',None)

    def update(self, data, preview):
        self.g['pref']=lambda key,default=None: (preview if key=='preview_updates' else True if key=='metadata_reports' else default)
        cover=dict(self.cover,data=data)
        def refresh(self_,target,media,lang,force):
            key=self.g['add_local_poster'](target,cover,0)
            target.posters.validate_keys([key])
        self.g['book_update_overrides'](refresh)(None,self.m,self.media,'en',False)
        return json.loads(next(line.split('METADATA_REPORT ',1)[1] for line in reversed(self.logs) if 'METADATA_REPORT ' in line))

    def test_same_key_same_content_is_unchanged(self):
        self.update(PNG,False)
        report=self.update(PNG,True)
        self.assertEqual(report['artwork_updates'][self.poster]['content_change'],'unchanged')
        self.assertNotIn('artwork_hashes',report['changes'])

    def test_same_key_changed_bytes_are_detected_without_preview_writes(self):
        self.update(PNG,False)
        original=dict(self.g['Dict'])
        before=dict(self.m.posters)
        # Bytes differ but decode identically: a valid PNG ancillary text chunk.
        import binascii
        payload=b'Comment\x00updated fixture'
        kind=b'tEXt'
        chunk=struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',binascii.crc32(kind+payload)&0xffffffff)
        changed=PNG[:-12]+chunk+PNG[-12:]
        report=self.update(changed,True)
        change=report['artwork_updates'][self.poster]
        self.assertEqual(change['content_change'],'changed')
        self.assertTrue(change['same_key'])
        self.assertEqual(change['before_sha256'],hashlib.sha256(PNG).hexdigest())
        self.assertEqual(change['after_sha256'],hashlib.sha256(changed).hexdigest())
        self.assertIn('artwork_hashes',report['changes'])
        self.assertEqual(self.g['Dict'],original)
        self.assertEqual(self.m.posters,before)

    def test_first_same_key_observation_has_unknown_baseline(self):
        self.m.posters={self.poster:object()}
        report=self.update(PNG,True)
        self.assertEqual(report['artwork_updates'][self.poster]['content_change'],'unknown')
        self.assertIsNone(report['artwork_updates'][self.poster]['before_sha256'])
        self.assertFalse(self.g['Dict'])

    def test_failed_candidate_does_not_create_observation(self):
        report=self.update(b'not an image',True)
        self.assertFalse(report['artwork_updates'])
        self.assertFalse(self.g['Dict'])

    def test_remote_same_url_observations_are_captured(self):
        self.g['HTTP']=SimpleNamespace(Request=lambda *args,**kwargs:SimpleNamespace(content=PNG))
        self.g['pref']=lambda key,default=None: True if key=='metadata_reports' else default
        def refresh(self_,target,*args):
            self.g['add_remote_poster'](target,['https://fixture.invalid/cover'],0)
        self.g['book_update_overrides'](refresh)(None,self.m,self.media,'en',False)
        self.assertTrue(any('hashes' in item for item in self.g['Dict'].values()))
        report=json.loads(self.logs[-1].split('METADATA_REPORT ',1)[1])
        self.assertEqual(report['artwork_updates']['https://fixture.invalid/cover']['content_change'],'added')

    def test_corrupt_saved_digest_is_not_trusted(self):
        self.assertEqual(artwork_report_core.known_hashes(['x'],{'x':[]} ),{'x':None})
        self.assertEqual(artwork_report_core.known_hashes(['x'],{'x':'wrong'}),{'x':None})

    def test_failed_update_restores_tracking_context(self):
        previous={}
        search_runtime.CONTEXT.artwork_candidates=previous
        def refresh(*args):raise RuntimeError('fixture')
        with self.assertRaises(RuntimeError):
            self.g['book_update_overrides'](refresh)(None,self.m,self.media,'en',False)
        self.assertIs(search_runtime.artwork_candidates(),previous)
