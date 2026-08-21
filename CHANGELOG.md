# Changelog

## 0.1.0 - 2026-08-15

### Added

- Direct audiobook matching and metadata from regional Audible catalogs.
- VocalisMeta public branding with compatibility-preserving SpokenMeta Plex and
  client identity formats.
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
- Authoritative matched-source refreshes that replace stale provider metadata.
- ASIN-backed parent-author recovery and short-lived Audible search caching.
- Author recovery from alternate Plex parent fields, embedded tags, and
  validated `Author/Book/file` directory layouts when track Artist is a narrator.
- Edition matching using runtime, narrator, language, year, and abridgment hints.
- Plex-tree duration recovery and strong rejection of severe runtime mismatches.
- Detailed Fix Match edition labels and normalized multi-series ordering.
- Catalog schema validation and equivalent ISBN-10/ISBN-13 enrichment lookups.
- App-friendly author, narrator, and series tags without changing Plex collections.
- Parseable series sequence, language, and abridged-edition Mood namespaces.
- Documented Client Identity Contract v1 and player-integration guide.
- Machine-readable Client Identity Contract v1 with shared compatibility test vectors.
- Optional Open Library work identity with additive Client Contract v2 and
  shared player test vectors.
- Optional provider-backed contributor IDs, first-publication year, explicit
  production type, and rating provenance with Client Contract v3 vectors.
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
