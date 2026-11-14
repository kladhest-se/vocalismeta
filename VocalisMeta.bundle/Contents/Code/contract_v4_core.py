# coding: utf-8
"""Optional v4 publication and strict reference transport, Python 2.7 compatible."""
from __future__ import unicode_literals
import base64
import binascii
import hashlib
import json
import re
import struct
import unicodedata
import zlib
from config_core import TEXT_TYPES, INTEGER_TYPES
from audible_core import to_text, sequence_label, valid_asin
from identity_core import canonical_client_key, client_identity
from multipart_core import language_key
from client_metadata_core import valid_contributor_id
from openlibrary_core import normalize_work_id

PREFIX = 'VocalisMeta-v4: '
MAX_BYTES = 16384
CHUNK_SIZE = 384
MAX_CHUNKS = 64
STATES = ('known', 'unknown', 'unavailable', 'cleared')
SOURCES = ('audible','librivox','ljudboksarkivet','openlibrary','googlebooks',
           'embedded_tags','embedded_artwork','local_artwork','remote_provider',
           'manual','plex','unknown')
EVIDENCE = ('explicit_identifier','provider_match','isbn_match','embedded_tags',
            'manual_override','name_only','provider_identifier','local_file','unknown')


def normalized(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, INTEGER_TYPES):
        return value
    if isinstance(value, TEXT_TYPES):
        # JSON joins valid UTF-16 surrogate pairs on wide builds without changing
        # the canonical escaped representation used by narrow Python 2 builds.
        value=json.loads(json.dumps(value,ensure_ascii=True))
        return unicodedata.normalize('NFC', value)
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if not isinstance(key, TEXT_TYPES):
                raise ValueError('v4 object keys must be text')
            key = normalized(key)
            try:
                key.encode('ascii')
            except UnicodeError:
                raise ValueError('v4 schema object keys must be ASCII')
            if key in output:
                raise ValueError('v4 canonical keys collide')
            output[key] = normalized(item)
        return output
    raise ValueError('v4 canonical values must not contain floats or runtime objects')


