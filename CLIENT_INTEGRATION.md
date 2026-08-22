# VocalisMeta player integration

This document is the client contract for applications that read a Plex music
library managed by VocalisMeta. It is written so it can be supplied directly to
another coding session implementing an audiobook player.

## Scope

VocalisMeta is a legacy Plex music metadata agent for audiobook libraries. It
runs inside Plex Media Server. It does not expose a separate REST service and
does not require an Audnexus service. A player reads the resulting metadata
through the normal authenticated Plex API.

The base recording contract is **Client Identity Contract v1**. The optional
literary-work extension is **Work Identity Contract v2**. The bundle's static
extended relationship and provenance layer is **Extended Player Metadata
Contract v3**. The bundle's static development version remains **0.1.0**.

The normative machine-readable files are:

- [`client-contract/metadata-contract-v1.json`](client-contract/metadata-contract-v1.json)
- [`client-contract/test-vectors-v1.json`](client-contract/test-vectors-v1.json)
- [`client-contract/metadata-contract-v2.json`](client-contract/metadata-contract-v2.json)
- [`client-contract/test-vectors-v2.json`](client-contract/test-vectors-v2.json)
- [`client-contract/metadata-contract-v3.json`](client-contract/metadata-contract-v3.json)
- [`client-contract/test-vectors-v3.json`](client-contract/test-vectors-v3.json)

VocalisMeta executes every published vector in its own test suite. Client
projects should run the same vectors in CI. The JSON contract is build-time
integration data; it is not a Plex service endpoint and is not written into
user-visible metadata.

The public product name changed from SpokenMeta to VocalisMeta without changing
the wire contract. The Plex provider remains
`com.plexapp.agents.spokenmeta`, and canonical book keys retain the
`spokenmeta:` prefix. Clients must not rewrite existing keys to a new brand
prefix.

## Plex hierarchy and field mapping

Use the music hierarchy as follows:

| Plex object or field | Audiobook meaning | Client use |
| --- | --- | --- |
| Artist | Primary author credit | Primary author pages and fast grouping |
| Album | One audiobook/edition | The playable book and progress owner |
| Track | One audio file or part | Playback queue and chapter fallback |
| `guid` | VocalisMeta identity | Cross-server book identity |
| `ratingKey` | Plex database row | Server-local lookup only |
| `parentRatingKey` / `parentTitle` | Primary author link | Navigate from book to artist |
| Mood with no reserved prefix | Author/co-author | Exact author relationship |
| `Series: <name>` Mood | Series membership | Exact series grouping |
| `Sequence: <name> #<position>` Mood | Series position | Ordering and “next in series” |
| `Language: <name>` Mood | Recording language | Display/filter when known |
| `Edition: Abridged` or `Edition: Unabridged` Mood | Recording edition | Display/filter when known |
| `Work-ID: openlibrary:<work-id>` Mood | Optional literary-work identity | Group recordings/editions; never own progress |
| `Contributor-ID: <role>:<source>:<id> = <name>` Mood | Optional stable person relationship | Merge provider-backed contributor spellings |
| `Work-Published: <year>` Mood | First publication year | Display separately from recording release |
| `Production: <type>` Mood | Explicit production type | Display/filter without cast-size inference |
| `Rating-Source: <source>` / `Rating-Count: <count>` Mood | Rating provenance | Interpret Plex album rating confidence |
| Style | Narrator or LibriVox reader | Narrator pages and filtering |
| Genre | Book genre | Genre browsing |
| `title_sort` | Provider/embedded series sort key | Plex-compatible album ordering |
| Poster | Cover artwork | Book artwork |
| Collection | User-managed Plex grouping | Leave untouched |

Do not interpret a raw Mood as an author before checking every reserved prefix:
`Series: `, `Sequence: `, `Language: `, `Edition: `, `Work-ID: `,
`Contributor-ID: `, `Work-Published: `, `Production: `, `Rating-Source: `, and
`Rating-Count: `. Contract v2 and v3 prefixes appear only when their configurable
preferences are enabled.

