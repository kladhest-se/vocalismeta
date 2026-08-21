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

The commands below install the immutable `v0.1.0` release into Plex's standard
Linux plug-in directory. Change `PLUGIN_DIR` if your Plex data directory is
different.

```bash
git --version

VOCALISMETA_VERSION='v0.1.0'
VOCALISMETA_REPOSITORY='https://github.com/kladhest-se/vocalismeta.git'
PLUGIN_DIR='/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-ins'
CHECKOUT_DIR="$(mktemp -d /tmp/VocalisMeta.XXXXXXXX)" &&
git -C "$CHECKOUT_DIR" init --quiet &&
git -C "$CHECKOUT_DIR" remote add origin "$VOCALISMETA_REPOSITORY" &&
git -C "$CHECKOUT_DIR" fetch --quiet --depth 1 origin \
  "refs/tags/$VOCALISMETA_VERSION:refs/tags/$VOCALISMETA_VERSION" &&
git -C "$CHECKOUT_DIR" checkout --quiet --detach \
  "$VOCALISMETA_VERSION^{commit}" &&
test "$(git -C "$CHECKOUT_DIR" describe --tags --exact-match)" = \
  "$VOCALISMETA_VERSION" &&
sudo mkdir -p "$PLUGIN_DIR" &&
sudo rm -rf -- "$PLUGIN_DIR/VocalisMeta.bundle" &&
sudo cp -a "$CHECKOUT_DIR/VocalisMeta.bundle" \
  "$PLUGIN_DIR/VocalisMeta.bundle" &&
sudo chown -R plex:plex "$PLUGIN_DIR/VocalisMeta.bundle" &&
sudo systemctl restart plexmediaserver &&
sudo systemctl is-active --quiet plexmediaserver &&
rm -rf -- "$CHECKOUT_DIR" &&
echo "VocalisMeta $VOCALISMETA_VERSION installed and Plex is active."
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
