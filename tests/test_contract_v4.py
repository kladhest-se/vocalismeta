"""V4 publication, transport, cache and migration safeguards; no real networking."""
import base64
import copy
import datetime
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zlib
from test_regressions import ROOT, agent
from test_features import Store
from test_tools_and_artwork import metadata, PNG
import contract_v4_core as v4
import contract_v4_runtime
import metadata_tools_core
import search_runtime
from config_core import load_config_file

VECTORS=json.loads((ROOT/'client-contract/test-vectors-v4.json').read_text())['vectors']


class ContractV4Vectors(unittest.TestCase):
    def test_every_published_vector(self):
        for item in VECTORS:
            with self.subTest(item['name']):
                payload=v4.build(item['snapshot'],item['context'],item['previous'],item['profile'])
                self.assertEqual(payload,item['expected'])
                self.assertEqual(v4.decode(item['moods']),payload)
                self.assertEqual(v4.encode(payload),item['moods'])

    def test_published_plex_json_fixtures(self):
        folder=ROOT/'client-contract/fixtures/v4'
        for item in VECTORS:
            with self.subTest(item['name']):
                album=json.loads((folder/(item['name']+'.json')).read_text())['MediaContainer']['Metadata'][0]
                self.assertEqual(v4.decode([m['tag'] for m in album['Mood']]),item['expected'])
                self.assertEqual(v4.canonical_client_key(album['guid']),item['expected']['recording_key'])

    def test_plex_xml_transport(self):
        for path in (ROOT/'client-contract/fixtures/v4').glob('*.xml'):
            album=ET.fromstring(path.read_bytes()).find('Directory')
            payload=v4.decode([m.get('tag') for m in album.findall('Mood')])
            self.assertEqual(payload['recording_key'],v4.canonical_client_key(album.get('guid')))

    def test_metadata_and_artwork_have_separate_invalidation(self):
        cases={v['name']:v['expected'] for v in VECTORS}
        base=cases['fresh_recording']['revisions']
        self.assertEqual(base,cases['unchanged_refresh']['revisions'])
        self.assertEqual(base,cases['provider_unavailable_preserves_revisions']['revisions'])
        self.assertEqual(base,cases['unicode_and_plex_mood_order']['revisions'])
        changed=cases['same_key_artwork_replacement']['revisions']
        self.assertEqual(base['metadata'],changed['metadata'])
        self.assertNotEqual(base['artwork'],changed['artwork'])
        self.assertNotEqual(base['metadata'],cases['manual_override_and_series_clear']['revisions']['metadata'])

    def test_explicit_primary_and_all_exact_memberships(self):
        data=next(v['expected'] for v in VECTORS if v['name']=='exact_secondary_membership_without_invented_id')
        value=data['fields']['series']['value']
        primary=next(m for m in value['memberships'] if m['ref']==value['primary_ref'])
        self.assertEqual(primary['title'],'Saga')
        self.assertEqual(primary['sequence'],'3.5')
        self.assertEqual(primary['provider_id']['id'],'B000SER001')
        accent=next(m for m in value['memberships'] if m['title']=='Sàga')
        self.assertNotIn('provider_id',accent)
        self.assertEqual(len(value['memberships']),3)
        self.assertNotIn('total',value)

    def test_series_zero_and_fractional_positions(self):
        value=v4.series_relationships([{'title':'Saga','sequence':0},{'title':'Other','sequence':'2.50'}])
        self.assertEqual({m['sequence'] for m in value['memberships']},{'0','2.5'})

    def test_unknown_primary_is_not_guessed_from_mood_order(self):
        a=v4.mood_series(['Series: Z','Series: A'])
        b=v4.mood_series(['Series: A','Series: Z'])
        self.assertEqual(a,b)
        self.assertIsNone(a['primary_ref'])

    def test_privacy_and_no_diagnostic_projection(self):
        item=copy.deepcopy(VECTORS[0])
        item['snapshot'].update(filename='/private/books/book.m4b',token='never-publish-this',updatedAt=999999)
        item['context'].update(request_url='https://private.invalid/?token=private',score=0.98)
        payload=v4.build(item['snapshot'],item['context'],item['previous'],item['profile'])
        self.assertEqual(payload['revisions'],item['expected']['revisions'])
        raw=v4.canonical(payload)
        for secret in (b'/private/books',b'never-publish-this',b'private.invalid',b'0.98'):
            self.assertNotIn(secret,raw)

    def test_narrator_name_fallback_is_not_provider_authority(self):
        data=VECTORS[0]['expected']
        self.assertEqual(data['fields']['narrators']['identity_evidence'],'name_only')
        self.assertEqual(data['fields']['authors']['identity_evidence'],'provider_identifier')


