# Configuration

Configure VocalisMeta through Plex's agent preferences or an optional JSON file.
Start with [config.example.json](config.example.json). The example deliberately
disables Google Books until you provide a key. No credentials are included.

## Location, precedence, and reload

The agent finds the file in this order:

1. Non-empty **Optional absolute path to VocalisMeta JSON configuration** Plex preference.
2. `VOCALISMETA_CONFIG_FILE` in the Plex service environment.
3. Legacy `SPOKENMETA_CONFIG_FILE` environment variable.

The path must be absolute and readable by the Plex service user. JSON values
override the corresponding Plex preferences; omitted keys retain Plex preferences
and defaults. `schema_version` is required and must be the integer `1`. Unknown
keys, wrong types, and out-of-range values reject the entire file.

The agent checks file signatures when reading preferences. Atomic replacement
of the config or referenced secret is detected without restarting Plex. A bad
reload of the same config path preserves the last valid values and logs an error.
An invalid first load, or changing to an invalid different path, falls back to
Plex preferences. Removing the configured path setting returns to preferences
unless an environment variable still supplies a path. If the file itself is
deleted after a valid load, last-known-good values remain active.

## Reference

Every section is optional. Boolean values must be JSON `true` or `false`;
numbers must be integers, not quoted strings. File size is limited to 1 MiB.

| Section | Keys and accepted values |
| --- | --- |
| `audible` | `region`: `au`, `ca`, `de`, `es`, `fr`, `in`, `it`, `jp`, `us`, `uk`; `fallback_regions`: array of at most four region codes; `maximum_results`: 10, 20, 25, 50; `exclude_preorders`, `include_adult`: booleans; `api_base_url`: empty or HTTP(S) URL for an Audible-compatible endpoint |
| `providers.librivox` | `enabled`: boolean; `mode`: `hinted_only`, `fallback`, `preferred` |
| `providers.ljudboksarkivet` | `enabled`: boolean; `mode`: `fallback`, `preferred` |
| `providers.open_library` | `enabled`: boolean |
| `providers.google_books` | `enabled`: boolean; `api_key_file`: non-empty path to a UTF-8 secret file |
| `providers` | `enrichment_priority`: `openlibrary_first` or `googlebooks_first`; `request_budget`: 2, 4, 6, 8, 12 logical enrichment requests per refresh (retries are additional attempts) |
| `metadata` | Boolean keys: `include_subtitle`, `simplify_title`, `keep_existing_genres`, `authors_as_moods`, `series_as_moods`, `embedded_series_fallback`, `embedded_contributor_fallback`, `author_genres`, `work_identity_as_mood`, `extended_player_metadata`, `preview_updates`, `reports`, `client_contract_v4` |
| `artwork` | `preference`: `local_first`, `audible_first`, `local_only`, `audible_only`; `requested_size`: 500, 1000, 2000, 3000 |
| `network` | `attempts`: 1–5 total attempts, including the first; `timeout_seconds`: 10–120 per attempt; `search_request_budget`: 12, 24, 48 total search attempts; `search_timeout_seconds`: 30, 60, 90, 180 |
| `logging` | `level`: `DEBUG`, `INFO`, `WARN`, `ERROR` |

Without a config file, actual defaults are in
[`DefaultPrefs.json`](VocalisMeta.bundle/Contents/DefaultPrefs.json). The example
is a usable starting configuration, not a promise that every value equals the
default (it adds a UK fallback and disables Google Books).

## Google Books secret

Add `"api_key_file": "google-books.key"` to `providers.google_books` and set
`enabled` to `true`. Relative secret paths resolve beside the JSON file, not
beside the plug-in. The secret must be a single non-empty UTF-8 value, at most
16 KiB, with an optional trailing newline. Google Books also requires a non-empty
key; enabling it alone is insufficient. Authentication uses the request header.

Keep config and secrets outside the bundle so upgrades preserve them. For example,
use `/etc/vocalismeta/config.json` and `/etc/vocalismeta/google-books.key`.
Allow only administrators and the Plex service account to read the secret
(for a `plex` group, ownership `root:plex` and mode `0640`; parent directory
`0750`). Adjust ownership for your actual service account. Do not commit keys
or include them in diagnostic reports.

Environment changes require a Plex service restart; changing the referenced file
does not. See [OPERATIONS.md](OPERATIONS.md) for logs and recovery.

Per-book overrides are separate from this agent settings schema: see
[BOOK_METADATA.md](BOOK_METADATA.md). Search limits default to 24 attempts /
90 seconds; enrichment has its own request budget.

`metadata.preview_updates` and `metadata.reports` default to false. See
[previews and export](BOOK_METADATA.md) before enabling snapshot logging.

`metadata.client_contract_v4` defaults to false. Enable only after all clients
reserve and support the v4 Mood prefix; see [Contract v4](docs/CLIENT_CONTRACT_V4.md).
