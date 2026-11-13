# Per-book metadata and match diagnostics

## Optional `vocalismeta.json`

Place a UTF-8 JSON file named `vocalismeta.json` beside a book's audio files.
It is optional and does not require a companion service. Example:

```json
{
  "schema_version": 1,
  "identity": {"provider": "audible", "id": "B08G9PRS1K", "region": "us"},
  "metadata": {
    "title": "My preferred title",
    "authors": ["Author Name"],
    "narrators": ["Narrator Name"],
    "series": [{"title": "Series Name", "sequence": "2.5"}],
    "language": "en",
    "abridged": false,
    "publisher": "Publisher Name",
    "release_date": "2026-01-15",
    "summary": "My description.",
    "genres": ["Fiction"]
  },
  "artwork": {"file": "cover.jpg"}
}
```

Only `schema_version` is required. Omit any other field you do not want to
control. Examples use illustrative values; replace the book identity and metadata.
Unknown keys, invalid IDs, dates, or types reject the entire sidecar and log a
warning; ordinary matching then continues. The maximum file size is 256 KiB.
Names/genres are arrays of up to 32 nonblank strings. Series has up to eight
objects with `title` and optional string `sequence`. Text must be nonblank;
summary/text fields allow up to 32,768 characters. An empty array explicitly
clears that author/narrator/series/genre list.

Sidecar metadata supplies search hints and is applied after provider/local
updates, so explicit values take precedence over those sources. Omitted values
retain normal behavior. Agent preference switches still control which
relationship tags are emitted. Plex field locks remain server-owned and need
live validation; no new guarantee about locked-field behavior is claimed here.
When explicit author/narrator names replace provider names, stale provider person
IDs are removed. Narrators receive portable name-based IDs when v3 is enabled.

`identity` controls the next search/Fix Match, not an existing book's GUID.
After changing it, use **Fix Match** to select the intended recording. Supported
identity objects are:

| Provider | Required fields | Optional fields |
| --- | --- | --- |
| `audible` | `id`: ten-character ASIN | `region`: supported Audible region |
| `librivox` | `id`: decimal project ID as a string | None |
| `ljudboksarkivet` | `slug`: final `/ljudbok/` path component, e.g. `book-name` | None |
| `isbn` | `id`: ISBN with valid checksum | None |
| `local` | None; identity is calculated from book evidence | None |

LibriVox and Ljudboksarkivet must be enabled in agent settings before explicit
lookups use them. An unavailable explicitly requested recording produces no
unrelated replacement match. Explicit `local` and `isbn` identities skip Swedish
catalogue rematching during refresh. To remove an identity override, remove the
`identity` object and use Fix Match again.

Artwork must be an existing supported image within the same book directory or a
subdirectory; absolute paths, external URLs, and symlinks escaping the directory
are rejected. Supported signatures are JPEG, PNG, and WebP, with the existing
32 MiB artwork limit. Images now have structure, dimension, pixel-count, and aspect checks. When PIL is
available in the runtime, they are also verified and fully decoded; see below.

For multipart books, one sidecar beside any part applies to the book. If several
part directories contain sidecars, their validated contents must agree; conflicting
files reject all overrides for that operation. A sidecar is not searched for in
parent folders, so place it beside a part rather than only beside disc directories.
Keep separate books in separate directories.

## Retaining Swedish recording selections

The agent records candidate slugs in Plex's persistent plug-in `Dict` storage,
scoped to the server-local media ID (or first audio path when no media ID exists)
and portable ISBN/local recording identity. A selected descriptive result label
resolves candidates that share an ISBN. Once resolved, future updates fetch the
exact stored slug instead of repeating a title search. The public GUID, canonical
client key, and progress owner remain unchanged.

If the saved page is unavailable or now identifies another recording, metadata
is preserved; a broader search is not silently substituted. Use Fix Match, or a
sidecar with an explicit Swedish slug, to select a replacement. If candidates are
ambiguous, the agent preserves metadata until an unambiguous selection is made.
Existing matches without stored locators use the ordinary search once, then save
an accepted locator. Disabling the provider pauses lookups. Removing plug-in data,
recreating a library, or changing the fallback audio path can lose the local
selection; these records are not a cross-server identity mechanism.

## Reading match decisions

Temporarily choose DEBUG logging, repeat a search, and run:

```bash
python3 scripts/explain-matches.py "/path/to/com.plexapp.agents.spokenmeta.log"
python3 scripts/explain-matches.py "/path/to/agent.log" --json
```

`MATCH_CANDIDATE` records show provider, region, title agreement, author agreement,
runtime difference, final score, threshold, and acceptance/rejection reason.
`unknown` means evidence was unavailable. Audible's candidate threshold shown is
its automatic threshold (80); Fix Match can show lower-confidence suggestions.
Adult/preorder filters and author conflicts have explicit reasons. Exact ID
lookups have no similarity ranking; the existing search summary records their
selection. Library-level filters and provider failures can stop candidate
inspection altogether. Logs contain book titles; review them before sharing.

## Search request and time budgets

Agent settings default to **24 HTTP attempts** and a **90-second network deadline**
per album search, including retries and local Plex runtime-tree requests. Each
request's timeout and retry sleep are limited by the remaining time. Config JSON
keys are `network.search_request_budget` (12/24/48) and
`network.search_timeout_seconds` (30/60/90/180). The deadline prevents further
network work; local file parsing and a networking implementation's timeout
behavior may add overhead. It is not a hard process-interruption deadline.

