# Development and verification

Run from the repository root with Python 3.9+ and Bash; no third-party Python
dependencies, live provider credentials, or Plex server are required:

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

The harness injects small AgentKit substitutes so actual agent helpers and update
code can run offline. It does not simulate Plex's complete model, field locks,
sandbox, networking cache, Python 2 interpreter, or service lifecycle. Keep bundle
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