## Durable identity

### Why `ratingKey` is insufficient

Plex assigns `ratingKey` inside one server database. The same file on two Plex
servers usually has different rating keys, and rebuilding a library can assign
new ones. Therefore this is unsafe as a cloud identity:

```text
bookKey = ratingKey
```

Use the VocalisMeta album GUID when available. Keep server machine identity plus
rating key only as a fallback and as the address used for Plex API requests.

### GUID wrapper

A normal album GUID is:

```text
com.plexapp.agents.spokenmeta://B08G9PRS1K_us?lang=en
```

Plex may URL-encode characters and may append a model suffix such as `/-1`.
Parsing must:

1. Verify the provider is `com.plexapp.agents.spokenmeta`.
2. Take the identifier after `://`.
3. Remove the query beginning with `?`.
4. Remove an optional final `/-1` or `/number` model suffix.
5. URL-decode the identifier.
6. Match one identity form below.

Do not rely on a guessed `/region/ASIN` layout. VocalisMeta's actual Audible
identifier is `ASIN_region`.

### Book identity forms

| Identifier | Strength | Canonical cloud key |
| --- | --- | --- |
| `B08G9PRS1K_us` | Strong: exact Audible edition/store | `spokenmeta:audible:us:B08G9PRS1K` |
| `librivox:52` | Strong: exact LibriVox project | `spokenmeta:librivox:52` |
| `isbn:9780593135204` | Strong: valid embedded edition ISBN | `spokenmeta:isbn:9780593135204` |
| `local:0123456789abcdef` | Lower confidence: local evidence | `spokenmeta:local:0123456789abcdef` |

The ASIN is ten uppercase alphanumeric characters. The marketplace is one of
`au`, `ca`, `de`, `es`, `fr`, `in`, `it`, `jp`, `uk`, or `us`.

An ISBN identity is emitted only for a valid checksummed ISBN. ISBN-10 is
canonicalized to its ISBN-13 equivalent when possible.

A local identity is a deterministic 64-bit fingerprint of normalized title,
author, runtime rounded to five minutes, language, and abridgment evidence. It
allows unmatched local books to survive a Plex rebuild or appear as the same
book on another server when their evidence agrees. It may legitimately change
after fixing tags or edition evidence, so treat it as weaker than provider or
ISBN identity.

### Artist identity is not book identity

VocalisMeta can emit a name-backed artist GUID when Audible has no single author
record for a compound credit:

```text
com.plexapp.agents.spokenmeta://name:Kevin+J.+Anderson_us?lang=en
```

This has artist scope. Never use it for book progress, bookmarks, history, or
deduplication. It exists only to keep the Plex artist relationship stable.

### Parser pseudocode

```text
function vocalisMetaBookIdentity(guid):
    require provider(guid) == "com.plexapp.agents.spokenmeta"
    id = urlDecode(stripQueryAndModelSuffix(identifier(guid)))

    if id matches /^([A-Z0-9]{10})_(au|ca|de|es|fr|in|it|jp|uk|us)$/i:
        return "spokenmeta:audible:" + lower(region) + ":" + upper(asin)
    if id matches /^librivox:([1-9][0-9]*)$/i:
        return "spokenmeta:librivox:" + decimalId
    if id matches /^isbn:([0-9]{13})$/i and checksumIsValid:
        return "spokenmeta:isbn:" + isbn
    if id matches /^local:([0-9a-f]{16})$/i:
        return "spokenmeta:local:" + lower(hex)
    return null
```

If this returns `null`, use:

```text
plex:<serverMachineIdentifier>:<ratingKey>
```

Do not use `ratingKey` without the machine identifier.

### Progress migration

Store both the canonical identity and the current Plex address:

```text
canonicalBookKey = spokenmeta:audible:us:B08G9PRS1K
serverMachineId  = e45929718f1878aecb32fd457978379d37f3c42f
ratingKey        = 122344
```

