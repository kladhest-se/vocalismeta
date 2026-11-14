# Audit repairs

All seven archive audit findings are addressed in this source tree. These notes cover
0.1.1 development work and its validation history.

| Finding | Resolution |
| --- | --- |
| Wrong-author automatic match | Shared scoring caps conflicting/missing provider author evidence below automatic acceptance; automatic Audible queries also reject conflicting authors. Unknown scanner authors are treated as absent evidence. |
| Work data lost on forced refresh | Work relationships remain until an accepted replacement lookup; explicitly implausible work evidence is still removed. |
| Stale contributor/rating data | Supplied contributor namespaces replace previous members; narrator name fallbacks and provider IDs replace the same narrator namespace. Rating source changes invalidate previous vote counts. |
| Catalogue never expires | Complete index expires after one week; partial loads do not become complete caches; previous complete data survives an outage. |
| Provider label stored as title | Local/ISBN updates clean Ljudboksarkivet presentation labels while preserving custom titles. |
| Missing automated suite | Standard-library regression suite, every published v1/v2/v3 vector, and GitHub Actions workflow are included. |
| Missing operator docs | Config schema, validated example, precedence/secrets/reload, requirements, verification limits, local deployment, troubleshooting, restore, and uninstall are documented. |

## Validation history

These are dated development checkpoints, not a statement about the currently
published release or a substitute for real Plex deployment evidence:

| Checkpoint | Offline result |
| --- | --- |
| Initial audit repairs, 12–13 November 2026 | 20 test methods, including the original 18 published contract cases |
| Unicode decoding repair, 13 November 2026 | 26 test methods |
| Saved selections, overrides, search limits, and release tools, 13 November 2026 | 112 test methods |
| Provider fixtures, installer simulations, previews, doctor/export, multipart conflicts, and artwork validation, 13 November 2026 | 141 test methods with Pillow enabled |
| Doctor missing-file check, Unicode identity vectors, and artwork hash previews, 14 November 2026 | 155 test methods with Pillow enabled |

The current checkpoint also passes Bash/PHP syntax checks and the installer-owned
source compatibility checks. Actual Python 2 execution, live provider integration,
real Plex startup/field locks, and real service restart/rollback remain unverified.
Real Plex tests are deferred at the user's request. Simulated installer rollback
is tested; it must not be confused with real service rollback verification.

See [DEVELOPMENT.md](DEVELOPMENT.md), [OPERATIONS.md](OPERATIONS.md),
[BOOK_METADATA.md](BOOK_METADATA.md), and [release instructions](docs/RELEASING.md).
