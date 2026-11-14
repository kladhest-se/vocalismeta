# Changelog

## 0.1.1 - Unreleased

### Fixed

- Return a doctor error for explicitly missing/non-file release settings paths.
- Hash Unicode scalar values consistently across narrow/wide string storage;
  add accent/combining-mark/emoji identity vectors without changing BMP IDs.
- Include observed artwork SHA-256 comparisons in previews, including same-key
  replacements and explicit unknown baselines, without persisting preview writes.
- Reconcile documentation and date historical validation checkpoints.

- Decode numeric HTML entities with Unicode characters on Python 2.7, including
  narrow builds; replace invalid scalar values without aborting provider parsing.
- Add a standalone Python 2.7/3 Unicode regression suite and a checklist for
  deferred live Plex validation.

- Prevent automatic title matches when known author evidence conflicts, across
  Audible and providers using the shared scorer; retain manual suggestions.
- Preserve valid work relationships when a forced enrichment refresh fails;
  replace them after an accepted lookup and still remove implausible work data.
- Replace supplied contributor namespaces rather than accumulating stale people,
  and discard a previous rating count when the rating source changes.
- Expire the Swedish catalogue index after one week, retry partial loads, and
  retain a complete index during reload failures.
- Recover clean album titles from Ljudboksarkivet presentation labels when a
  repeated lookup is unavailable.
- Add offline regression tests, execution of all v1/v2/v3 contract vectors,
  automated checks, a validated config example, and operator documentation.

### Added

- Synthetic provider response fixtures for normal, partial, and malformed payloads.
- Offline installer lifecycle tests and rollback on catchable interruption, with
  explicit reporting if the restored service cannot restart.
- Isolated album metadata previews and optional snapshot reports for offline review.
- Local doctor, snapshot comparison, report extraction, and validated per-book export.
- Multipart tag conflict detection with safe automatic matching deferral.
- Artwork structure, dimension, pixel/aspect checks and real PIL decoding when available.

- Strict optional vocalismeta.json identity, metadata, and local artwork overrides.
- Persistent per-book Swedish provider locators without changing portable IDs.
- Candidate evidence logs and an offline readable/JSON diagnostic report tool.
- Per-search HTTP attempt/deadline limits and 60-second provider outage backoff.
- Adapted ZIFburn/BitSkim release workflow for source uploads, bundle packaging,
  annotated tags, GitLab/GitHub releases, checksum verification, and resuming uploads.
  Release configuration remains external; no release was published by integration.

- Ko-fi support links on the public VocalisMeta website and GitHub README.
- Simplified Catppuccin Mocha-inspired public website with clearer typography,
  fewer visual panels, and no decorative book mockup.
- Portable deterministic `Contributor-ID: narrator:name:<fingerprint>`
  fallback metadata when Audible or Ljudboksarkivet supplies narrator names
  without person IDs.
- Rejection and cleanup of Open Library work relationships whose claimed first
  publication year occurs after the known audiobook recording release.
- Client documentation for the verified Ljudboksarkivet narrator fallback and
  complete cleanup of rejected Open Library work relationships.
- Active `0.1.1` development version reporting in the Plex bundle and runtime
  startup log, while the immutable stable release remains `v0.1.0`.
- Last-known-good author, series, sequence, language, edition, and valid
  Contract v3 metadata preservation when a provider refresh omits an existing
  relationship namespace.
- Traceable `series_tags` and `sequence_tags` counts in structured metadata
  refresh summaries.
- Exact multi-series client semantics that designate the first provider
  relationship as primary without unsafe fuzzy alias merging.
- Stable and development installer summaries that report the installed bundle
  version, install channel, and exact source revision.
- Google Books authentication through the `X-Goog-Api-Key` request header so
  Plex networking logs no longer expose API keys in request URLs.
- Clean local-fallback album titles when Plex persists VocalisMeta's descriptive
  Fix Match label, while preserving genuine custom titles.