class ContractV4Transport(unittest.TestCase):
    def setUp(self):
        self.payload=copy.deepcopy(VECTORS[0]['expected'])
        self.tags=list(VECTORS[0]['moods'])

    def test_order_independent_and_absence(self):
        self.assertEqual(v4.decode(list(reversed(self.tags))),self.payload)
        self.assertIsNone(v4.decode(['Author','Series: Saga']))

    def test_missing_duplicate_mixed_and_tampered_chunks(self):
        other=copy.deepcopy(self.payload);other['fields']['title']['value']='Other'
        other_tags=v4.encode(other)
        bad=[self.tags[:-1],self.tags+[self.tags[0]],self.tags+other_tags,
             [self.tags[0][:-1]+'!']+self.tags[1:],[v4.PREFIX+'bad'],
             [self.tags[0].replace('/'+str(len(self.tags))+':','/999:')]+self.tags[1:]]
        for tags in bad:
            with self.subTest(tags=tags),self.assertRaises(ValueError):v4.decode(tags)

    def test_bounded_expansion(self):
        raw=b' '* (v4.MAX_BYTES+1)
        encoded=base64.urlsafe_b64encode(zlib.compress(raw)).decode().rstrip('=')
        tag=v4.PREFIX+hashlib.sha256(raw).hexdigest()+':1/1:'+encoded
        with self.assertRaises(ValueError):v4.decode([tag])

    def test_invalid_states_primary_refs_and_strong_aliases_rejected(self):
        mutations=[]
        bad=copy.deepcopy(self.payload);bad['fields']['title']['state']='maybe';mutations.append(bad)
        bad=copy.deepcopy(self.payload);bad['fields']['series']['value']['primary_ref']='missing';mutations.append(bad)
        bad=copy.deepcopy(self.payload);bad['identity_upgrades']=[{
            'previous':'spokenmeta:audible:uk:B000000001','current':bad['recording_key'],
            'status':'verified_same_recording','evidence':['same_explicit_asin_and_region'],
            'reasons':[],'requires_client_confirmation':True}];mutations.append(bad)
        bad=copy.deepcopy(self.payload);bad['identity_upgrades']=[{
            'previous':'spokenmeta:local:0123456789abcdef','current':bad['recording_key'],
            'status':'verified_same_recording','evidence':['same_title'],'reasons':[],
            'requires_client_confirmation':False}];mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(ValueError):v4.encode(bad)

    def test_canonical_unicode_and_invalid_runtime_types(self):
        self.assertEqual(v4.canonical({'a':'Café'}),v4.canonical({'a':'Cafe\u0301'}))
        self.assertEqual(v4.canonical({'a':'😀'}),v4.canonical({'a':'\ud83d\ude00'}))
        with self.assertRaises(ValueError):v4.canonical({'float':0.95})