After three consecutive failed logical HTTP requests to a host, transient failure
backoff skips that host for 60 seconds. Successful requests and non-transient
HTTP failures reset its failure count. Other hosts can still be used. Cooldowns
are process-local; restarting the plug-in resets them. Budget exhaustion and
cooldown skips are recorded as provider failures, rather than evidence that a
book does not exist. `SEARCH_BUDGET` records show attempts used and exhaustion.
The existing enrichment request budget remains separate. Album refresh artwork
and enrichment are not claimed to be bounded by this search-only deadline.


## Local validation (`doctor`)

The following commands only read local files. They do not contact Plex/providers,
look up 1Password secrets, push source, or publish releases:

```bash
python3 scripts/vocalismeta.py doctor
python3 scripts/vocalismeta.py doctor --config /etc/vocalismeta/config.json
python3 scripts/vocalismeta.py doctor --book "/path/to/Author/Book" --artwork "/path/to/cover.jpg"
python3 scripts/vocalismeta.py doctor --release-config "$HOME/Development/tools/git-release/projects/vocalismeta.json" --json
```

The doctor validates strict configuration/secret-file readability without printing
secret contents, sidecar schema and artwork paths, multipart tag consistency,
release destination/reference syntax, and requested image decoding. An unset token
reference is a warning; remote access and 1Password resolution remain unverified.
Errors return exit status 1; warnings alone return 0. Book directories are scanned
for at most 256 audio files; give a single book, not a whole library. A directory
containing only a sidecar can be validated before its audio is copied in.

## Previewing updates

Enable **Preview album updates without changing metadata** in agent settings, or
set `metadata.preview_updates` to `true` in the main configuration. Then refresh an
album. Provider lookups and local artwork reads still occur, but updates run on an
isolated draft: scalar fields, genre/narrator/relationship lists, and poster keys
are not written to the original metadata, and saved recording selections are not
changed. Artist updates are outside this album-only preview mode.

A single-line `METADATA_REPORT` JSON record in the agent log contains `before`,
`after`, and a per-field `changes` map, including artwork key changes. Reports
include titles, descriptions, and identities; keep logs private as appropriate.
Extract the latest report (optionally filter by metadata identity):

```bash
python3 scripts/vocalismeta.py report --log "/path/to/agent.log" --output preview.json
python3 scripts/vocalismeta.py preview --before before.json --after after.json
```

Review the report, disable preview mode, and refresh again to apply normal
updates. That refresh fetches current evidence; it does not apply a frozen or
approved report. Real Plex behavior and field locks remain deferred for live
validation. The preview/report is not a backup of the Plex database.

For export snapshots during ordinary applied updates, enable **Record album
metadata snapshots for offline export**, or `metadata.reports: true`. Both
settings default to false. A normal report records changes after applying them;
only preview mode prevents album writes.

## Portable export

Export an extracted report, a metadata snapshot, or saved single-album Plex XML:

```bash
python3 scripts/vocalismeta.py export --input preview.json --output vocalismeta.json
python3 scripts/vocalismeta.py export --input album.xml --output vocalismeta.json
```

The exporter runs the production sidecar validator before writing, refuses to
replace an existing file unless `--overwrite` is given, and supports `--output -`
for review on stdout. Copy the reviewed file beside the intended book's audio;
export itself does not modify a library. XML must contain exactly one album.
XML entity declarations are rejected. Input files/logs are limited to 32 MiB;
trim a large log to the relevant refresh before extracting a report.

Export includes supported title, summary, publisher/date, author/narrator names,
genres, series/sequence, language/edition, and a supported provider identity when
available. Saved Swedish locators are retained in agent reports. Source-only
local fingerprint IDs are exported as `provider: local`, so they are recomputed
from the destination book's evidence; they are not force-assigned identifiers.
Unknown author relationships are omitted rather than guessed. A saved XML's album
artist supplies the author only when no author Mood is available. Artwork URLs,
image bytes, ratings, progress, bookmarks, field locks, Work-ID, and unsupported
provider details are not exported. Inspect provider IDs before using Fix Match.

## Multipart conflicts

Different nonempty ASINs, regions, LibriVox IDs, ISBN evidence, language, edition,
series names, or series positions produce `MULTIPART_CONFLICT` log records.
Missing values are unknown rather than conflicts. ISBN-10/13 equivalents and
common language aliases are normalized; overlapping ISBN lists are compatible.
Contradictory embedded values are cleared from combined matching evidence.
Automatic matching stops until the files are reviewed. Manual matching remains
available with warnings; an explicit sidecar identity is authoritative. Explicit
sidecar language/series/edition overrides resolve their corresponding conflicts.
This detects inconsistent tags, not acoustic differences or missing chapters.

## Artwork verification

All incoming local, embedded, and remote candidates receive bounded structural
checks and dimensions. Limits are 32 MiB encoded, 10,000 pixels per axis,
25 million pixels total, and width/height from 0.33 to 3.0. Extreme banners are
rejected; images below 200 pixels on either axis are reported by the doctor as
low resolution. Animated WebP is not accepted as cover art.

When PIL/Pillow is available, `verify()` and a fresh `load()` reject corrupt
compressed image data. Full offline decoding can be enabled in an isolated
Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/vocalismeta.py doctor --artwork cover.jpg
```

The Plex bundle does not install packages into the server; it uses its installed
PIL if available. Without a decoder, PNG checks include CRC/decompression/filter
structure, while JPEG/WebP receive container/dimension checks only. Such a result
is explicitly marked `decoded: false`; it is not proof of full image decoding.
`doctor --artwork` requires a decoder and returns an error if unavailable.