Recommended migration when loading existing rows:

1. Fetch the album and parse its current VocalisMeta GUID.
2. If a canonical book key exists, look for progress under that key.
3. Otherwise look under `plex:machineIdentifier:ratingKey`.
4. If only a legacy raw-rating-key row exists, copy or move it to the best key.
5. Keep `machineIdentifier` and `ratingKey` as the current playback address,
   even after the cloud key becomes provider-backed.
6. If two old rows resolve to the same strong identity, merge deliberately:
   keep the furthest credible position, latest activity timestamp, union of
   bookmarks, and a completed state if either row is completed.
7. Do not automatically merge two different `local:` identities using title
   alone. Offer a user-visible merge if needed.

The same ASIN can represent regional catalog editions. Region is part of the
key intentionally; do not discard it. A later client-level equivalence layer
may relate editions using ISBN or explicit user confirmation without changing
the storage key.

## Relationship tags

### Authors

The primary author comes from the Plex album's parent artist. Additional
authors are raw exact Mood values such as:

```text
Terry Pratchett
Neil Gaiman
```

To find every book involving an author, combine:

- albums under the matching Plex artist;
- albums whose Mood exactly equals the author name.

Never treat reserved namespace Moods as authors.

### Series and sequence

VocalisMeta deliberately uses two Moods:

```text
Series: Discworld
Sequence: Discworld #5
```

The first remains an exact, stable grouping value. The second carries the
per-book sequence without corrupting exact series matching. Split a sequence
Mood at the final ` #` so series names can contain spaces and punctuation.

The position is a string and can be an integer or decimal, for example `5` or
`3.5`. Common provider forms such as `Book 5`, `Volume 05`, and `Book IV` are
normalized to `5`, `5`, and `4`. Parse a numeric value when possible, but keep
the original normalized string for display and future non-numeric positions.

One book may belong to multiple series. Keep every `Series:` and `Sequence:`
relationship. The first provider series controls `title_sort`, but the client
should build its own series ordering from matching sequence tags.

Series names are exact provider relationships, not fuzzy aliases. `Dune` and
`The Dune Sequence`, for example, stay separate unless authoritative source
data says otherwise. A compact UI may present the first relationship as the
primary series, but it should retain the remaining memberships rather than
silently merging them.

On a partial provider refresh, VocalisMeta preserves the last-known-good
author, series, sequence, language, edition, and valid Contract v3 values when
the current response omits that entire namespace. Non-empty fresh values
replace the old namespace. Clients should invalidate their cached projection
when Plex changes the item's metadata timestamp and then trust the new Plex
detail response; the agent-side preservation rule prevents incidental omission
from erasing a previously valid relationship.

VocalisMeta does not know a trustworthy series total. A client can calculate
“book 5 of 9 in this Plex library” from currently indexed members, but should
label that as library coverage rather than a publisher-defined total.

### Language and edition

Examples:

```text
Language: English
Edition: Unabridged
```

These are emitted only when provider or embedded-file evidence exists.
`Edition:` is currently `Abridged` or `Unabridged`. Do not infer an edition from
the absence of the tag.

### Narrators

Audible narrators, LibriVox readers, or enabled embedded contributor fallbacks
are stored as exact Style values. Multiple styles mean multiple narrators.

### Work identity versus recording identity

The album GUID and its Contract v1 canonical key identify the exact audiobook
recording or edition. They own progress, bookmarks, listening history, and
completion.

When **Store Open Library Work-ID Mood for Contract v2 audiobook players** is
enabled, VocalisMeta may also emit:

```text
Work-ID: openlibrary:OL12345W
```

After validation, the client canonical key is:

```text
spokenmeta:work:openlibrary:OL12345W
```

This is an authoritative Open Library Work match and may group editions,
languages, narrators, or providers that represent the same literary work. It
must not merge playback state: two recordings can have different duration,
chapter layout, abridgment, and narration. Treat a missing or invalid Work-ID
as unknown and do not manufacture one from title and author.