class ContractV4Migration(unittest.TestCase):
    def test_accepted_and_rejected_published_upgrades(self):
        for item in VECTORS:
            if item['name'].startswith(('verified_local','rejected_upgrade','title_work','strong_regional')):
                with self.subTest(item['name']):
                    upgrade=item['expected']['identity_upgrades'][0]
                    verified=item['name'].startswith('verified_local')
                    self.assertEqual(upgrade['status'],'verified_same_recording' if verified else 'review_required')
                    self.assertTrue(upgrade['requires_client_confirmation'])

    def test_later_conflict_revokes_verified_declaration(self):
        item=next(v for v in VECTORS if v['name']=='verified_local_to_audible')
        context=copy.deepcopy(item['context']);context['previous_profile']=item['profile']
        profile=dict(item['profile'],language='sv')
        result=v4.build(item['snapshot'],context,item['expected'],profile)
        self.assertEqual(result['identity_upgrades'][0]['status'],'review_required')
        self.assertIn('language_conflict',result['identity_upgrades'][0]['reasons'])

    def test_strong_id_and_isbn_alone_do_not_auto_alias(self):
        local='spokenmeta:local:0123456789abcdef'
        current='spokenmeta:isbn:9780593135204'
        result=v4.verify_upgrade(local,current,{'isbns':['9780593135204']},{'isbns':['9780593135204']},True)
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(v4.verify_upgrade(local,local,{},{}),None)


class ContractV4Agent(unittest.TestCase):
    def setUp(self):
        self.g=agent();self.g['Dict']=Store();self.enabled=True;self.preview=False
        self.g['pref']=lambda key,default=None: {'store_client_contract_v4':self.enabled,
            'openlibrary_enabled':False,'googlebooks_enabled':False,'preview_updates':self.preview}.get(key,default)
        self.g['read_book_sidecar']=lambda media:{}
        self.g['embedded_identity_from_paths']=lambda paths: self.embedded()
        self.g['Datetime']=SimpleNamespace(ParseDate=lambda value:datetime.datetime.strptime(value,'%Y-%m-%d'))
        self.g['enrich_and_apply_book_artwork']=lambda *args:None
        self.product={'asin':'B000000001','title':'Book','authors':[{'name':'Author'}],
            'narrators':[{'name':'Reader'}],'series':[{'title':'Saga','sequence':'3.5','asin':'B000SER001'}],
            'language':'english','release_date':'2020-01-01','runtime_length_min':120}
        self.available=True
        self.g['fetch_product']=lambda *args:self.product if self.available else None
        self.m=metadata();self.m.posters=metadata_tools_core.Posters()
        self.media=SimpleNamespace(id='101',duration=7200000,album='Book')
        search_runtime.CONTEXT.contract_v4=None
        self.addCleanup(setattr,search_runtime.CONTEXT,'contract_v4',None)

    def embedded(self):
        value={'authors':[],'narrators':[],'isbns':[],'language':None,'abridged':None,'series':None}
        contract_v4_runtime.embedded(value)
        return value

    def update(self):
        self.g['VocalisMetaAlbum']().update(self.m,self.media,'en',False)
        return v4.decode(self.m.moods)

    def test_emission_is_disabled_by_default_and_does_not_leak_authors(self):
        self.enabled=False
        self.assertIsNone(self.update())
        self.assertFalse(any(tag.startswith(v4.PREFIX) for tag in self.m.moods))
        self.assertFalse(self.g['existing_relationship_metadata']([v4.PREFIX+'invalid'])['authors'])

    def test_actual_update_has_fresh_field_sources_and_explicit_primary(self):
        data=self.update()
        self.assertEqual(data['fields']['title']['provenance']['source'],'audible')
        self.assertEqual(data['fields']['recording_date']['provenance']['date_kind'],'recording_release')
        self.assertIsNotNone(data['fields']['series']['value']['primary_ref'])
        self.assertEqual(data['recording_key'],'spokenmeta:audible:us:B000000001')
        self.assertNotIn(v4.PREFIX,self.g['existing_relationship_metadata'](self.m.moods)['authors'])

    def test_unchanged_and_failed_exact_provider_lookup(self):
        first=self.update()
        self.assertEqual(first['revisions'],self.update()['revisions'])
        self.available=False
        # A not-found/unavailable exact lookup is a preservation case, not a clear.
        old_fetch=self.g['fetch_product']
        def failed(*args):
            contract_v4_runtime.fail()
            return old_fetch(*args)
        self.g['fetch_product']=failed
        failed=self.update()
        self.assertEqual(first['revisions'],failed['revisions'])
        self.assertEqual(failed['fields']['title']['state'],'unavailable')
        self.assertTrue(failed['fields']['title']['stale'])
        self.assertEqual(failed['fields']['title']['value'],'Book')

    def test_preview_does_not_publish_or_persist_v4(self):
        self.preview=True
        before=list(self.m.moods)
        self.update()
        self.assertEqual(list(self.m.moods),before)
        self.assertFalse(self.g['Dict'])

    def test_disable_v4_removes_owned_tags_and_preserves_legacy_metadata(self):
        self.update();self.enabled=False
        self.update()
        self.assertFalse(any(tag.startswith(v4.PREFIX) for tag in self.m.moods))
        self.assertIn('Author',self.m.moods)
        self.assertIn('Series: Saga',self.m.moods)

    def test_v4_configuration_defaults_and_opt_in(self):
        prefs=json.loads((ROOT/'VocalisMeta.bundle/Contents/DefaultPrefs.json').read_text())
        pref=next(v for v in prefs if v['id']=='store_client_contract_v4')
        self.assertEqual(pref['default'],'false')