def canonical(value):
    return json.dumps(normalized(value), ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(value):
    return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()


def exact_set(values):
    result = []
    for value in values or []:
        value = normalized(to_text(value))
        if value and value not in result:
            result.append(value)
    return sorted(result,key=lambda value:canonical(value))


def series_relationships(entries, source='unknown', scope=''):
    members = []
    seen = set()
    entries=entries if isinstance(entries,(list,tuple)) else []
    for entry in entries:
        if not isinstance(entry,dict):
            continue
        title = to_text(entry.get('title') or entry.get('name')).strip()
        if not title:
            continue
        item = {'title': normalized(title), 'sequence': sequence_label(
            entry.get('sequence') if entry.get('sequence') is not None else entry.get('position') or '')}
        supplied = to_text(entry.get('asin')).strip().upper()
        if source == 'audible' and valid_asin(supplied):
            item['provider_id'] = {'source':'audible','scope':scope,'id':supplied}
        slug=to_text(entry.get('provider_slug'))
        if source=='ljudboksarkivet' and re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$',slug):
            item['provider_id']={'source':'ljudboksarkivet','scope':'','id':slug}
        item['ref'] = 'relationship:' + hashlib.sha256(canonical(item)).hexdigest()
        if item['ref'] not in seen:
            seen.add(item['ref'])
            members.append(item)
    primary = members[0]['ref'] if members else None
    return {'primary_ref':primary, 'memberships':sorted(members,key=lambda item:item['ref'])}


def mood_series(moods):
    names, positions = [], {}
    for value in moods:
        if value.startswith('Series: '):
            names.append(value[8:])
        elif value.startswith('Sequence: ') and ' #' in value:
            title, position = value[10:].rsplit(' #',1)
            positions[title] = position
    result = series_relationships([{'title':name,'sequence':positions.get(name,'')} for name in sorted(set(names))])
    result['primary_ref'] = None  # returned Mood order is never evidence of primacy
    return result


def valid_person_tag(value):
    if not value.startswith('Contributor-ID: ') or ' = ' not in value:
        return False
    identifier,name=value[16:].split(' = ',1)
    parts=identifier.split(':')
    if len(parts)!=3 or parts[0] not in ('author','narrator') or not name:
        return False
    return bool(valid_contributor_id(parts[1],parts[2]) and (parts[1]!='name' or parts[0]=='narrator'))


def published_values(snapshot):
    moods = [to_text(v) for v in snapshot.get('moods',[]) if not to_text(v).startswith(PREFIX)]
    reserved = ('Series: ','Sequence: ','Language: ','Edition: ','Work-ID: ','Contributor-ID: ',
                'Work-Published: ','Production: ','Rating-Source: ','Rating-Count: ')
    values = {'title':snapshot.get('title') or None,
        'authors':exact_set([v for v in moods if not v.startswith(reserved)]),
        'narrators':exact_set(snapshot.get('styles')), 'series':mood_series(moods),
        'recording_date':snapshot.get('originally_available_at'), 'language':None,
        'edition':None,'work':None,'work_publication':None,
        'contributors':exact_set([v for v in moods if valid_person_tag(v)])}
    for prefix,field in (('Language: ','language'),('Edition: ','edition'),
                         ('Work-ID: ','work'),('Work-Published: ','work_publication')):
        candidates = exact_set([v[len(prefix):] for v in moods if v.startswith(prefix)])
        if field=='work':
            candidates=[v for v in candidates if v.startswith('openlibrary:') and normalize_work_id(v.split(':',1)[1])]
        if field=='work_publication':
            candidates=[v for v in candidates if re.match(r'^[1-9][0-9]{0,3}$',v)]
        if candidates:
            values[field] = candidates[0]
    return values


def empty_value(value):
    return value is None or value == '' or value == [] or (
        isinstance(value,dict) and 'memberships' in value and not value['memberships'])


def value_equal(left, right):
    return canonical(left) == canonical(right)


def field_state(field, value, previous, context):
    clearing = context.get('cleared',{}).get(field)
    if clearing:
        return {'state':'cleared','value':value,'stale':False,'reason':clearing,
                'provenance':{'source':'manual' if clearing=='manual_clear' else 'unknown',
                              'evidence':'manual_override' if clearing=='manual_clear' else 'unknown'}}
    candidates = context.get('evidence',{}).get(field,[])
    for candidate in reversed(candidates):
        if value_equal(candidate['value'],value):
            result={'state':'unknown' if empty_value(value) else 'known','value':value,
                    'stale':False,'provenance':{'source':candidate['source'],
                                              'evidence':candidate['evidence']}}
            if candidate.get('date_kind'):
                result['provenance']['date_kind']=candidate['date_kind']
            return result
    old = (previous or {}).get('fields',{}).get(field,{})
    if old.get('state')=='cleared' and empty_value(value):
        return dict(old)
    if not empty_value(value) and old and value_equal(old.get('value'),value):
        result = dict(old)
        unavailable = bool(context.get('failed'))
        result.update(state='unavailable' if unavailable else 'known', value=value, stale=True,
                      reason='lookup_unavailable' if unavailable else 'retained_previous_value')
        return result
    return {'state':('unavailable' if context.get('failed') else 'unknown') if empty_value(value) else 'known',
            'value':value,'stale':bool(context.get('failed') and not empty_value(value)),
            'reason':'lookup_unavailable' if context.get('failed') else 'source_not_observed',
            'provenance':{'source':'unknown','evidence':'unknown'}}


def compatible_profiles(before, after):
    reasons = []
    for field in ('language','language_tag','abridged'):
        a,b = before.get(field),after.get(field)
        if a is not None and b is not None and a != b:
            reasons.append(field+'_conflict')
    for field in ('asin','region','librivox_id'):
        a,b = before.get(field),after.get(field)
        if a and b and a != b:
            reasons.append(field+'_conflict')
    a,b = before.get('duration_ms'),after.get('duration_ms')
    if a and b and abs(a-b) > max(60000, int(min(a,b)*0.005)):
        reasons.append('runtime_conflict')
    a,b = before.get('narrators'),after.get('narrators')
    if a and b and a != b:
        reasons.append('narrator_conflict')
    if before.get('conflicting_tags') or after.get('conflicting_tags'):
        reasons.append('conflicting_recording_tags')
    return sorted(reasons)


def verify_upgrade(previous_key, current_key, before, after, confirmed=False):
    if not previous_key or previous_key == current_key:
        return None
    result = {'previous':previous_key,'current':current_key,'status':'review_required',
              'evidence':[], 'requires_client_confirmation':True}
    if not previous_key.startswith('spokenmeta:local:'):
        result['reasons'] = ['strong_identity_conflict']
        return result
    reasons = compatible_profiles(before,after)
    if reasons:
        result['reasons'] = reasons
        return result
    proof = None
    if current_key.startswith('spokenmeta:audible:'):
        parts = current_key.split(':')
        if (before.get('asin') == after.get('asin') == parts[-1] and
                before.get('region') == after.get('region') == parts[-2]):
            proof = 'same_explicit_asin_and_region'
    elif current_key.startswith('spokenmeta:librivox:'):
        if before.get('librivox_id') == after.get('librivox_id') == current_key.split(':')[-1]:
            proof = 'same_explicit_librivox_project'
    if proof and confirmed:
        result.update(status='verified_same_recording',evidence=[proof],reasons=[])
    else:
        result['reasons'] = ['insufficient_recording_evidence']
    return result


def build(snapshot, context, previous=None, profile=None):
    previous = previous or {}
    values = published_values(snapshot)
    selected = context.get('series')
    if selected is not None:
        values['series'] = selected
    elif previous.get('fields',{}).get('series'):
        old = previous['fields']['series'].get('value')
        # Preserve explicit primacy only when every old exact membership survives.
        plain = values['series']['memberships']
        before_names = sorted([(v['title'],v['sequence']) for v in old.get('memberships',[])]) if old else []
        after_names = sorted([(v['title'],v['sequence']) for v in plain])
        if before_names == after_names:
            values['series'] = old
    for field in context.get('cleared',{}):
        if field in values:
            values[field] = {'primary_ref':None,'memberships':[]} if field=='series' else [] if field in ('authors','narrators','contributors') else None
    fields = {}
    for field,value in values.items():
        fields[field] = field_state(field,value,previous,context)
    for name in ('authors','narrators'):
        ids = [v for v in values['contributors'] if v.startswith('Contributor-ID: '+('author' if name=='authors' else 'narrator')+':')]
        fields[name]['identity_evidence'] = ('provider_identifier' if any_provider_ids(ids)
                                          else 'name_only' if ids else 'unknown')
    accepted = context.get('artwork')
    old_revision = previous.get('revisions',{}).get('artwork')
    artwork_revision = 'sha256:'+accepted['sha256'] if accepted else old_revision
    if accepted:
        fields['artwork'] = {'state':'known','value':artwork_revision,'stale':False,
                             'provenance':{'source':accepted['source'],'evidence':accepted['evidence']}}
    else:
        old_artwork = previous.get('fields',{}).get('artwork') or {}
        fields['artwork'] = dict(old_artwork) if old_artwork else {
            'provenance':{'source':'unknown','evidence':'unknown'}}
        fields['artwork'].update(state='unavailable' if (context.get('artwork_failed') or context.get('failed')) else ('known' if artwork_revision else 'unknown'),
            value=artwork_revision,stale=bool(artwork_revision),
            reason='lookup_unavailable' if (context.get('artwork_failed') or context.get('failed')) else 'no_new_accepted_image')
    # Health/provenance changes do not churn semantic metadata revisions.
    projection = {field:state['value'] for field,state in fields.items() if field!='artwork'}
    projection['cleared_fields'] = sorted([field for field,state in fields.items() if state['state']=='cleared'])
    projection['published'] = {'title_sort':snapshot.get('title_sort'), 'summary':snapshot.get('summary'),
        'studio':snapshot.get('studio'),'rating':decimal_text(snapshot.get('rating')),
        'genres':exact_set(snapshot.get('genres')),
        'other_moods':exact_set([v for v in snapshot.get('moods',[]) if not v.startswith(PREFIX)])}
    key = canonical_client_key(snapshot.get('id')) or None
    result = {'contract_version':4,'recording_key':key,
        'revisions':{'metadata':digest(projection),'artwork':artwork_revision},
        'match':context.get('match') or previous.get('match') or {'source':'unknown','evidence':'unknown'},
        'fields':fields,'cleared_namespaces':context.get('cleared_namespaces',[]),
        'identity_upgrades':list(previous.get('identity_upgrades') or []) if key else []}
    upgrade = verify_upgrade(previous.get('recording_key'),key,context.get('previous_profile') or {},profile or {},
                             context.get('confirmed_recording',False)) if key else None
    if not upgrade and result['identity_upgrades']:
        conflicts=compatible_profiles(context.get('previous_profile') or {},profile or {})
        if conflicts:
            result['identity_upgrades']=[dict(item,status='review_required',reasons=conflicts)
                for item in result['identity_upgrades']]
    if upgrade:
        # Bounded declarations, not an alias graph or listening-state mutation.
        result['identity_upgrades'] = [upgrade]
    return normalized(result)


def any_provider_ids(tags):
    for tag in tags:
        parts=tag[16:].split(' = ',1)[0].split(':')
        if len(parts)==3 and parts[1]!='name':
            return True
    return False


def decimal_text(value):
    if value is None:
        return None
    text = ('%.6f' % float(value)).rstrip('0').rstrip('.')
    if text.lower() in ('nan','inf','-inf'):
        return None
    return text or '0'


def encode(payload):
    validate(payload)
    raw = canonical(payload)
    if len(raw)>MAX_BYTES:
        raise ValueError('v4 payload exceeds byte limit')
    sha = hashlib.sha256(raw).hexdigest()
    data = base64.urlsafe_b64encode(zlib.compress(raw,9)).decode('ascii').rstrip('=')
    count = (len(data)+CHUNK_SIZE-1)//CHUNK_SIZE
    if count<1 or count>MAX_CHUNKS:
        raise ValueError('v4 chunk limit exceeded')
    return [PREFIX+'%s:%d/%d:%s'%(sha,index+1,count,data[index*CHUNK_SIZE:(index+1)*CHUNK_SIZE]) for index in range(count)]


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate v4 JSON key')
        result[key] = value
    return result


def decode_unchecked(moods):
    parts, identity, total = {},None,None
    for tag in moods:
        if not isinstance(tag,TEXT_TYPES) or not tag.startswith(PREFIX):
            continue
        match = re.match(r'^([0-9a-f]{64}):([1-9][0-9]?)/([1-9][0-9]?):([A-Za-z0-9_-]+)$',tag[len(PREFIX):])
        if not match:
            raise ValueError('malformed v4 chunk')
        sha,index,count,data = match.group(1),int(match.group(2)),int(match.group(3)),match.group(4)
        if count>MAX_CHUNKS or index>count or len(data)>CHUNK_SIZE or index in parts:
            raise ValueError('invalid/duplicate v4 chunk')
        if identity is not None and (sha!=identity or total!=count):
            raise ValueError('mixed v4 envelopes')
        identity,total = sha,count
        parts[index] = data
    if identity is None:
        return None
    if len(parts)!=total:
        raise ValueError('incomplete v4 envelope')
    encoded = ''.join([parts[i] for i in range(1,total+1)])
    data = base64.urlsafe_b64decode((encoded+'='*((-len(encoded))%4)).encode('ascii'))
    inflater = zlib.decompressobj()
    raw = inflater.decompress(data,MAX_BYTES+1)
    if len(raw)>MAX_BYTES or inflater.unconsumed_tail or inflater.unused_data or len(data)<6:
        raise ValueError('v4 expansion/trailing data limit')
    if data[-4:]!=struct.pack('>I',zlib.adler32(raw)&0xffffffff):
        raise ValueError('incomplete v4 compressed stream')
    if hashlib.sha256(raw).hexdigest()!=identity:
        raise ValueError('v4 digest mismatch')
    payload = json.loads(raw.decode('ascii'),object_pairs_hook=unique_object)
    validate(payload)
    if canonical(payload)!=raw:
        raise ValueError('noncanonical v4 payload')
    return payload


def canonical_key_valid(key):
    if key is None:
        return True
    if not isinstance(key,TEXT_TYPES):
        return False
    match=re.match(r'^spokenmeta:audible:(au|ca|de|es|fr|in|it|jp|uk|us):([A-Z0-9]{10})$',key)
    if match:
        return canonical_client_key(match.group(2)+'_'+match.group(1))==key
    match=re.match(r'^spokenmeta:(librivox|isbn|local):([A-Za-z0-9]+)$',key)
    return bool(match and canonical_client_key(match.group(1)+':'+match.group(2))==key)


# Schema validation is intentionally dependency-free for the Plex interpreter.
def validate(payload):
    required=('contract_version','recording_key','revisions','match','fields',
              'cleared_namespaces','identity_upgrades')
    if not isinstance(payload,dict) or set(payload)!=set(required) or payload['contract_version']!=4:
        raise ValueError('unsupported v4 payload shape')
    if not canonical_key_valid(payload['recording_key']):
        raise ValueError('invalid recording key')
    revisions=payload['revisions']
    if not isinstance(revisions,dict) or set(revisions)!=set(('metadata','artwork')):
        raise ValueError('invalid revisions')
    if not re.match(r'^sha256:[0-9a-f]{64}$',to_text(revisions.get('metadata'))):
        raise ValueError('invalid metadata revision')
    if revisions['artwork'] is not None and not re.match(r'^sha256:[0-9a-f]{64}$',to_text(revisions['artwork'])):
        raise ValueError('invalid artwork revision')
    match=payload['match']
    if not isinstance(match,dict) or set(match)!=set(('source','evidence','method')):
        raise ValueError('invalid overall match')
    if match['source'] not in SOURCES or match['evidence'] not in EVIDENCE or match['method'] not in (
        'unknown','manual_override','explicit_identifier','provider_match','local_fallback'):
        raise ValueError('invalid match category')
    field_names=('title','authors','narrators','series','recording_date','language','edition',
                 'work','work_publication','contributors','artwork')
    if not isinstance(payload['fields'],dict) or set(payload['fields'])!=set(field_names):
        raise ValueError('missing or unknown v4 field')
    for field,value in payload['fields'].items():
        if (not isinstance(value,dict) or not set(('state','value','stale','provenance')).issubset(value) or
                value.get('state') not in STATES or not isinstance(value.get('stale'),bool)):
            raise ValueError('invalid field state')
        if set(value)-set(('state','value','stale','reason','provenance','identity_evidence')):
            raise ValueError('unknown field attribute')
        if value.get('state')=='cleared' and not empty_value(value.get('value')):
            raise ValueError('cleared field contains a value')
        provenance=value.get('provenance',{})
        if (not isinstance(provenance,dict) or provenance.get('source') not in SOURCES or
                provenance.get('evidence') not in EVIDENCE or set(provenance)-set(('source','evidence','date_kind'))):
            raise ValueError('invalid provenance')
        if provenance.get('date_kind') is not None and provenance['date_kind'] not in (
            'recording_release','copyright_year_fallback','work_year_fallback',
            'book_edition_date_fallback','user_supplied_recording_date'):
            raise ValueError('invalid date semantics')
        if value.get('identity_evidence') is not None and value['identity_evidence'] not in ('unknown','name_only','provider_identifier'):
            raise ValueError('invalid contributor evidence')
    series=payload['fields']['series']['value']
    if not isinstance(series,dict) or set(series)!=set(('primary_ref','memberships')) or not isinstance(series['memberships'],list):
        raise ValueError('invalid series relationships')
    refs=set()
    for item in series['memberships']:
        if not isinstance(item,dict) or set(item)-set(('ref','title','sequence','provider_id')):
            raise ValueError('invalid series membership')
        if not isinstance(item.get('title'),TEXT_TYPES) or not item['title'] or not isinstance(item.get('sequence'),TEXT_TYPES):
            raise ValueError('invalid series display')
        copy=dict(item)
        reference=copy.pop('ref',None)
        if reference!='relationship:'+hashlib.sha256(canonical(copy)).hexdigest() or reference in refs:
            raise ValueError('invalid or duplicate series reference')
        refs.add(reference)
        provider=item.get('provider_id')
        if provider is not None:
            if not isinstance(provider,dict) or set(provider)!=set(('source','scope','id')):
                raise ValueError('invalid supplied series identifier')
            audible=(provider['source']=='audible' and provider['scope'] in ('au','ca','de','es','fr','in','it','jp','uk','us')
                     and valid_asin(provider['id']))
            swedish=(provider['source']=='ljudboksarkivet' and provider['scope']==''
                     and re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$',to_text(provider['id'])))
            if not (audible or swedish):
                raise ValueError('invalid supplied series identifier')
    if series['primary_ref'] is not None and series['primary_ref'] not in refs:
        raise ValueError('primary series reference is missing')
    if not isinstance(payload['cleared_namespaces'],list) or set(payload['cleared_namespaces'])-set(
        ('work_identity','work_publication','openlibrary_author_ids','extended_metadata')):
        raise ValueError('invalid cleared namespaces')
    if payload['fields']['artwork']['value']!=revisions['artwork']:
        raise ValueError('artwork field/revision mismatch')
    upgrades=payload['identity_upgrades']
    if not isinstance(upgrades,list) or len(upgrades)>8:
        raise ValueError('invalid upgrade list')
    for item in upgrades:
        if not isinstance(item,dict) or set(item)!=set(('previous','current','status','evidence','reasons','requires_client_confirmation')):
            raise ValueError('invalid upgrade declaration')
        if (not canonical_key_valid(item['previous']) or not item['previous'] or
            item['current']!=payload['recording_key'] or item['previous']==item['current'] or
            item['requires_client_confirmation'] is not True or not isinstance(item['reasons'],list) or
            not isinstance(item['evidence'],list) or item['status'] not in ('review_required','verified_same_recording')):
            raise ValueError('unsafe upgrade declaration')
        if item['status']=='verified_same_recording':
            if not item['previous'].startswith('spokenmeta:local:') or item['reasons']:
                raise ValueError('unsafe verified upgrade')
            proof=item['evidence']
            if not ((proof==['same_explicit_asin_and_region'] and item['current'].startswith('spokenmeta:audible:')) or
                    (proof==['same_explicit_librivox_project'] and item['current'].startswith('spokenmeta:librivox:'))):
                raise ValueError('missing exact recording proof')
    canonical(payload)  # reject noncanonical runtime types, including floats


def decode(moods):
    try:
        return decode_unchecked(moods)
    except (TypeError,KeyError,AttributeError,OverflowError,zlib.error,UnicodeError,binascii.Error,ValueError):
        raise ValueError('Invalid Contract v4 envelope')


def decode_for_recording(moods,guid_or_key):
    payload=decode(moods)
    key=(guid_or_key if isinstance(guid_or_key,TEXT_TYPES) and guid_or_key.startswith('spokenmeta:')
         and canonical_key_valid(guid_or_key) else canonical_client_key(guid_or_key))
    if payload is not None and payload['recording_key']!=key:
        raise ValueError('Contract v4 recording key does not match album GUID')
    return payload
