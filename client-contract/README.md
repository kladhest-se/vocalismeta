# VocalisMeta client contract

This directory is the machine-readable companion to
[`CLIENT_INTEGRATION.md`](../CLIENT_INTEGRATION.md). Audiobook players can use
the files as build-time input or copy them into their own test suite. They are
not loaded by Plex and do not add control values to user-visible metadata.

- `metadata-contract-v1.json` defines the stable GUID, canonical-key, Plex
  field, relationship namespace, progress, artwork, and chapter contracts.
- `test-vectors-v1.json` contains identity and relationship examples that a
  compatible player parser must pass.
- `metadata-contract-v2.json` is an additive, configurable extension for an
  authoritative literary-work identity stored in a Plex Mood.
- `test-vectors-v2.json` defines valid, missing, and malformed work-identity
  behavior.
- `metadata-contract-v3.json` defines optional contributor identities, original
  publication year, explicit production type, and rating provenance.
- `test-vectors-v3.json` contains valid provider metadata and malformed-value
  cases for a player parser.

Version 1 is additive and immutable. Version 2 extends it without changing the
recording identity or progress contract. A future incompatible interpretation
must be introduced in a new versioned file instead of changing an existing
version silently.

Contract v2 is enabled by default and can be disabled in the agent. A compatible
player must treat `Work-ID: openlibrary:<work-id>` as a reserved Mood, exclude it
from the author index, and use it only to group editions or recordings. Playback
progress, bookmarks, and completion remain owned by the Contract v1 recording
identity.

Contract v3 is also enabled by default and can be disabled. Its five additional
Mood prefixes are reserved when enabled and must not enter the author index.
Provider identities, production type, and publication year are emitted only
from explicit provider data. When Audible exposes a narrator name without a
person ID, VocalisMeta may also emit the documented deterministic `name`-source
narrator fallback. That fallback is portable but not authoritative.
The data is stored in Plex, so a compatible player still needs access only to
Plex.

Relationship names are exact. Clients must not fuzzy-merge two provider series
such as `Dune` and `The Dune Sequence`; the first provider relationship is the
primary series and the remaining exact memberships are still valid. During a
partial provider refresh, VocalisMeta preserves a previously valid
relationship namespace when the current response omits that namespace. Fresh
non-empty values replace the previous namespace.

VocalisMeta's own tests execute every published vector; run
`python3 -m unittest discover -s tests -v` from the repository root. See
[development instructions](../DEVELOPMENT.md) for coverage and limitations.
A player such as
[VocalisBook](https://github.com/kladhest-se/vocalisbook) should run the same
vectors in its CI so agent and client changes cannot drift apart unnoticed.


Additional compatibility vectors are in
[`unicode-identity-vectors-v1.json`](unicode-identity-vectors-v1.json). They freeze
raw Unicode-scalar fingerprints, normalized narrator-name fingerprints, and local
book examples. Run `python3 tests/test_unicode_identities.py` (or Python 2.7) from
the repository root. These vectors supplement the existing v1/v2/v3 contracts;
they do not change the provider-ID, recording key, or progress-owner formats.


## Optional Contract v4 (client-first rollout)

[metadata-contract-v4.json](metadata-contract-v4.json) defines independent content
revisions, exact/primary series, field provenance/availability, explicit clears,
and recording-upgrade review declarations. [test-vectors-v4.json](test-vectors-v4.json)
contains 20 positive cases and 6 invalid transport mutations. [fixtures/v4](fixtures/v4/)
contains synthetic normal Plex JSON/XML detail responses and a disabled legacy
response. All cases execute offline. See [the specification](../docs/CLIENT_CONTRACT_V4.md)
and [VocalisBook handoff](../docs/VOCALISBOOK_V4_HANDOFF.md).

V4 is disabled by default. Every client must reserve `VocalisMeta-v4: ` from author
parsing before a user enables it. Existing GUIDs, provider IDs, canonical recording
keys and v1–v3 semantics remain unchanged. There is no app/service/provider access
requirement. A verified declaration is still a proposal requiring explicit client
confirmation, never authority to merge listening state automatically.