class AdditionalV4Boundaries(unittest.TestCase):
    def test_all_published_negative_vectors(self):
        import copy,base64,hashlib,zlib
        data=json.loads((ROOT/'client-contract/test-vectors-v4.json').read_text())
        base=next(v for v in data['vectors'] if v['name']=='fresh_recording')
        def unchecked(payload):
            raw=v4.canonical(payload)
            encoded=base64.urlsafe_b64encode(zlib.compress(raw)).decode().rstrip('=')
            count=(len(encoded)+v4.CHUNK_SIZE-1)//v4.CHUNK_SIZE
            return [v4.PREFIX+'%s:%d/%d:%s'%(hashlib.sha256(raw).hexdigest(),i+1,count,
                encoded[i*v4.CHUNK_SIZE:(i+1)*v4.CHUNK_SIZE]) for i in range(count)]
        for item in data['invalid_transport_vectors']:
            with self.subTest(item['name']):
                tags=list(base['moods']);kind=item['mutation']
                if kind=='remove_last':tags=tags[:-1]
                elif kind=='duplicate_first':tags.append(tags[0])
                elif kind=='invalid_character':tags[0]=tags[0][:-1]+'!'
                elif kind=='append_unchanged_other_payload':
                    other=copy.deepcopy(base['expected']);other['fields']['title']['value']='Other'
                    tags+=unchecked(other)
                elif kind=='missing_primary_ref':
                    bad=copy.deepcopy(base['expected']);bad['fields']['series']['value']['primary_ref']='missing'
                    tags=unchecked(bad)
                elif kind=='verified_strong_to_strong':
                    bad=copy.deepcopy(base['expected']);bad['identity_upgrades']=[{
                        'previous':'spokenmeta:audible:uk:B000000001','current':bad['recording_key'],
                        'status':'verified_same_recording','evidence':['same_explicit_asin_and_region'],
                        'reasons':[],'requires_client_confirmation':True}];tags=unchecked(bad)
                else:self.fail('Unexecuted published negative vector')
                with self.assertRaises(ValueError):v4.decode(tags)

    def test_legacy_response_and_scalar_set_order(self):
        path=ROOT/'client-contract/fixtures/v4/disabled_legacy_response.json'
        album=json.loads(path.read_text())['MediaContainer']['Metadata'][0]
        self.assertIsNone(v4.decode([m['tag'] for m in album['Mood']]))
        self.assertEqual(v4.exact_set(['😀','\ud83d\ude00','\ue000']),['😀','\ue000'])
        with self.assertRaises(ValueError):v4.canonical({'é':'non-ASCII schema key'})

