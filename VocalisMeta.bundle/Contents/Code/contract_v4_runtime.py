# coding: utf-8
"""Per-operation evidence capture. Never stores URLs, paths or request errors."""
from __future__ import unicode_literals
import search_runtime
import re
from contract_v4_core import series_relationships, exact_set
from audible_core import to_text, people, product_abridged, product_runtime_minutes, language_label
from multipart_core import language_key


def current():
    try:
        return search_runtime.CONTEXT.contract_v4
    except AttributeError:
        return None


def observe(field,value,source,evidence):
    context=current()
    if context is not None:
        context.setdefault('evidence',{}).setdefault(field,[]).append(
            {'value':value,'source':source,'evidence':evidence})


def clear(field,reason):
    context=current()
    if context is not None:
        context.setdefault('cleared',{})[field]=reason


def fail(artwork=False):
    context=current()
    if context is not None:
        context['artwork_failed' if artwork else 'failed']=True


def series(entries,source,scope='',evidence='provider_match',replace=False):
    context=current()
    if context is None:
        return
    if entries or replace:
        if source=='embedded_tags' and context.get('series') is not None:
            return
        value=series_relationships(entries,source,scope)
        context['series']=value
        observe('series',value,source,evidence)


def embedded(record):
    context=current()
    if context is None:
        return
    profile=context.setdefault('profile',{})
    for field in ('asin','region','librivox_id','abridged'):
        if record.get(field) is not None:
            profile[field]=record[field]
    if record.get('language'):
        profile['language']=language_key(record['language'])
        tag=locale_tag(record['language'])
        if tag:
            profile['language_tag']=tag
        observe('language',language_label(record['language']),'embedded_tags','embedded_tags')
    if record.get('abridged') is not None:
        observe('edition','Abridged' if record['abridged'] else 'Unabridged','embedded_tags','embedded_tags')
    profile['conflicting_tags']=bool(record.get('conflicts'))
    for field in ('authors','narrators'):
        if record.get(field):
            observe(field,exact_set(record[field]),'embedded_tags','embedded_tags')
    if record.get('narrators'):
        profile['narrators']=exact_set(record['narrators'])
    if record.get('series'):
        series([{'title':record['series'],'sequence':record.get('series_sequence') or ''}],
               'embedded_tags',evidence='embedded_tags')


def provider(source,title,authors,narrators,entries,language=None,abridged=None,date=None,scope='',runtime=None):
    context=current()
    if context is None:
        return
    context['provider_source']=source
    context['confirmed_recording']=source in ('audible','librivox')
    evidence='explicit_identifier' if source in ('audible','librivox') else 'provider_match'
    context['provider_evidence']=evidence
    if title:
        observe('title',title,source,evidence)
    for field,values in (('authors',authors),('narrators',narrators)):
        if values:
            observe(field,exact_set(values),source,evidence)
    series(entries,source,scope,evidence)
    if language:
        observe('language',language_label(language),source,evidence)
    if abridged is not None:
        observe('edition','Abridged' if abridged else 'Unabridged',source,evidence)
    if date:
        recording_date(to_text(date)[:10],source,evidence,
            'copyright_year_fallback' if source=='librivox' else 'recording_release')
    profile=context.setdefault('profile',{})
    tag=locale_tag(language) if language else None
    if tag:
        if profile.get('language_tag') and profile['language_tag']!=tag:
            profile['conflicting_tags']=True
        elif not profile.get('language_tag'):
            profile['language_tag']=tag
    for field,value in (('language',language_key(language) if language else None),
                        ('abridged',abridged),('narrators',exact_set(narrators) if narrators else None)):
        old=profile.get(field)
        if old is not None and value is not None and old!=value:
            profile['conflicting_tags']=True
        if old is None and value is not None:
            profile[field]=value
    if runtime:
        try:
            milliseconds=int(round(runtime*60000))
        except (TypeError,ValueError,OverflowError):
            milliseconds=0
        before=profile.get('duration_ms')
        if before and milliseconds>0 and abs(before-milliseconds)>max(60000,int(min(before,milliseconds)*0.005)):
            profile['conflicting_tags']=True
        if not before and milliseconds>0:
            profile['duration_ms']=milliseconds


def scalar(field,value):
    context=current()
    if context is not None and field=='title' and context.get('provider_source'):
        observe('title',value,context['provider_source'],context['provider_evidence'])


def manual(document):
    for field,value in document.get('metadata',{}).items():
        if field=='series':
            series(value,'manual',evidence='manual_override',replace=True)
            if not value:
                clear('series','manual_clear')
        elif field in ('title','authors','narrators','language'):
            converted=exact_set(value) if isinstance(value,list) else language_label(value) if field=='language' else value
            observe(field,converted,'manual','manual_override')
            if value==[]:
                clear(field,'manual_clear')
        elif field=='release_date':
            recording_date(value,'manual','manual_override','user_supplied_recording_date')
        elif field=='abridged':
            observe('edition','Abridged' if value else 'Unabridged','manual','manual_override')


def image(key,sha,order,source,evidence):
    context=current()
    if context is not None:
        context.setdefault('images',[]).append({'key':key,'sha256':sha,'order':order,
                                              'source':source,'evidence':evidence})


def accepted_image(keys):
    context=current()
    if context is None:
        return
    values=[item for item in context.get('images',[]) if item['key'] in keys]
    if values:
        # Last candidate wins ties (an explicit sidecar cover is applied last).
        minimum=min([item['order'] for item in values])
        chosen=[item for item in values if item['order']==minimum][-1]
        context['artwork']={k:chosen[k] for k in ('sha256','source','evidence')}


def recording_date(value,source,evidence,kind):
    observe('recording_date',value,source,evidence)
    context=current()
    if context is not None:
        context['evidence']['recording_date'][-1]['date_kind']=kind


def locale_tag(value):
    text=to_text(value).strip().replace('_','-').lower()
    return text if re.match(r'^[a-z]{2,3}-[a-z0-9]{2,8}(?:-[a-z0-9]{2,8})*$',text) else None