Contract v2 is enabled by default and can be disabled in the agent. When
enabled, it can cause a cached Open Library lookup during a Plex metadata
refresh for an album that lacks the tag. The resulting value is stored in Plex;
the player still communicates only with Plex and never needs Open Library access
or a companion service.

### Contract v3 extended player metadata

Contract v3 adds provider-backed metadata that is useful to an audiobook
player but has no dedicated legacy Plex music field. It is enabled by default
and can be disabled in the agent.

Contracts v2 and v3 are enabled by default but remain configurable. Existing
albums do not gain these fields until Plex refreshes their metadata. Work
identity, Open Library contributor IDs, and first-publication year require a
confident Open Library match. Audible and LibriVox contributor IDs require an
authoritative person identifier in the provider response; plain narrator Style
names are the expected fallback. Production requires an explicit provider
label, and rating source/count require usable provider rating data. Treat every
missing optional field as unknown.

Contributor identities use:

```text
Contributor-ID: author:audible:B00G0WYW92 = Andy Weir
Contributor-ID: author:openlibrary:OL2162289A = Andy Weir
Contributor-ID: narrator:librivox:20 = Ray Example
```

Split once at ` = ` to separate the stable role/source/identifier tuple from
the display name. Validate the source-specific identifier before using it.
Supported roles are currently `author` and `narrator`; supported sources are
`audible`, `openlibrary`, and `librivox`. Names remain display values and must
not be used as stable person keys.

After validation, form the provider-scoped contributor key as:

```text
spokenmeta:contributor:<role>:<source>:<identifier>
```

Do not merge two different provider-scoped keys solely because their display
names match.

`Work-Published: <year>` is the literary work's first publication year from an
authoritative Open Library match. Plex `originally_available_at` remains the
audiobook recording release date. Keep both values.

`Production:` is emitted only for explicit provider values such as `Full cast`,
`Dramatized`, or `Community recording`. Never derive it from the number of
narrators. A Plex album rating may be accompanied by `Rating-Source: Audible`
and `Rating-Count: <integer>`; do not interpret a count without a valid source.

All Contract v3 values come from Plex metadata. The player does not call
Audible, Open Library, Google Books, or LibriVox directly.

## Source precedence and trust

The identity/search order is:

1. Explicit LibriVox project identity supplied to Fix Match or filename.
2. Explicit Audible ASIN, followed by an embedded Audible ASIN.
3. Embedded LibriVox project identity.
4. LibriVox-first matching for media paths explicitly containing `librivox`;
   failure falls back to a stable local identity rather than Audible.
5. Unhinted recording matching according to the configured LibriVox mode:
   `hinted_only` uses Audible only, `fallback` tries Audible then LibriVox, and
   `preferred` tries LibriVox then Audible.
6. The other enabled recording provider when the selected mode permits it.
7. Embedded ISBN identity.
8. Deterministic local identity.

The provider search order does not change the stable identity format. A client
must key an accepted result from its parsed GUID, not infer identity from which
provider was searched first.

Audible or LibriVox remains authoritative for recording-specific metadata once
matched. Embedded series/authors/narrators fill only provider gaps when their
preferences are enabled. For an ISBN/local match, scanner and embedded values
are preserved.

Open Library and Google Books are enrichment providers, not recording match
providers. They may fill only missing descriptions, dates, genres, ISBN
relationships, or covers. They do not replace existing Plex values and do not
supply narrator, series, rating, collection, or recording identity.

Plex field locks remain authoritative. A client should not assume a refresh
will replace a value the user locked in Plex.

## Artwork

The album poster may come from:

- a local sidecar such as `cover.jpg`;
- embedded ID3 APIC, MP4/M4B `covr`, FLAC picture, or Vorbis picture data;
- Audible;
- LibriVox;
- Open Library or Google Books as a missing-cover fallback.

