# coding: utf-8
"""Pure, Python 2.7-compatible Audible helpers for the VocalisMeta Plex agent."""

from __future__ import unicode_literals

import re
import unicodedata

try:
    from urllib import urlencode, quote_plus, unquote_plus
except ImportError:  # Python 3 test environment
    from urllib.parse import urlencode, quote_plus, unquote_plus

try:
    text_type = unicode
except NameError:  # pragma: no cover - Python 3 only
    text_type = str


REGION_TLDS = {
    'au': 'com.au',
    'ca': 'ca',
    'de': 'de',
    'es': 'es',
    'fr': 'fr',
    'in': 'in',
    'it': 'it',
    'jp': 'co.jp',
    'us': 'com',
    'uk': 'co.uk',
}

LANGUAGE_NAMES = {
    'de': 'german', 'deu': 'german', 'ger': 'german',
    'en': 'english', 'eng': 'english',
    'es': 'spanish', 'spa': 'spanish',
    'fr': 'french', 'fra': 'french', 'fre': 'french',
    'it': 'italian', 'ita': 'italian',
    'ja': 'japanese', 'jpn': 'japanese',
}

RESPONSE_GROUPS = ','.join([
    'contributors',
    'media',
    'product_desc',
    'product_extended_attrs',
    'product_attrs',
    'rating',
    'series',
    'category_ladders',
])

ASIN_RE = re.compile(r'(?<![A-Z0-9])([A-Z0-9]{10})(?![A-Z0-9])', re.I)
ASIN_HINT_RE = re.compile(r'(?<![A-Z0-9])(B[A-Z0-9]{9})(?![A-Z0-9])', re.I)
ASIN_LABEL_RE = re.compile(
    r'\bASIN\s*[:#=_-]\s*([A-Z0-9]{10})(?![A-Z0-9])', re.I
)
PLEX_ID_SUFFIX_RE = re.compile(r'/-?\d+$')
REGION_RE = re.compile(r'\[\s*(au|ca|de|es|fr|in|it|jp|us|uk)\s*\]', re.I)
TAG_RE = re.compile(r'<[^>]+>')
BREAK_RE = re.compile(r'<\s*(?:br\s*/?|/p|/li|/ul|/ol)\s*>', re.I)
LIST_RE = re.compile(r'<\s*li(?:\s+[^>]*)?\s*>', re.I)


def to_text(value):
    if value is None:
        return ''
    if isinstance(value, text_type):
        return value
    try:
        return value.decode('utf-8', 'replace')
    except AttributeError:
        return text_type(value)


def text_field(value):
    """Return only genuine catalog text, never a container representation."""
    if isinstance(value, text_type):
        return value.strip()
    try:
        return value.decode('utf-8', 'replace').strip()
    except AttributeError:
        return ''


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return to_text(value).strip().lower() in ('1', 'true', 'yes', 'on')


def normalize_text(value):
    value = REGION_RE.sub(' ', to_text(value))
    value = unicodedata.normalize('NFKD', value)
    characters = []
    # Plex's Python 2 RestrictedPython guard cannot iterate unicode directly.
    # Index access preserves the full Unicode normalization behavior.
    for index in range(len(value)):
        character = value[index]
        if not unicodedata.combining(character):
            characters.append(character)
    value = ''.join(characters)
    value = value.lower()
    value = re.sub(r'\b(?:official\s+)?audiobook\b', ' ', value)
    value = re.sub(r'\b(?:unabridged|abridged)\b', ' ', value)
    value = re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', value).strip()


def primary_title(value):
    value = to_text(value).strip()
    value = re.sub(r'\s*[\[(](?:unabridged|abridged|audio(?:book)?)[^\])]*[\])]\s*$', '', value, flags=re.I)
    for separator in (':', ' - '):
        if separator in value:
            head = value.split(separator, 1)[0].strip()
            if len(head) >= 3:
                return head
    return value


