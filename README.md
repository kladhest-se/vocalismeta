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

If upgrading from `SpokenMeta.bundle`, remove the old bundle first. Do not keep
both bundles installed because they use the same internal Plex provider ID.
