# Client Contract v4: refresh, provenance and recording upgrades

V4 is optional, additive, and **disabled by default**. It publishes only through
normal Plex album Mood tags. V1 GUIDs, provider IDs, canonical recording keys,
work grouping, v1–v3 fields, and application listening databases are unchanged.
No new endpoint, service, provider credentials, or app-to-provider requests exist.
The normative definition is [metadata-contract-v4.json](../client-contract/metadata-contract-v4.json),
with [vectors](../client-contract/test-vectors-v4.json), [Plex JSON/XML fixtures](../client-contract/fixtures/v4/),
and a dependency-free reference encoder/parser in `contract_v4_core.py`.

## Client-first rollout

Older readers interpret unfamiliar Mood tags as author names. **Update every
reader to reserve `VocalisMeta-v4: ` before enabling emission.** Supporting the
prefix without parsing its payload is safe: exclude it from author indexing and
continue with v1–v3. Enable **Emit optional Client Contract v4** only when all
readers are compatible, or set `metadata.client_contract_v4` to `true` in agent
JSON settings, then refresh albums. Both preference/config defaults are false. This is an agent preference, not a
new per-library permission boundary: update all readers before enabling it, then
start with a small refreshed library or an isolated test deployment.
Disabling v4 removes its own tags on the next update. Missing or disabled v4 is
unsupported/unknown, not an instruction to erase old app data or listening state.
The v1/v2/v3 machine-readable files retain their previous semantics.

## Exact transport and parsing

Each `Mood.tag` (JSON) or `Mood/@tag` (XML) begins:

```text
VocalisMeta-v4: <sha256-hex>:<index>/<count>:<segment>
```

Indexes start at 1. Collect every owned tag from a **full album detail response**;
returned tag order is irrelevant. Require one consistent digest/count, no duplicates,
every index, count at most 64, and segments at most 384 base64url characters.
Concatenate segments in index order, restore base64 padding, decode base64url,
and zlib-decompress with a hard 16,384-byte output limit. Reject unused/trailing
compressed input or an incomplete stream. The SHA-256 header is over the
uncompressed canonical JSON, not compressed bytes. Verify the complete envelope,
canonical representation, schema, enum values, refs, and upgrade safeguards before
using any of it. JSON duplicate keys are invalid. Partial/corrupt/mixed/unsupported
payloads are unavailable: keep the last valid projection and fall back to v1–v3.
Never treat their tags as authors. Do not combine chunks from different responses.

Canonical JSON normalizes string values to NFC, requires ASCII schema object keys,
and sorts those keys lexicographically. It
escapes non-ASCII with lowercase JSON Unicode escapes (surrogate pairs for non-BMP
characters), and uses no whitespace after commas/colons. Values are null, booleans,
integers, text, arrays, or objects; floats/runtime objects are prohibited. Negative
zero is not emitted. The encoded bytes are ASCII. Slash characters are not escaped; control characters use standard JSON short
escapes where defined, otherwise lowercase Unicode escapes. Compression is zlib/RFC1950;
compressed bytes need not be identical across zlib implementations. Integrity is
not authentication: Plex metadata can be edited by a server user. Bind
`recording_key` to the album's independently parsed v1 GUID before accepting data.

## Envelope fields

- `contract_version`: integer 4.
- `recording_key`: existing v1 canonical key, or null when unavailable.
- `revisions.metadata` and `revisions.artwork`: independent cache validators.
- `match`: overall `{method, source, evidence}` describing the accepted search
  receipt. Unknown historic matching remains unknown; an exact product lookup
  during refresh does not retroactively prove how the original search matched.
- `fields`: per-field `{state, value, stale, provenance, reason?, identity_evidence?}`.
- `cleared_namespaces`: explicit removals of owned work/extended namespaces.
- `identity_upgrades`: bounded verified/review declarations, always requiring
  client confirmation.

