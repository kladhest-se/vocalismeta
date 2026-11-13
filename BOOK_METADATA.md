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
32 MiB artwork limit. Header validation does not prove the image fully decodes.

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
