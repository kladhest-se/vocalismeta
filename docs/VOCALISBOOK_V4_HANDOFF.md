# VocalisBook handoff: optional VocalisMeta Client Contract v4

No VocalisBook code or listening database was modified. This is the implementation
handoff for a future compatible client. V4 emission is off by default.

## Read and validate

1. Fetch the full album detail from normal Plex, e.g.
   `GET /library/metadata/{ratingKey}?includeGuids=1`, using existing Plex auth.
2. Parse the album's existing VocalisMeta GUID into its v1 canonical recording
   key. Do not change GUID syntax or drop the Audible region.
3. Before building author indexes, exclude every Mood beginning
   **`VocalisMeta-v4: `**, even if the client will not parse v4.
4. Collect v4 chunks from JSON `Mood[].tag` or XML `Directory/Mood/@tag`.
   Reassemble and validate as specified in [CLIENT_CONTRACT_V4.md](CLIENT_CONTRACT_V4.md).
   The reference `contract_v4_core.decode_for_recording(moods, guid_or_key)` also enforces
   recording-key binding. The lower-level `decode()` returns null for no envelope and
   raises ValueError for an invalid one. Apply no partial packet.
5. Bind `recording_key` to the independently parsed album key. Ignore a packet
   with a mismatched key. For null/unknown identity retain normal v1 Plex fallback.
   The digest is integrity checking, not a signature from a trusted authority.

Normative inputs: [contract](../client-contract/metadata-contract-v4.json),
[20 positive and 6 negative transport vectors](../client-contract/test-vectors-v4.json),
and [Plex JSON/XML fixtures](../client-contract/fixtures/v4/). Run each published
case in the client suite. The disabled fixture is a normal v1–v3 response.

## Exact fields to consume

| Payload path | Client behavior |
| --- | --- |
| `revisions.metadata` | Compare to the last valid `sha256:…`; rebuild published metadata/relationships when it changes |
| `revisions.artwork` | Compare independently; invalidate the cover cache even if Plex thumb/provider key is unchanged; null means no accepted input is known |
| `fields.series.value.primary_ref` | Resolve against memberships[].ref; null means no trustworthy primary selection |
| `fields.series.value.memberships[]` | Keep every exact title/normalized sequence and any supplied `{source,scope,id}` provider_id |
| `fields.<name>.state` | `known`, `unknown`, `unavailable`, or `cleared`; never map omission to clear |
| `fields.<name>.stale` | Label retained older data; do not pretend it came from a fresh successful lookup |
| `fields.<name>.provenance` | Per-field source/evidence; display manual/tag/ISBN/provider labels without scores or probabilities |
| `match` | Overall matching method; do not use it as the provenance for every field |
| `fields.recording_date.provenance.date_kind` | Distinguish actual recording release input from manual/literary-date fallbacks |
| `fields.contributors.value[]` | Valid v3 contributor tags; parse role/source/id, retaining non-authoritative name fallbacks |
| `cleared_namespaces[]` | Remove only the specified agent-owned work/extended relationship projection, not user collections or artist rows |
| `identity_upgrades[]` | Offer an evidence-aware migration review; never automatically merge listening state |

`fields.authors` represents author/co-author Moods; the album's native Plex parent
artist remains a separate primary-author relationship. Explicit namespace clearing
must not delete that artist. Series relationship refs are not authoritative series
IDs; use supplied provider IDs or exact display relationships, never fuzzy names.
There is no publisher series total. A narrator `name` fingerprint is not a provider
person ID. Raw source IDs are retained; do not merge different providers/regions
because spellings match.

## Refresh/cache flow

After the app requests a normal Plex refresh, fetch/poll album detail using the
existing server mechanism. V4 adds no refresh-job RPC or completion timestamp.
An unchanged revision means no changed semantic input was published; it is **not
proof an asynchronous refresh has completed**. Use native Plex status where
available, otherwise bounded polling and an honest timeout/unavailable indication.
Do not force a revision change merely to signal job completion.

```text
on fresh album detail:
    native = parse existing Plex/v1-v3 fields
    packet = fully validate optional v4; bind its key to the album GUID
    if absent or invalid:
        retain last valid v4 information as unavailable
        use normal native/Plex refresh behavior; do not invent clears or aliases
    else:
        if packet.revisions.metadata != cached.revisions.metadata or native fields changed:
            rebuild book/relationship projection using explicit field states
        if packet.revisions.artwork != cached.revisions.artwork:
            invalidate/reload cover through Plex
        always update provenance/availability/stale indicators
        offer upgrade review when a relevant declaration exists
```

Do not skip provenance/status parsing because both revision strings stayed the
same: provider failures intentionally retain revisions. Unknown/unavailable keeps
valid prior cache information; a deliberate `cleared` tombstone removes the
corresponding owned projection. Native fields/updatedAt remain authoritative, especially for external/manual
Plex edits or field locks. Rebuild the native projection when those values change
even if the last agent revision is unchanged; do not override native values with
a mismatched v4 snapshot or keep its provenance label as fresh. Keep last-known
values separately when marking a field unknown/unavailable. Native thumb remains
useful for external/manual Plex artwork changes. Artwork digests describe the agent's
accepted original image input, not the transcoded bytes returned by Plex. Do not
compare a resized image download's hash against this revision.

## Listening-state migration safeguards

A verified declaration requires a previously observed local recording key and an
exact-confirmed Audible/LibriVox key with the same explicit recording ID present
in both stored profiles, without known language/abridgment/runtime/narrator/ID
conflicts. Runtime tolerance is max(60 seconds, 0.5% of the shorter known runtime).
Different strong identities, different Audible regions/editions, ISBN alone,
titles, works, and contributor identities never create verified equivalence.
Historical proof is not retroactively invented when v4 is first enabled.

Even `verified_same_recording` includes `requires_client_confirmation:true`.
Show previous/current recording keys, evidence/reasons, known recording details,
and the saved states under each key. A `review_required` declaration is explicitly
not verified equivalence. Ask the user before any move/copy/merge. Preserve the
original state or a recoverable backup; do not silently overwrite newer progress,
completion, history, or bookmarks. Resolve track/chapter position conflicts in the
client with user review. Never migrate via work grouping, series, or person IDs.
Keep region in all Audible recording keys. Agent code does not touch app storage.

## Rollout and verification limits

Deploy the prefix reservation and parser in **all** readers first. Only then let
users enable agent preference `store_client_contract_v4` / JSON
`metadata.client_contract_v4`. Refresh a small test library before broader use.
Older readers can otherwise mistake chunk tags for authors. Missing v4 after a
rollback/disable is not a mass deletion instruction. Native v1–v3 behavior is
preserved when v4 is off. Oversized/invalid publications leave v4 unavailable,
retain prior private state, and do not suppress ordinary native metadata updates.

Offline producer, parser, simulated-agent, migration and fixture tests are
provided. Real Plex transport/field locks/provider calls and actual Python 2
execution remain deferred/unverified. No release or repository push is part of
this change.