Use Plex's returned `thumb`/poster key and normal authenticated image endpoint.
Do not construct Amazon image URLs in the player. VocalisMeta validates remote
image content, retries transient failures, falls back through smaller Audible
sizes, and removes stale poster keys during refresh.

## Chapters and tracks

VocalisMeta does not manufacture chapters and does not rename tracks. A player
should resolve chapters in this order:

1. Plex chapter metadata when present.
2. Embedded M4B/MP4 chapter markers or other supported embedded chapters.
3. Track/file boundaries as the final fallback.

Progress belongs to the album identity, while the player may retain the active
track and intra-track offset needed to resume playback.

## Useful Plex requests

Use the server's normal `X-Plex-Token` authentication and follow keys returned
by Plex rather than constructing paths from titles.

```text
GET /identity
GET /library/sections
GET /library/sections/{sectionKey}/all?type=8&includeGuids=1
GET /library/metadata/{albumRatingKey}?includeGuids=1
GET /library/metadata/{artistRatingKey}/children
GET /library/metadata/{albumRatingKey}/children
```

Plex versions differ in whether the primary GUID appears as a `guid` attribute
or a `Guid` child. Support both. Prefer the GUID whose provider is
`com.plexapp.agents.spokenmeta`.

## Contract test vectors

The compact table below is provided for human readers. The complete normative
set, including invalid-provider, checksum, normalization, multiple-series, and
unknown-facet cases, is in
[`client-contract/test-vectors-v1.json`](client-contract/test-vectors-v1.json).
Contract v2 work-identity cases are in
[`client-contract/test-vectors-v2.json`](client-contract/test-vectors-v2.json).
Contract v3 contributor, date, production, rating, and malformed-value cases
are in
[`client-contract/test-vectors-v3.json`](client-contract/test-vectors-v3.json).

| Input | Expected result |
| --- | --- |
| `com.plexapp.agents.spokenmeta://B08G9PRS1K_us?lang=en` | `spokenmeta:audible:us:B08G9PRS1K` |
| `com.plexapp.agents.spokenmeta://librivox%3A52?lang=en` | `spokenmeta:librivox:52` |
| `com.plexapp.agents.spokenmeta://isbn:9780593135204/-1?lang=en` | `spokenmeta:isbn:9780593135204` |
| `com.plexapp.agents.spokenmeta://local:0123456789ABCDEF?lang=en` | `spokenmeta:local:0123456789abcdef` |
| `com.plexapp.agents.spokenmeta://name:Kevin+J.+Anderson_us?lang=en` | no book identity; artist scope |
| `local://122344` | no cross-server identity; use Plex fallback |

## Client implementation checklist

- Parse the VocalisMeta GUID before creating or updating cloud progress rows.
- Namespace all fallback Plex keys with the server machine identifier.
- Store the current server and rating key separately from the canonical book key.
- Migrate legacy raw-rating-key progress without losing bookmarks or completion.
- Exclude reserved Mood namespaces from the author index.
- If supporting Contract v2, validate `Work-ID:` and use it only for grouping.
- Never merge progress, bookmarks, completion, or history by work identity.
- If supporting Contract v3, reserve all five new prefixes before author parsing.
- Validate contributor IDs by source and treat their names as display values.
- Keep work publication year separate from Plex's recording release date.
- Never infer production type from narrator or track count.
- Pair `Series:` with every matching `Sequence:` tag; support multiple series.
- Display language and abridgment only when their Mood exists.
- Read narrator names from Style.
- Treat Plex collections as user data and do not derive series from them alone.
- Use Plex poster URLs and authentication rather than provider image URLs.
- Keep chapter resolution in the player; do not depend on agent-created tracks.
- Test the six identity vectors above and cross-server rating-key collisions.

These contracts are additive. Existing Audible and LibriVox identifiers do not
change, and Contracts v2 and v3 do not reinterpret Contract v1 recording keys.
Future changes should introduce a documented new contract version rather than
silently changing an existing version.
