# Development and verification

Run from the repository root with Python 3.9+ and Bash; no live provider credentials or Plex server are required. Install
`requirements-dev.txt` in a virtual environment for full image-decoder tests;
without it those cases skip explicitly and structural fallback tests still run:

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/install-on-plex.sh
php -l public-web/index.php
```

PHP is needed only for the website check. Tests execute every case in the
published v1, v2, and v3 vector files. They also cover conflicting author matches,
partial metadata preservation, replacement of contributor namespaces, rating
provenance, failed/successful work refreshes, catalogue expiry and partial loads,
and recovery of provider presentation labels. The example config is validated
by the production loader. Tests run the installer's embedded source compatibility
checks without running its root/service operations.

The agent harness injects small AgentKit substitutes so actual helpers and update
code can run offline. It does not simulate Plex's complete model, field locks,
sandbox, networking cache, or Python 2 interpreter. A separate installer harness
simulates service commands and lifecycle failures; it does not run real systemd. Keep bundle
code Python 2.7 compatible even though the test runner uses Python 3. Before a
release, test agent startup, search, metadata refresh, locked fields, multipart
books, and installer upgrade/rollback on a real supported Plex deployment.

Add regression cases when changing matching, merge rules, configuration, or
provider parsing. Stable contract files retain their existing semantics; add a
new version for incompatible changes. See [client-contract/README.md](client-contract/README.md).


## Unicode compatibility and deferred server checks

`python3 -m unittest discover -s tests -v` includes numeric-entity cases, invalid
Unicode scalar values, provider record parsing, and simulated narrow-build
behavior. The standalone file also runs under an actual Python 2.7 interpreter:

```bash
python2.7 tests/test_unicode_compat.py -v
```

No Python 2.7 interpreter was available locally for this change. The simulated
branch check is not a claim of execution on Python 2.7. Live Plex validation is
deferred at the user's request; see [the checklist](PLEX_VALIDATION.md).


## Added feature and release checks

The suite also checks per-book validation/precedence, saved recording persistence
and ambiguity, retry/time budgets, thread isolation, provider cooldowns, diagnostic
report rendering, and the adapted release workflow with mocked GitLab/GitHub APIs.
Release tooling and its dependencies live in `scripts/`; bundle code remains
Python 2.7-compatible. See [release instructions](docs/RELEASING.md).


## Provider, installer, preview, and artwork regression coverage

`tests/fixtures/providers` holds synthetic normal/partial/malformed catalogue
responses. These are offline schema examples, not live service captures. Installer
lifecycle tests execute a disposable copy of the script with fake Git/service/
ownership/move/sleep commands. Only the test copy removes the root gate; production
still requires root. All file changes occur in temporary test directories, and
no real service or remote repository is touched. Tests cover success, exact-tag
installation, startup/registration failures, initial installs, permission and move
errors, SIGTERM rollback, and failure to restart after restoration. SIGKILL, power
loss, real systemd, and real Plex startup remain outside this harness.

Preview tests verify scalar/list/poster isolation, suppressed persistent selection
writes, and exception cleanup. CLI tests validate reports/export through the real
sidecar loader, overwrite protection, XML boundaries, and config-secret redaction.
Artwork tests include corrupt/truncated fixtures, dimensions/aspect limits, real
JPEG/PNG/WebP decoding when Pillow is installed, and explicit no-decoder fallback.
See [Pillow's image API](https://pillow.readthedocs.io/en/stable/reference/Image.html)
for the verify/reopen/load lifecycle.


## Unicode identities and artwork observations

`client-contract/unicode-identity-vectors-v1.json` supplies fixed raw fingerprint,
narrator-name, and local-book cases for accents, combining marks, Swedish/CJK
names, and emoji. `python3 tests/test_unicode_identities.py` runs them without
Plex or third-party packages; the file also supports Python 2.7. Tests simulate
UTF-16 surrogate storage as well as native strings. This is not a claim of
execution on an actual Python 2 interpreter or every historical Unicode table.

Artwork report tests cover identical/changed bytes under the same poster key,
unknown baselines, failed candidates, remote URLs, preview isolation, and tracking
context cleanup. Stored hashes describe bytes last supplied by the agent, not a
read-back of the Plex database or proof that the server accepted a locked field.
