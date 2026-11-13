# VocalisMeta source and tagged releases

These tools adapt the workflow supplied in the ZIFburn archive, originally
adapted from BitSkim. The MIT notices are retained in `scripts/LICENSE-BitSkim` and
`scripts/LICENSE-ZIFburn`.
VocalisMeta packages a Plex bundle, source, and the PHP website; no Xcode,
macOS app signing, DMG, or notarization step is involved.

Requires Python 3.9+, Git, Bash, and PHP for checks. Run from the project root.
The bundle version in `Contents/Info.plist` is authoritative; its two version
fields and runtime `VERSION` must agree. Version changes are explicit source
edits; release commands do not rewrite them.

## External project settings

Default: `~/Development/tools/git-release/projects/vocalismeta.json`.
Use `examples/release-config.json` as the schema example. Override with
`--config /path/to/settings.json` or `VOCALISMETA_RELEASE_CONFIG`.
Actual internal destinations and credential references belong outside the public
checkout. `source_branch` optionally names the destination branch; empty means
use the current branch. `env` accepts only `PHP` and
`VOCALISMETA_RELEASE_PYTHON` executable paths. GitLab nested groups are supported.
Git push URLs must match their HTTPS repository identity; normal SSH URLs and
credential-free HTTPS Git URLs are accepted.

API credentials are resolved only during publication. The default environment
references are `GITHUB_TOKEN` and `GITLAB_TOKEN`; no token belongs in JSON.
Alternatively configure a 1Password CLI reference:

```json
{
  "credentials": {
    "github": {"provider": "1password", "reference": "op://Vault/Item/Field"},
    "gitlab": {"provider": "1password", "vault": "Vault", "item": "GitLab", "field": "project-token"}
  }
}
```

This is a fragment to merge into external settings. Optional `account` selects
a 1Password account. The `op` CLI must already be installed and authorized.
Git pushes use SSH keys or the Git credential helper separately from API tokens.
Build subprocesses have configured API token variables removed. Publication
requires repository write access, package upload access on GitLab, and permission
to create the target tags/releases. Protected tag policies can require additional
rights. Tests use mocks and do not prove live service access.

## Source-only upload

```bash
python3 scripts/release.py source --to gitlab,github --dry-run
python3 scripts/release.py source --to gitlab,github --confirm-push
```

A clean committed Git checkout is required. Both destinations are preflighted
before any actual source push. Only the current branch is pushed; no force,
mirror, or implicit tag upload is used.

For a directory with no Git history, `source --init --to gitlab,github --dry-run`
can initialize and commit allowlisted local source, but only after checking both
remotes are empty. **`--init` changes local Git metadata even with `--dry-run`.**
It requires Git author identity and a reviewed `.gitignore`. If either repository
already has history, clone it and transfer reviewed changes into that checkout.
The integration itself does not initialize this project or alter remote history.

## Build, check, and prepare

```bash
python3 scripts/release.py plan
python3 scripts/release.py build
python3 scripts/release.py check
python3 scripts/release.py prepare --tag v0.1.1 --tag-message "VocalisMeta 0.1.1"
```

`plan` lists checks without building, credential lookup, or network requests.
`build` runs the full offline suite, installer compatibility/syntax checks, and
PHP syntax validation. It packages reviewed inputs, records source and artifact
hashes, and checks the completed inventory. Build/check/prepare do not publish.
Extracted source can build and prepare with a null commit; publication refuses
such a manifest until a clean committed checkout is rebuilt and prepared.

Local `outputs/artifacts/` contains:

- `VocalisMeta-<version>.bundle.zip` with the installable bundle and MIT license.
- `vocalismeta-<version>-source.tar.gz` with allowlisted source and build record.
- `vocalismeta-<version>-website.tar.gz` with PHP/CSS/assets and MIT license.
- `BUILD-PROVENANCE.json` and `SHA256SUMS`.

Only the bundle ZIP and its individual `.sha256` file are staged for publication
in `outputs/release/publish/`. GitHub/GitLab provide source from the tagged commit;
standalone source, website, and provenance stay local. Publishing does not deploy
the website. Source selection excludes outputs, work/settings directories,
Git metadata, bytecode caches, and unrelated files. Do not put credentials in
allowlisted inputs or Git history; the known-token check is not a secret scanner.

`prepare` freezes notes, destinations, exact commit, source hash, tag annotation,
and asset hashes in `outputs/release/manifest.json`. Default notes are
`docs/RELEASE-NOTES.md`; use `--notes` for a reviewed alternative. Review this
manifest and the staged ZIP. An omitted tag defaults to `v<bundle-version>`;
custom tags are used verbatim. The Linux installer expects release tags of the
form `vX.Y.Z`, so prefer that convention. Stable published tags are never moved.

## Publishing and resuming

```bash
python3 scripts/release.py publish --tag v0.1.1 --to gitlab,github --confirm-publish
```

For an already verified build, `release --tag v0.1.1 --to gitlab,github
--confirm-publish` combines prepare and publish. These commands create annotated
local tags, push the selected tag and its commit, then upload exact staged bytes.
They do not replace the source-only branch push operation. Without the explicit
confirmation flag they stop before publication.

All selected destinations are preflighted before tag pushes or uploads. Conflicting
tags, notes, package hashes, settings, or asset inventories stop the run. GitHub
stays a draft until expected asset hashes are confirmed. GitLab package downloads
are hashed before release links are added. Credentials are sent only over HTTPS
without following redirects; deployments requiring object-store redirects need
an adapter rather than weaker credential forwarding.

Keep manifest, staged assets, artifacts, and `outputs/release/receipt.json`
together after an interrupted publication. Review the failure, then repeat the
same command. Matching remote files are reused; completed destinations are
revalidated. The receipt is bound to the manifest. There is no automatic network
retry or cross-service rollback; a later failure can leave an earlier destination
published. Do not delete a receipt to bypass verification, force-move tags, or
rebuild over existing release evidence. Archive old outputs outside `outputs/`
when preparing a different release.

## Validation limits

`make release-tests` runs the same complete offline suite as `make test`.
Release tests use temporary Git repositories, mocked API services, and simulated
uploads/interruptions. No test publishes anything. Real GitLab/GitHub publication
and real Plex startup, field locks, provider integration, and rollback remain
unverified. See [the deferred Plex checklist](../PLEX_VALIDATION.md).
