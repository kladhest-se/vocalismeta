# coding: utf-8
"""Published identity vectors; runnable independently on Python 2.7 or Python 3."""
from __future__ import unicode_literals
import io
import json
import os
import struct
import sys
import unittest

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,'VocalisMeta.bundle','Contents','Code'))
from identity_core import stable_fingerprint,local_identity
from client_metadata_core import name_fingerprint
try:
    character=unichr
except NameError:
    character=chr


def narrow(value):
    encoded=value.encode('utf-16-le')
    units=struct.unpack('<%dH'%(len(encoded)//2),encoded)
    return ''.join([character(unit) for unit in units])


class UnicodeIdentityVectors(unittest.TestCase):
    def setUp(self):
        path=os.path.join(ROOT,'client-contract','unicode-identity-vectors-v1.json')
        with io.open(path,'r',encoding='utf-8') as stream:
            self.vectors=json.load(stream)

    def test_raw_scalar_and_simulated_utf16_vectors(self):
        for item in self.vectors['raw_vectors']:
            self.assertEqual(stable_fingerprint(item['text']),item['expected'])
            self.assertEqual(stable_fingerprint(narrow(item['text'])),item['expected'])

    def test_narrator_vectors_across_storage_models(self):
        for item in self.vectors['contributor_vectors']:
            self.assertEqual(name_fingerprint(item['name']),item['expected'])
            self.assertEqual(name_fingerprint(narrow(item['name'])),item['expected'])

    def test_local_identity_vectors(self):
        for item in self.vectors['local_vectors']:
            self.assertEqual(local_identity(item['title'],item['author'],item['duration'],item['language']),item['expected'])
            self.assertEqual(local_identity(narrow(item['title']),narrow(item['author']),item['duration'],item['language']),item['expected'])

    def test_existing_normalization_semantics_are_preserved(self):
        self.assertNotEqual(name_fingerprint('René'),name_fingerprint('Rene\u0301'))
        vectors=self.vectors['local_vectors']
        self.assertEqual(vectors[0]['expected'],vectors[1]['expected'])
        self.assertEqual(name_fingerprint('Ray Porter'),'9303478f4aa8e7a9')


if __name__=='__main__':
    unittest.main()