Important fields are `title`, `authors`, `narrators`, `series`, `recording_date`,
`language`, `edition`, `work`, `work_publication`, `contributors`, and `artwork`.
Other native published values (summary, studio, title_sort, genres, rating) also
participate in metadata revision computation but remain available in normal Plex
fields. Author arrays correspond to author/co-author Moods; the native primary
Plex parent artist remains separate. An author-namespace clear must not delete
that artist or unrelated user data.

Sources/evidence are closed categories in the JSON definition. Useful labels:
`manual/manual_override` → “Manual override”; `embedded_tags/embedded_tags` →
“From local tags”; `openlibrary/isbn_match` → “Matched by ISBN”; provider source
with `provider_match` → “From [provider]”. `explicit_identifier` means an exact
identifier-backed provider lookup; it is not a calibrated score or probability.
Unknown evidence must stay unknown. Overall match evidence and each field's
provenance are independent. A matched Audible recording can have embedded series,
manual title, Open Library work grouping, and local cover artwork.

`contributors.value` contains validated v3 Contributor-ID strings. Parse each
role/source/id using v3 rules. A `name` narrator fingerprint is explicitly
non-authoritative. `authors/narrators.identity_evidence` is an aggregate hint;
when mixed identities exist, inspect each contributor rather than applying that
hint to every person. `recording_date` mirrors the native Plex date; its optional
`provenance.date_kind` distinguishes true recording-release input, manual input,
LibriVox copyright-year fallback, Open Library work-year fallback, and Google
Books book-edition date fallback. Do not relabel a literary fallback as a verified
recording release. This documents existing v1–v3 date behavior without changing it.

## Revisions and availability

`metadata` is `sha256:` plus the digest of canonical semantic values, deliberate
field tombstones, and the whitelisted native fields. Authors, narrators, genres,
contributors, and legacy Moods are NFC deduplicated sets, sorted by canonical
escaped JSON bytes (independent of narrow/wide Unicode storage). Series includes an explicit
primary reference and exact secondary memberships sorted by relationship ref.
Native ratings are quantized to six decimal places and represented as trimmed
decimal strings. Incidental Mood/JSON order, refreshed timestamps, request errors,
URLs, private paths, credentials, scores, and freshness status are not inputs.

`artwork` is `sha256:` plus the digest of the accepted **primary image input bytes**,
or null when never known. The agent chooses the successful retained candidate
with the lowest artwork sort preference; the last wins ties (explicit sidecar
artwork is applied last). Alternate candidates do not control this revision.
The digest identifies the agent's accepted input, **not Plex's resized/transcoded
image bytes**. Same URL/key with new accepted bytes changes it. Provider failure
retains the previous valid revision. Images manually changed outside the agent
cannot be byte-verified by this mechanism; native Plex thumb/cache signals still
matter, and a missing revision requires normal Plex fallback.

| state | Meaning | Client behavior |
| --- | --- | --- |
| `known` | A value is published; `stale=true` marks retained older evidence | Display/use it; show retained/source information where useful |
| `unknown` | No supported/known value, or no source history | Do not interpret omission as deliberate removal or a negative fact |
| `unavailable` | Lookup temporarily failed; a retained value may still exist | Keep retained/client values, label stale if applicable, retry later |
| `cleared` | Deliberate empty tombstone | Remove only the corresponding agent-owned cached projection |

Tombstones persist until superseded by fresh known values. Empty provider arrays
alone do not prove deliberate deletion. Manual sidecar empty lists, rejected work
relationships, and disabled author/series/v2/v3 namespaces provide explicit clear
reasons. Work rejection removes its work/year/Open Library author relationship
namespace while retaining independently sourced contributors/recording data.
V4-off has no envelope in which to emit tombstones: absence alone never clears.

Fetch a complete album detail response after native Plex changes. Compare metadata
and artwork revisions independently: metadata change rebuilds the book/relationship
projection; artwork change invalidates the image cache even at the same URL.
Always inspect availability/provenance on the fresh response even if revisions
are unchanged—health/staleness can change without semantic data changing. Do not
cache a broken packet as a deliberate clear. No timestamp token churn is required.