- Optional Ljudboksarkivet recording matching for Swedish audiobooks, using the
  site's public sitemaps and structured `Audiobook` page data without calling
  its disallowed search endpoint.
- Ljudboksarkivet ISBN identities, Swedish titles, authors, narrators,
  publishers, release dates, summaries, genres, series/sequence relationships,
  ratings, and cover artwork stored directly in Plex.
- Swedish language aliases across recording and enrichment matching.
## 0.1.0 - 2026-08-15

### Added

- Direct audiobook matching and metadata from regional Audible catalogs.
- Compatibility-preserving Plex and client identity formats.
- Titles, authors, narrators, series, genres, dates, summaries, ratings, and covers.
- Embedded Audible and LibriVox IDs, ISBN, region, edition hints, and artwork
  across multi-part books.
- Embedded series and sequence fallback without changing Plex collections.
- Embedded author and narrator fallback when provider contributors are missing.
- Local, embedded, Audible, Open Library, and Google Books artwork fallbacks.
- Exact-ISBN Open Library enrichment with full Work descriptions.
- Multiple Audible-region search, request retries, validation, and safe failure handling.
- Ordered full-title, split-title, filename-title, and author-free search fallbacks
  with contributor validation, embedded-author recovery, and rejected-candidate
  diagnostics.
- Matched-parent author recovery when track Artist tags contain the narrator.
- Stable VocalisMeta artist identities for unresolved compound author credits.
- Stable Audible, LibriVox, ISBN, and local-fingerprint client identities.
- Clean local-fallback titles for Open Library and Google Books enrichment.
- Authoritative matched-source refreshes that replace stale provider metadata.
- ASIN-backed parent-author recovery and short-lived Audible search caching.
- Author recovery from alternate Plex parent fields, embedded tags, and
  validated `Author/Book/file` directory layouts when track Artist is a narrator.
- Edition matching using runtime, narrator, language, year, and abridgment hints.
- Presentation-aware matching that prevents ordinary audiobooks from
  automatically matching radio dramatisations, dramatized adaptations, or
  explicitly full-cast editions.
- Plex-tree duration recovery and strong rejection of severe runtime mismatches.
- Detailed Fix Match edition labels and normalized multi-series ordering.
- Catalog schema validation and equivalent ISBN-10/ISBN-13 enrichment lookups.
- App-friendly author, narrator, and series tags without changing Plex collections.
- Parseable series sequence, language, and abridged-edition Mood namespaces.
- Documented Client Identity Contract v1 and player-integration guide.
- Machine-readable Client Identity Contract v1 with shared compatibility test vectors.
- Default-on Open Library work identity with configurable Client Contract v2
  and shared player test vectors.
- Default-on provider-backed contributor IDs, first-publication year, explicit
  production type, and rating provenance with configurable Contract v3 vectors.
- Public release and developer installers with startup validation and rollback.
- Safe cleanup of disabled Contract v2 and v3 Mood namespaces on refresh.
- Work and Open Library contributor relationship revalidation after rematches.
- Google Books missing-field enrichment using exact ISBN or title and author.
- Configurable Open Library/Google Books priority and enrichment request budget.
- Short-lived book-provider search caching with safe uncached malformed-response
  retries.
- Optional LibriVox fallback matching with distinct project IDs, readers,
  durations, genres, and covers.
- LibriVox-first matching and Audible cross-match protection for media paths
  that explicitly contain `librivox`.
- LibriVox hinted-only, fallback, and preferred matching modes with short-lived
  search caching and safe uncached retry for malformed responses.
- One-line structured search summaries with provider, identity, author source,
  candidate counts, and stable outcome reasons.
- One-line structured metadata-refresh summaries for successful and early-exit
  update paths.
- Provider-failure classification that defers local fallback after network,
  HTTP, malformed-response, or partial regional catalog failures.
- Optional strict JSON configuration with safe reloads and secret-file support.
- Lightweight responsive PHP project website without external dependencies.
