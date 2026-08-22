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
Values are emitted only from explicit provider data: no person identifier,
production type, or publication year is manufactured from a name, cast size,
title, or filename.
The data is stored in Plex, so a compatible player still needs access only to
Plex.

Relationship names are exact. Clients must not fuzzy-merge two provider series
such as `Dune` and `The Dune Sequence`; the first provider relationship is the
primary series and the remaining exact memberships are still valid. During a
partial provider refresh, VocalisMeta preserves a previously valid
relationship namespace when the current response omits that namespace. Fresh
non-empty values replace the previous namespace.

VocalisMeta's own tests execute every published vector. A player such as
[VocalisBook](https://github.com/kladhest-se/vocalisbook) should run the same
vectors in its CI so agent and client changes cannot drift apart unnoticed.