class V4AgentInteractions(unittest.TestCase):
    setUp=ContractV4Agent.setUp
    embedded=ContractV4Agent.embedded
    update=ContractV4Agent.update
    def test_same_key_primary_artwork_bytes_change_only_artwork_revision(self):
        self.g['Proxy']=SimpleNamespace(Media=lambda body,**kwargs:object())
        body=[PNG]
        def artwork(target,*args):
            key=self.g['add_local_poster'](target,{'path':'cover.png','data':body[0]},0)
            target.posters.validate_keys([key])
        self.g['enrich_and_apply_book_artwork']=artwork
        first=self.update()
        text=b'Comment\x00new image input'
        import binascii
        chunk=struct.pack('>I',len(text))+b'tEXt'+text+struct.pack('>I',binascii.crc32(b'tEXt'+text)&0xffffffff)
        body[0]=PNG[:-12]+chunk+PNG[-12:]
        second=self.update()
        self.assertEqual(first['revisions']['metadata'],second['revisions']['metadata'])
        self.assertNotEqual(first['revisions']['artwork'],second['revisions']['artwork'])

    def test_manual_field_provenance_is_separate_from_overall_match(self):
        self.update()
        self.g['read_book_sidecar']=lambda media:{'metadata':{'title':'Manual title','series':[]}}
        value=self.update()
        self.assertEqual(value['fields']['title']['provenance'],{'source':'manual','evidence':'manual_override'})
        self.assertEqual(value['fields']['series']['state'],'cleared')
        self.assertNotEqual(value['match']['method'],'manual_override')

    def test_disabled_namespaces_publish_explicit_clears(self):
        self.m.moods.add('Work-ID: openlibrary:OL123W')
        self.m.moods.add('Work-Published: 1900')
        self.update()
        old=self.g['pref']
        self.g['pref']=lambda key,default=None:False if key in ('store_work_identity_as_mood','store_extended_player_metadata') else old(key,default)
        value=self.update()
        for field in ('work','work_publication','contributors'):
            self.assertEqual(value['fields'][field]['state'],'cleared')
        self.assertIn('extended_metadata',value['cleared_namespaces'])

    def test_real_local_to_provider_transition_uses_stored_explicit_evidence(self):
        self.media.filename='/books/Book [ASIN B000000001].m4b'
        self.m.id='local:0123456789abcdef'
        previous=self.update()
        self.assertEqual(previous['recording_key'],'spokenmeta:local:0123456789abcdef')
        # Simulates Fix Match changing Plex's ID, not an agent-side GUID rewrite.
        self.m.id='B000000001_us'
        current=self.update()
        self.assertEqual(current['identity_upgrades'][0]['status'],'verified_same_recording')
        self.assertEqual(self.m.id,'B000000001_us')

class V4AdditionalSafeguards(unittest.TestCase):
    def test_reference_consumer_binds_guid(self):
        item=VECTORS[0]
        self.assertEqual(v4.decode_for_recording(item['moods'],'com.plexapp.agents.spokenmeta://B000000001_us?lang=en'),item['expected'])
        with self.assertRaises(ValueError):v4.decode_for_recording(item['moods'],'B000000009_us')

    def test_series_malformed_provider_shapes_are_ignored(self):
        self.assertEqual(v4.series_relationships({'not':'an array'})['memberships'],[])
        self.assertEqual(v4.series_relationships([None,[],{'title':'Saga','sequence':'0.5'}])['memberships'][0]['sequence'],'0.5')

    def test_same_name_in_different_regions_is_not_equivalence(self):
        a=v4.series_relationships([{'title':'Saga','asin':'B000SER001'}],'audible','us')
        b=v4.series_relationships([{'title':'Saga','asin':'B000SER001'}],'audible','uk')
        self.assertNotEqual(a['primary_ref'],b['primary_ref'])

    def test_field_availability_is_not_a_metadata_revision_clock(self):
        base=VECTORS[0]['expected']
        failed=next(v['expected'] for v in VECTORS if v['name']=='provider_unavailable_preserves_revisions')
        self.assertEqual(base['revisions'],failed['revisions'])
        self.assertNotEqual(base['fields']['title']['state'],failed['fields']['title']['state'])
        self.assertTrue(failed['fields']['title']['stale'])

    def test_v3_name_source_display_does_not_hide_provider_ids(self):
        self.assertTrue(v4.any_provider_ids(['Contributor-ID: narrator:audible:B000000001 = A:name:Reader']))