## Series references

`series.value` is `{primary_ref, memberships}`. Every membership has `ref`, exact
NFC `title`, and normalized string `sequence` (fractional values remain strings).
An actual supplied Audible series ASIN adds
`provider_id: {source:"audible", scope:"us", id:"…"}`. Scope is the region, and
IDs in different scopes are not automatically equal. A supplied same-provider
Ljudboksarkivet `/bokserie/<slug>` link adds source `ljudboksarkivet`, empty scope,
and that exact safe slug. External links and display names do not manufacture IDs.
Missing IDs stay absent.

`relationship:<sha256>` is a local relationship reference over canonical
`{title, sequence, provider_id?}`; it is **not an authoritative series identifier**.
Use it to resolve `primary_ref` within this envelope, not to claim cross-provider
series equivalence. The first fresh provider relationship is primary; explicit
manual/embedded selection can supply primacy. Partial refreshes retain known
prior v4 primacy. An initial legacy Mood-only set has `primary_ref:null`, because
returned Mood order is not evidence. Keep every exact secondary relationship;
never fuzzy-merge similarly named series. No publisher-defined series total is
invented. Library coverage must be separately labelled as local coverage.

## Recording upgrade safeguards

An upgrade declaration has previous/current **existing canonical recording keys**,
`status`, categorical `evidence`, `reasons`, and
`requires_client_confirmation:true`. The previous key must have been observed in
the same server-local media scope; no alias is inferred retroactively from a
similar title, work, contributor, or progress position.

Only local→exact-confirmed Audible/LibriVox transitions can be
`verified_same_recording`, and require the **same explicit ASIN plus region**, or
**same explicit LibriVox project**, in both stored recording profiles. Known
language, abridgment, narrator, runtime, recording-ID, or multipart conflicts
reject verification. Runtime tolerance is max(60 seconds, 0.5% of the shorter
known runtime), accounting for rounding—not a similarity confidence score.
Later observed conflicts downgrade retained declarations to `review_required`.
ISBN alone, newly added identifiers with no previous proof, and different strong
identities/regions/editions are review cases. V4 must have observed the weak state
beforehand; lost plug-in data or a different media scope cannot manufacture proof.

**Even verified declarations do not authorize automatic migration.** VocalisBook
should show old/new recordings, evidence/conflicts, durations, and existing saved
states; require explicit user confirmation. On confirmation, preserve originals
or a recoverable backup, avoid overwriting newer state, and resolve conflicts in
progress/bookmarks/completion deliberately. Work grouping and contributor keys
never own listening state. The agent never reads or modifies any application's
listening database, never rewrites the Plex GUID to create an alias, and never
merges different Audible regions automatically.

## Validation limits

All published vectors, malformed transport cases, and synthetic client-facing
Plex XML/JSON fixtures run offline. Preview mode computes v4 only on the isolated
metadata draft and does not persist state/evidence/revisions. Existing v1–v3 tests
remain required. Actual AgentKit tag transport, Plex field locks, provider services,
and Python 2 execution remain unverified; real Plex testing is still deferred.

If a new publication is invalid or exceeds the payload limit, no partial/old-key
envelope is emitted; native metadata updates continue and prior private evidence
is retained for retry. Treat that response as v4 unavailable, never a clear.


Native Plex fields remain authoritative if a locked field or external manual edit
makes them differ from the agent's last snapshot. A v4 metadata revision describes
the agent publication, not a read-back acknowledgement of all server field writes.
Clients must also honor observed native field/updatedAt changes, rebuild changed
native values even with an unchanged v4 token, and mark mismatched provenance as
unknown/stale rather than overwriting native values from a packet. This cannot be
fully exercised until deferred AgentKit/field-lock validation is performed.
