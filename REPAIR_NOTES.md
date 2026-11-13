# Audit repairs

All seven archive audit findings are addressed in this source tree. These are
local 0.1.1 development changes; no remote release was published and no Plex
installation was modified.

| Finding | Resolution |
| --- | --- |
| Wrong-author automatic match | Shared scoring caps conflicting/missing provider author evidence below automatic acceptance; automatic Audible queries also reject conflicting authors. Unknown scanner authors are treated as absent evidence. |
| Work data lost on forced refresh | Work relationships remain until an accepted replacement lookup; explicitly implausible work evidence is still removed. |
| Stale contributor/rating data | Supplied contributor namespaces replace previous members; narrator name fallbacks and provider IDs replace the same narrator namespace. Rating source changes invalidate previous vote counts. |
| Catalogue never expires | Complete index expires after one week; partial loads do not become complete caches; previous complete data survives an outage. |
| Provider label stored as title | Local/ISBN updates clean Ljudboksarkivet presentation labels while preserving custom titles. |
| Missing automated suite | Standard-library regression suite, every published v1/v2/v3 vector, and GitHub Actions workflow are included. |
| Missing operator docs | Config schema, validated example, precedence/secrets/reload, requirements, verification limits, local deployment, troubleshooting, restore, and uninstall are documented. |

Validation: 20 test methods passed, including all 18 published vector cases;
installer compatibility checks, Bash syntax, and PHP syntax passed. No live Plex
server, Python 2 runtime, provider integration, or service rollback was exercised.
See [DEVELOPMENT.md](DEVELOPMENT.md) and [OPERATIONS.md](OPERATIONS.md).


Additional development work on 13 November 2026 adds persistent Swedish provider
selections, optional per-book JSON overrides, candidate diagnostics, bounded search
requests/time, provider outage backoff, and the adapted ZIFburn/BitSkim release
workflow. External release settings are kept outside public source. See
[BOOK_METADATA.md](BOOK_METADATA.md) and [docs/RELEASING.md](docs/RELEASING.md).
Real Plex tests remain deferred by request; no repository publication occurred.


The next reliability pass adds all seven requested improvements: provider fixtures,
offline installer rollback tests, metadata previews, doctor, multipart conflict
detection, portable export, and artwork validation. Details and usage are in
BOOK_METADATA.md. No real Plex validation, repository push, or release publication
is performed by these changes.

This pass is validated with 141 offline tests in a Pillow-enabled test environment;
Bash and PHP syntax checks also pass. Live Plex checks remain deferred.