class V4LocaleAndExport(unittest.TestCase):
    def test_known_regional_language_conflicts_require_review(self):
        before={'asin':'B000000001','region':'us','language':'en','language_tag':'en-us'}
        after=dict(before,language_tag='en-gb')
        declaration=v4.verify_upgrade('spokenmeta:local:0123456789abcdef',
            'spokenmeta:audible:us:B000000001',before,after,True)
        self.assertEqual(declaration['status'],'review_required')
        self.assertIn('language_tag_conflict',declaration['reasons'])

    def test_v4_xml_does_not_leak_chunk_tags_into_exported_authors(self):
        import subprocess,sys,tempfile
        path=ROOT/'client-contract/fixtures/v4/fresh_recording.xml'
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'vocalismeta.json'
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/vocalismeta.py'),
                'export','--input',str(path),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(output.read_text())
            self.assertEqual(value['metadata']['authors'],['Fixture Author'])
            self.assertFalse(any(name.startswith(v4.PREFIX) for name in value['metadata']['authors']))

class V4SuppliedSeriesIdentifiers(unittest.TestCase):
    def test_swedish_link_ids_are_real_provider_fields_and_legacy_is_unchanged(self):
        import ljudboksarkivet_core as lba
        html='<a href="/bokserie/saga-one">Saga · del 3,5</a><a href="/bokserie/saga-two">saga · del 2</a>'
        legacy=lba.series_entries(html)
        self.assertEqual(legacy,[{'title':'Saga','sequence':'3.5'}])
        raw=lba.series_entries(html,exact=True)
        relationships=v4.series_relationships(raw,'ljudboksarkivet')
        self.assertEqual(len(relationships['memberships']),2)
        self.assertEqual({m['provider_id']['id'] for m in relationships['memberships']},{'saga-one','saga-two'})

    def test_external_or_absent_link_does_not_invent_provider_identity(self):
        import ljudboksarkivet_core as lba
        raw=lba.series_entries('<a href="https://unrelated.invalid/bokserie/saga">Saga del 1</a>',exact=True)
        membership=v4.series_relationships(raw,'ljudboksarkivet')['memberships'][0]
        self.assertNotIn('provider_id',membership)

class V4UnavailableAndCapacity(unittest.TestCase):
    def test_malformed_enrichment_envelope_marks_unavailable(self):
        g=agent();search_runtime.CONTEXT.contract_v4={}
        try:
            g['request_json']=lambda *args,**kwargs:{'docs':'not a list'}
            self.assertEqual(g['fetch_openlibrary_documents']('Book'),[])
            self.assertTrue(contract_v4_runtime.current()['failed'])
        finally:
            search_runtime.CONTEXT.contract_v4=None

    def test_enrichment_budget_exhaustion_is_not_a_negative_fact(self):
        g=agent();search_runtime.CONTEXT.contract_v4={}
        try:
            budget=SimpleNamespace(take=lambda source:False)
            self.assertFalse(g['use_enrichment_request'](budget,'Open Library'))
            self.assertTrue(contract_v4_runtime.current()['failed'])
        finally:
            search_runtime.CONTEXT.contract_v4=None

    def test_oversized_publication_does_not_reemit_a_stale_old_key(self):
        g=agent();g['Dict']=Store()
        search_runtime.CONTEXT.contract_v4={'evidence':{},'profile':{}}
        g['pref']=lambda key,default=None:default
        m=metadata();m.title='x'*(v4.MAX_BYTES+1)
        m.moods.extend(VECTORS[0]['moods'])
        previous={'payload':VECTORS[0]['expected'],'profile':{}}
        try:
            g['publish_v4'](m,SimpleNamespace(id='1'),previous,'fixture')
            self.assertIsNone(v4.decode(m.moods))
            self.assertFalse(g['Dict'])
            self.assertEqual(m.title,'x'*(v4.MAX_BYTES+1))
        finally:
            search_runtime.CONTEXT.contract_v4=None