def filename_title(value):
    """Return a conservative title derived from a Plex media filename."""
    value = to_text(value).strip()
    if not value:
        return ''
    try:
        value = to_text(unquote_plus(value))
    except Exception:
        pass
    value = value.replace('\\', '/')
    value = value.rsplit('/', 1)[-1]
    value = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', value)
    value = re.sub(r'\s*[\[(]\d+[\])]\s*$', '', value)
    value = re.sub(r'^\s*\d+\s*[-._]\s*', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def filename_author(value, title=''):
    """Return an author from an unambiguous Author/Book/file path."""
    value = to_text(value).strip()
    if not value:
        return ''
    try:
        value = to_text(unquote_plus(value))
    except Exception:
        pass
    value = value.replace('\\', '/')
    parts = [part.strip() for part in value.split('/') if part.strip()]
    if len(parts) < 3:
        return ''
    book_directory = parts[-2]
    author_directory = parts[-3]
    normalized_book = normalize_text(book_directory)
    normalized_title = normalize_text(title)
    primary = normalize_text(primary_title(title))
    if normalized_title and not (
        normalized_book == normalized_title
        or normalized_book == primary
        or (len(normalized_book) >= 4 and normalized_book in normalized_title)
    ):
        return ''
    if normalize_text(author_directory) in (
        'audiobook', 'audiobooks', 'audio book', 'audio books', 'book',
        'books', 'media', 'media book audio',
    ):
        return ''
    return re.sub(r'\s+', ' ', author_directory).strip()


def search_title_variants(value, filename=''):
    """Return ordered catalog queries without assuming which side is the title."""
    title = to_text(value).strip()
    candidates = []
    if title:
        candidates.append(title)
        if ' - ' in title:
            head, tail = title.split(' - ', 1)
            if len(tail.strip()) >= 3:
                candidates.append(tail.strip())
            if len(head.strip()) >= 3:
                candidates.append(head.strip())
        base = primary_title(title)
        if base:
            candidates.append(base)
    file_title = filename_title(filename)
    if file_title:
        candidates.append(file_title)

    output = []
    seen = set()
    for candidate in candidates:
        key = normalize_text(candidate)
        if key and key not in seen:
            seen.add(key)
            output.append(candidate)
    return output


def find_asin(*values):
    for value in values:
        text = to_text(value).strip().upper()
        if valid_asin(text):
            return text
        labelled = ASIN_LABEL_RE.search(text)
        if labelled and valid_asin(labelled.group(1)):
            return labelled.group(1)
        for match in ASIN_HINT_RE.findall(text):
            if valid_asin(match):
                return match
    return None


def valid_asin(value):
    value = to_text(value).strip().upper()
    match = ASIN_RE.search(value)
    if not match or match.group(1).upper() != value:
        return False
    # Plex's Python 2 RestrictedPython iterator guard cannot iterate unicode
    # strings directly because unicode does not expose an allowed __iter__.
    return bool(re.search(r'\d', value))


def strip_identity_hints(value):
    value = REGION_RE.sub(' ', to_text(value))
    value = ASIN_RE.sub(' ', value)
    value = re.sub(r'\s*[-_:|]+\s*$', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def find_region(default_region, *values):
    override = find_region_override(*values)
    if override:
        return override
    return default_region if default_region in REGION_TLDS else 'us'


def find_region_override(*values):
    for value in values:
        match = REGION_RE.search(to_text(value))
        if match:
            return match.group(1).lower()
    return None


def make_id(identifier, region):
    return '%s_%s' % (to_text(identifier), region if region in REGION_TLDS else 'us')


def split_id(value, default_region='us'):
    value = PLEX_ID_SUFFIX_RE.sub('', to_text(value).strip())
    if '_' in value:
        identifier, possible_region = value.rsplit('_', 1)
        if possible_region.lower() in REGION_TLDS:
            return identifier, possible_region.lower()
    return value, default_region if default_region in REGION_TLDS else 'us'


def make_author_id(asin, name, region):
    if asin:
        return make_id(asin, region)
    return make_id('name:' + quote_plus(to_text(name).encode('utf-8')), region)


def author_name_from_id(value):
    identifier, unused_region = split_id(value)
    del unused_region
    if identifier.startswith('name:'):
        decoded = unquote_plus(identifier[5:])
        return to_text(decoded)
    return ''


def plex_identifier_from_guid(value):
    """Return the identifier portion of a Plex metadata GUID."""
    value = to_text(value).strip().replace('\\:', ':')
    if '://' in value:
        value = value.split('://', 1)[1]
    return value.split('?', 1)[0]


def author_name_from_guid(value):
    """Return a name-backed VocalisMeta author from a Plex parent GUID."""
    return author_name_from_id(plex_identifier_from_guid(value))


def author_id_from_guid(value):
    """Return an author identifier and region from a Plex parent GUID."""
    return split_id(plex_identifier_from_guid(value))


def api_base(region, custom_base=''):
    custom_base = to_text(custom_base).strip().rstrip('/')
    if custom_base:
        return custom_base
    return 'https://api.audible.%s' % REGION_TLDS.get(region, REGION_TLDS['us'])


def catalog_url(region, params, custom_base=''):
    merged = {
        'response_groups': RESPONSE_GROUPS,
    }
    merged.update(params)
    encoded = {}
    for key, value in merged.items():
        if value is not None and to_text(value).strip() != '':
            encoded[key] = to_text(value).encode('utf-8')
    return '%s/1.0/catalog/products?%s' % (
        api_base(region, custom_base), urlencode(encoded)
    )


def products_from_response(response):
    if not isinstance(response, dict):
        return []
    products = response.get('products')
    if not isinstance(products, list):
        return []
    return [product for product in products if valid_product(product)]


def valid_product(product):
    title = product.get('title') if isinstance(product, dict) else None
    return bool(
        isinstance(product, dict)
        and valid_asin(product.get('asin'))
        and text_field(title)
    )


def list_items(value):
    return value if isinstance(value, (list, tuple)) else []


def people(product, key):
    if not isinstance(product, dict):
        return []
    values = list_items(product.get(key))
    output = []
    for value in values:
        if isinstance(value, dict):
            name = text_field(value.get('name'))
        else:
            name = text_field(value)
        if name and name not in output:
            output.append(name)
    return output


def author_name_variants(value):
    value = to_text(value).strip()
    if not value:
        return []
    candidates = [value]
    candidates.extend(re.split(
        r'\s*(?:[;&|,]|\band\b)\s*', value, flags=re.I
    ))
    output = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip()
        key = normalize_text(candidate)
        if key and key not in seen:
            seen.add(key)
            output.append(candidate)
    return output


def author_ratio(wanted_author, product):
    wanted_names = author_name_variants(wanted_author)
    actual_names = people(product, 'authors')
    if not wanted_names or not actual_names:
        return 0.0
    return max([
        levenshtein_ratio(wanted, actual)
        for wanted in wanted_names
        for actual in actual_names
    ])


def contributor_objects(product, key):
    if not isinstance(product, dict):
        return []
    values = list_items(product.get(key))
    return [
        item for item in values
        if isinstance(item, dict) and text_field(item.get('name'))
    ]


def display_title(product, include_subtitle=True):
    title = text_field(product.get('title'))
    subtitle = text_field(product.get('subtitle'))
    if include_subtitle and subtitle and normalize_text(subtitle) not in normalize_text(title):
        return '%s: %s' % (title, subtitle)
    return title


def levenshtein_ratio(left, right):
    left = normalize_text(left)
    right = normalize_text(right)
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for col, right_char in enumerate(right, 1):
            current.append(min(
                current[col - 1] + 1,
                previous[col] + 1,
                previous[col - 1] + (left_char != right_char),
            ))
        previous = current
    return max(0.0, 1.0 - (float(previous[-1]) / float(max(len(left), len(right)))))


def title_ratio(wanted, product):
    candidate = display_title(product, True)
    variants_wanted = [wanted, primary_title(wanted)]
    variants_candidate = [candidate, product.get('title', ''), primary_title(candidate)]
    return max([
        levenshtein_ratio(a, b)
        for a in variants_wanted
        for b in variants_candidate
    ])


def product_runtime_minutes(product):
    for key in ('runtime_length_min', 'runtime_length_minutes', 'runtime_minutes'):
        try:
            value = float(product.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def runtime_label(product):
    value = product_runtime_minutes(product)
    if not value:
        return ''
    minutes = max(1, int(round(value)))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return '%dh %dm' % (hours, minutes)
    if hours:
        return '%dh' % hours
    return '%dm' % minutes


def product_abridged(product):
    for key in ('is_abridged', 'abridged'):
        if key not in product:
            continue
        value = product.get(key)
        if isinstance(value, bool):
            return value
        text = to_text(value).strip().lower()
        if text in ('1', 'true', 'yes'):
            return True
        if text in ('0', 'false', 'no'):
            return False
    format_type = to_text(product.get('format_type')).lower()
    if 'unabridged' in format_type:
        return False
    if re.search(r'\babridged\b', format_type):
        return True
    return None


def presentation_traits(*values):
    """Return explicit audiobook-presentation traits found in title text."""
    combined = normalize_text(' '.join([
        to_text(value) for value in values if to_text(value).strip()
    ]))
    traits = []
    if (
        'radio dramatisation' in combined or
        'radio dramatization' in combined or
        'radio drama' in combined or
        'radio play' in combined or
        'audio drama' in combined or
        'dramatised' in combined or
        'dramatized' in combined or
        'dramatisation' in combined or
        'dramatization' in combined
    ):
        traits.append('dramatization')
    if 'full cast' in combined or 'fullcast' in combined:
        traits.append('full_cast')
    return traits


def product_presentation_traits(product):
    if not isinstance(product, dict):
        return []
    return presentation_traits(
        text_field(product.get('title')),
        text_field(product.get('subtitle')),
    )


def presentation_label(product):
    if not isinstance(product, dict):
        return ''
    traits = product_presentation_traits(product)
    combined = normalize_text('%s %s' % (
        text_field(product.get('title')),
        text_field(product.get('subtitle')),
    ))
    if 'dramatization' in traits:
        if 'radio' in combined:
            return 'Radio dramatisation'
        return 'Dramatized adaptation'
    if 'full_cast' in traits:
        return 'Full cast'
    return ''


def presentation_mismatch_penalty(wanted_title, product):
    """Demote explicitly different productions without hiding manual matches."""
    wanted = presentation_traits(wanted_title)
    actual = product_presentation_traits(product)
    if 'dramatization' in actual and 'dramatization' not in wanted:
        return 35
    if 'full_cast' in actual and 'full_cast' not in wanted:
        return 24
    return 0


def sequence_label(value):
    """Return a compact, client-parseable series position."""
    value = to_text(value).strip()
    if not value:
        return ''
    value = re.sub(r'^\s*(?:book|volume|vol\.?|part)\s*#?\s*', '', value, flags=re.I)
    value = value.lstrip('#').strip()
    if re.match(r'^\d+(?:\.\d+)?$', value):
        if '.' in value:
            value = value.rstrip('0').rstrip('.')
        else:
            value = str(int(value))
        return value
    roman_values = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
        'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
        'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20,
    }
    return str(roman_values.get(value.upper(), value))


def language_label(value):
    """Return a human-readable language without inventing missing evidence."""
    value = to_text(value).strip()
    if not value:
        return ''
    normalized = value.lower().replace('_', '-').split('-', 1)[0]
    aliases = {
        'eng': 'English', 'deu': 'German', 'ger': 'German',
        'spa': 'Spanish', 'fra': 'French', 'fre': 'French',
        'ita': 'Italian', 'jpn': 'Japanese',
    }
    if normalized in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[normalized].capitalize()
    if normalized in aliases:
        return aliases[normalized]
    return value[:1].upper() + value[1:]


def release_year(product):
    try:
        value = int(release_date(product)[:4])
        return value if 0 < value < 10000 else None
    except (TypeError, ValueError):
        return None


def edition_details(product, region=''):
    """Return concise, deterministic details for Plex Fix Match labels."""
    output = []
    presentation = presentation_label(product)
    if presentation:
        output.append(presentation)
    runtime = runtime_label(product)
    if runtime:
        output.append(runtime)
    year = release_year(product)
    if year:
        output.append(str(year))
    abridged = product_abridged(product)
    if abridged is not None:
        output.append('Abridged' if abridged else 'Unabridged')
    language = text_field(product.get('language'))
    if language:
        output.append(language[:1].upper() + language[1:])
    region = to_text(region).strip().upper()
    if region.lower() in REGION_TLDS:
        output.append(region)
    return output


def search_result_label(product, region=''):
    authors = ', '.join(people(product, 'authors')) or 'Unknown author'
    narrators = ', '.join(people(product, 'narrators'))
    label = '"%s" by %s' % (display_title(product, True), authors)
    if narrators:
        label += ' — narrated by ' + narrators
    details = edition_details(product, region)
    if details:
        label += ' — ' + ' · '.join(details)
    return label


def edition_penalty(product, duration_minutes=None, narrators=None, year=None, abridged=None):
    """Return a mismatch-only penalty for audiobook-edition evidence."""
    penalty = 0.0
    actual_runtime = product_runtime_minutes(product)
    try:
        wanted_runtime = float(duration_minutes)
    except (TypeError, ValueError):
        wanted_runtime = 0.0
    if actual_runtime and wanted_runtime > 0:
        difference = abs(actual_runtime - wanted_runtime)
        ratio = difference / max(actual_runtime, wanted_runtime)
        if difference > 3 and ratio > 0.03:
            if ratio <= 0.08:
                penalty += 1
            elif ratio <= 0.15:
                penalty += 3
            elif ratio <= 0.30:
                penalty += 8
            elif ratio <= 0.50:
                penalty += 15
            else:
                penalty += 28

    wanted_narrators = narrators if isinstance(narrators, (list, tuple)) else [narrators]
    wanted_narrators = [to_text(name).strip() for name in wanted_narrators if to_text(name).strip()]
    actual_narrators = people(product, 'narrators')
    if wanted_narrators and actual_narrators:
        best = max([
            levenshtein_ratio(wanted, actual)
            for wanted in wanted_narrators
            for actual in actual_narrators
        ])
        if best < 0.80:
            penalty += 7

    try:
        wanted_year = int(year)
    except (TypeError, ValueError):
        wanted_year = None
    actual_year = release_year(product)
    if wanted_year and actual_year:
        difference = abs(wanted_year - actual_year)
        if difference >= 15:
            penalty += 6
        elif difference >= 5:
            penalty += 4
        elif difference >= 2:
            penalty += 2

    actual_abridged = product_abridged(product)
    if abridged is not None and actual_abridged is not None and bool(abridged) != actual_abridged:
        penalty += 14
    return penalty


def score_product(wanted_title, wanted_author, wanted_language, product, rank=0,
                  duration_minutes=None, narrators=None, year=None, abridged=None):
    if not valid_asin(product.get('asin')) or not product.get('title'):
        return 0
    title_score = title_ratio(wanted_title, product)
    if wanted_author:
        author_score = author_ratio(wanted_author, product)
        score = (title_score * 84.0) + (author_score * 14.0)
    else:
        score = title_score * 98.0
    expected_language = LANGUAGE_NAMES.get(to_text(wanted_language).lower(), normalize_text(wanted_language))
    actual_language = normalize_text(product.get('language'))
    if expected_language and actual_language and expected_language == actual_language:
        score += 2.0
    elif expected_language and actual_language:
        score = score - 5.0
    score = score - edition_penalty(
        product, duration_minutes, narrators, year, abridged
    )
    score = score - presentation_mismatch_penalty(wanted_title, product)
    score = score - (min(int(rank), 9) * 0.35)
    return max(0, min(100, int(round(score))))


def score_author(wanted_name, author, rank=0):
    score = levenshtein_ratio(wanted_name, author.get('name')) * 100.0
    score = score - (min(int(rank), 9) * 0.25)
    return max(0, min(100, int(round(score))))


def release_date(product):
    for key in ('release_date', 'issue_date', 'publication_datetime'):
        value = text_field(product.get(key))
        if value:
            return value[:10]
    return ''


def is_preorder(product, today_iso):
    value = release_date(product)
    return bool(value and today_iso and value > today_iso)


def rating_out_of_ten(product):
    rating = product.get('rating')
    if not isinstance(rating, dict):
        return None
    overall = rating.get('overall_distribution')
    if not isinstance(overall, dict):
        return None
    value = overall.get('average_rating') or overall.get('display_average_rating')
    try:
        return min(10.0, max(0.0, float(value) * 2.0))
    except (TypeError, ValueError):
        return None


def genres(product, maximum=8):
    output = []
    ladders = list_items(product.get('category_ladders'))
    for category in ladders:
        if not isinstance(category, dict) or category.get('root') not in (None, 'Genres'):
            continue
        for item in list_items(category.get('ladder')):
            name = text_field(item.get('name') if isinstance(item, dict) else item)
            if name and name not in output:
                output.append(name)
                if len(output) >= maximum:
                    return output
    for item in list_items(product.get('genres')):
        name = text_field(item.get('name') if isinstance(item, dict) else item)
        if name and name not in output:
            output.append(name)
            if len(output) >= maximum:
                break
    return output


def series_entries(product):
    output = []
    indexes = {}
    for item in list_items(product.get('series')):
        if not isinstance(item, dict):
            continue
        title = re.sub(r'\s+', ' ', (
            text_field(item.get('title')) or text_field(item.get('name'))
        )).strip()
        sequence = re.sub(
            r'\s+', ' ', (
                text_field(item.get('sequence')) or text_field(item.get('position'))
            )
        ).strip()
        key = normalize_text(title)
        if not title or not key:
            continue
        if key in indexes:
            existing = output[indexes[key]]
            if not existing['sequence'] and sequence:
                existing['sequence'] = sequence
            continue
        indexes[key] = len(output)
        output.append({'title': title, 'sequence': sequence})
    return output


def roman_number(value):
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    text = to_text(value).strip().upper()
    if not text or not re.match(r'^[IVXLC]+$', text):
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        current = values[char]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total if 0 < total < 10000 else None


def sequence_sort_key(value):
    """Convert common series positions into lexically sortable text."""
    text = re.sub(r'\s+', ' ', to_text(value)).strip()
    if not text:
        return ''
    matches = re.findall(r'\d+(?:[.,]\d+)?', text)
    if matches:
        output = []
        for match in matches[:3]:
            pieces = match.replace(',', '.').split('.', 1)
            whole = pieces[0].lstrip('0') or '0'
            key = whole.zfill(4)
            if len(pieces) == 2:
                fraction = pieces[1].rstrip('0')
                if fraction:
                    key += '.' + fraction.ljust(4, '0')[:4]
            output.append(key)
        return '.'.join(output)
    words = re.findall(r'[A-Za-z]+', text)
    if words:
        roman = roman_number(words[-1])
        if roman is not None:
            return str(roman).zfill(4)
    normalized = normalize_text(text)
    return 'ZZZZ ' + normalized if normalized else ''


def sort_title(product):
    entries = series_entries(product)
    if entries:
        prefix = entries[0]['title']
        sequence = sequence_sort_key(entries[0]['sequence'])
        if sequence:
            prefix += ' - ' + sequence
        return '%s - %s' % (prefix, to_text(product.get('title')).strip())
    return to_text(product.get('title')).strip()


def summary(product):
    for key in ('publisher_summary', 'merchandising_summary', 'short_description'):
        value = text_field(product.get(key))
        if value:
            return clean_html(value)
    return ''


def clean_html(value):
    value = to_text(value)
    value = LIST_RE.sub(' • ', value)
    value = BREAK_RE.sub('\n', value)
    value = TAG_RE.sub('', value)
    try:
        from html import unescape
        value = unescape(value)
    except ImportError:  # Python 2
        try:
            from HTMLParser import HTMLParser
            value = HTMLParser().unescape(value)
        except Exception:
            pass
    value = value.replace('\r', '')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r' *\n *', '\n', value)
    return re.sub(r'\n{3,}', '\n\n', value).strip()


def best_image(product, requested_size=2000):
    candidates = image_candidates(product, requested_size)
    return candidates[0] if candidates else ''


def image_candidates(product, requested_size=2000):
    """Return deduplicated Audible cover URLs from preferred to fallback."""
    images = product.get('product_images')
    if not isinstance(images, dict):
        return []
    choices = []
    for key, value in images.items():
        try:
            size = int(key)
        except (TypeError, ValueError):
            size = 0
        url = text_field(value)
        if re.match(r'^https?://', url, re.I):
            choices.append((size, url))
    if not choices:
        return []
    choices.sort(reverse=True)
    try:
        requested_size = max(1, int(requested_size or 2000))
    except (TypeError, ValueError):
        requested_size = 2000
    output = []
    seen = set()

    def append(url):
        url = to_text(url).strip()
        if url and url not in seen:
            seen.add(url)
            output.append(url)

    source = choices[0][1]
    if 'm.media-amazon.com' in source and re.search(r'_SL\d+_', source):
        sizes = set([requested_size])
        sizes.update([
            size for size in (3000, 2000, 1000, 500)
            if size < requested_size
        ])
        sizes.update([
            size for size, unused in choices if 0 < size < requested_size
        ])
        for size in sorted(sizes, reverse=True):
            append(re.sub(r'_SL\d+_', '_SL%d_' % size, source))
    for unused_size, url in choices:
        append(url)
    return output


def unique_authors(products):
    output = []
    seen = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        for author in contributor_objects(product, 'authors'):
            key = (text_field(author.get('asin')), normalize_text(author.get('name')))
            if key in seen:
                continue
            seen.add(key)
            output.append({
                'asin': text_field(author.get('asin')),
                'name': text_field(author.get('name')),
            })
    return output
