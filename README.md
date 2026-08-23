# VocalisMeta

VocalisMeta is a legacy Plex metadata agent for audiobook libraries. It adds
book and recording metadata directly to Plex without requiring a companion
service.

Current release: **v0.1.0**

For the best listening experience, use VocalisMeta with
[VocalisBook](https://vocalisbook.kladhest.se) for macOS, iPhone, iPad, and
Apple TV.

## Features

- Audible matching across multiple regions
- Optional Ljudboksarkivet matching for Swedish audiobooks
- Open Library, Google Books, and optional LibriVox enrichment
- Authors, narrators, genres, series, sequence, language, and edition metadata
- Stable audiobook, work, and contributor identities for Plex clients
- Embedded ASIN, region, ISBN, LibriVox ID, series, and contributor tags
- Local, embedded, and provider cover artwork with validation and fallback
- Multi-part audiobook scanning and edition-aware matching
- Configurable retries, provider priority, artwork preference, and JSON settings
- Versioned player contracts and test vectors:
  [v1](client-contract/metadata-contract-v1.json) / [tests](client-contract/test-vectors-v1.json),
  [v2](client-contract/metadata-contract-v2.json) / [tests](client-contract/test-vectors-v2.json),
  and [v3](client-contract/metadata-contract-v3.json) / [tests](client-contract/test-vectors-v3.json)

## Install on Linux

The installer downloads VocalisMeta, validates it, replaces the existing bundle,
restarts Plex, checks the plug-in log, and restores the previous installation if
startup fails.

Install the immutable `v0.1.0` release:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/kladhest-se/vocalismeta/main/scripts/install-on-plex.sh |
  sudo bash -s -- --release v0.1.0
```

### Developer build

Use this only when testing the latest unpublished changes from GitHub. The
`main` branch can change at any time and is less reproducible than a release
tag.

```bash
curl -fsSL \
  https://raw.githubusercontent.com/kladhest-se/vocalismeta/main/scripts/install-on-plex.sh |
  sudo bash -s -- --developer
```

Then configure Plex:

1. Open **Settings → Manage → Libraries**.
2. Create or edit the **Music** library used for audiobooks.
3. Open **Advanced**.
4. Select **Plex Music Scanner** and **VocalisMeta Agent**.
5. Enable **Store track progress** when available.
6. Save the library and run **Refresh All Metadata**.

### Swedish audiobooks

In the VocalisMeta agent settings, enable **Ljudboksarkivet matching for Swedish
audiobooks** and select either `fallback` (try after Audible) or `preferred`
(try before Audible). It is disabled by default.

VocalisMeta reads Ljudboksarkivet's public sitemap and structured audiobook
metadata, then stores the accepted result in Plex. Audiobook players still talk
only to Plex; no companion service or Ljudboksarkivet client integration is
required.

## Inspect one audiobook

Download the public inspector on the Plex server, then resolve and inspect a
book by title and author. Running as root lets it read Plex's local token.

```bash
curl -fsSLo /tmp/inspect-plex-book.py \
  https://raw.githubusercontent.com/kladhest-se/vocalismeta/main/scripts/inspect-plex-book.py
chmod +x /tmp/inspect-plex-book.py
sudo /tmp/inspect-plex-book.py "Dune" \
  --author "Frank Herbert" \
  --library "Audiobooks"
```

Add `--refresh` to force-refresh that album before inspection, `--json` for
machine-readable diagnostics, or `--xml` for Plex's raw per-item response.

If upgrading from `SpokenMeta.bundle`, remove the old bundle first. Do not keep
both bundles installed because they use the same internal Plex provider ID.
