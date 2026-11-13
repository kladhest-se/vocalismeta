# Installation, troubleshooting, and recovery

## Requirements and compatibility

The supplied installer targets Linux installations managed by **systemd**.
It runs as root, restarts Plex, and assumes the service/user/group are
`plexmediaserver` / `plex` / `plex` unless overridden. It requires Bash, Git,
Python 3, systemctl, and standard filesystem/text tools, including awk, grep,
tail, chown, id, mktemp, mv, mkdir, rmdir, rm, date, and sleep. It needs network
access to GitHub; the agent needs access to the providers you enable.

The bundle targets the legacy Plex Framework 2 / Python 2.7 agent environment.
Python 3 is used by the installer and offline tests, not as a replacement for the
Plex runtime. Plex must expose legacy Music agent selection and the Plex Music
Scanner. Container, NAS, Windows, macOS, and non-systemd deployments are not
handled by this installer. VocalisBook's supported platforms describe the player,
not the server installer.

| Environment | Verification shipped with this source |
| --- | --- |
| Python 3 offline helpers | Standard-library regression suite and all published contract vectors |
| Legacy Plex AgentKit | Installer-owned source compatibility checks; tests use lightweight Plex stubs |
| Linux/systemd installer | Bash syntax check; live restart and rollback require deployment testing |
| PHP website | PHP syntax check; site requires PHP 7.4+ |
| Specific Plex Media Server release | No end-to-end tested version is claimed by this archive |

Before production use, validate on your actual Plex version with a small test
library. Record server version, operating system, search/update results, and
installer startup/rollback outcomes. Offline tests do not establish server
compatibility.

## Installer paths and overrides

Default data directory:
`/var/lib/plexmediaserver/Library/Application Support/Plex Media Server`.

| Environment variable | Purpose |
| --- | --- |
| `PLEX_MEDIA_SERVER_DATA_DIR` | Data directory; used to derive default plug-in and log paths |
| `VOCALISMETA_PLUGIN_DIRECTORY` | Plug-ins directory containing `VocalisMeta.bundle` |
| `VOCALISMETA_LOG_FILE` | Full agent log path |
| `PLEX_SERVICE_NAME` | systemd service name |
| `PLEX_USER`, `PLEX_GROUP` | Bundle ownership |

Defaults for the log and bundle are `Logs/PMS Plugin Logs/com.plexapp.agents.spokenmeta.log`
and `Plug-ins/VocalisMeta.bundle` under the data directory. The retained
`spokenmeta` identifier is intentional for client identity compatibility.
Use explicit environment assignments with `sudo env` if you need to pass overrides
through sudo. Consult `bash scripts/install-on-plex.sh --help` before installation.

The installer stops Plex, moves an existing bundle into a uniquely named
`.vocalismeta-backup.*` directory, installs the new bundle, and validates startup.
On a successful upgrade it prints the retained backup location. Keep that output.
An initial install has no previous bundle to back up. Installation changes the
plug-in, not a backup of your complete Plex database; back up Plex separately
before bulk metadata changes.

## Deploying reviewed local source

The README's stable command downloads v0.1.0; the developer command downloads
GitHub main. Neither installs edits that exist only in your local archive.
To try this corrected source, run [the checks](DEVELOPMENT.md), stop Plex on your
test server, and move the existing `VocalisMeta.bundle` outside Plug-ins as a
backup. Copy this tree's `VocalisMeta.bundle` into the effective Plug-ins directory,
set its ownership to the Plex service user/group, then start Plex and confirm
agent registration in the log. Preserve the directory structure:
`Contents/Info.plist` must be directly beneath `VocalisMeta.bundle`. Copy only
the bundle into Plug-ins. If startup fails, stop Plex and restore the previous
bundle as described below.

## Troubleshooting

If installation fails, read the printed error and agent log. The installer checks
service activation and agent registration, not whether every provider works.
Rollback is attempted automatically on startup failure or catchable interruption; verify Plex is running
afterward. If automatic rollback cannot restore service, follow the manual
procedure below.

If the agent is missing from the library settings, verify this Plex version
offers legacy agents, the bundle is in the effective Plug-ins directory, and its
files are readable by the service account. Check both the agent log and
`systemctl status plexmediaserver` (substitute your service name).

For a wrong or missing book match, inspect title/album, author, embedded IDs,
language, and multipart runtime. Use Plex **Fix Match** for a specific recording;
an explicit valid Audible ASIN or LibriVox ID avoids title ambiguity. Check region
and provider settings. A low-confidence automatic candidate falls back to local
metadata; manual suggestions remain available for review. For a network outage,
restore provider access and refresh again. Inspect field locks if accepted
metadata does not appear to change.

For missing enrichment, check provider enablement and Google Books key, JSON
validation errors, request budget, and provider response errors. Temporarily
select DEBUG logging, reproduce once, then return to INFO. Review diagnostics
before sharing them: filenames, book titles, and custom endpoint details can
contain private information.

Ljudboksarkivet's complete catalogue index expires after one week. Partial loads
are retried instead of replacing a complete index; an older complete index is
retained if a reload fails. Provider pages have a separate six-hour HTTP cache.

## Manual restore

Use the exact backup path printed by your successful installation. With Plex
stopped, move the current bundle aside, then move that backup directory to
`VocalisMeta.bundle` in the same Plug-ins directory. Restore ownership to the
actual Plex user/group, start Plex, and inspect startup logs. Keep the displaced
bundle until the restore is verified. Never move or delete the entire Plug-ins
or Plex data directory. A bundle restore does not undo metadata already written
to Plex; restoring that requires your Plex database backup.

## Uninstall

Stop Plex, move only `VocalisMeta.bundle` out of the Plug-ins directory to a
separate backup location, and start Plex. Select another available agent for
the audiobook library before refreshing its metadata. Remove any dedicated
configuration environment setting and its secret files only if they are no
longer needed. Existing metadata can remain in Plex until a subsequent refresh;
uninstalling the bundle does not restore earlier field values. Retained installer
backups may be deleted individually after you no longer need recovery.


Offline validation and preview/export commands are documented in
[BOOK_METADATA.md](BOOK_METADATA.md). Rollback failures now explicitly report when
files were restored but the service could not be restarted; inspect the service
and start it manually. SIGKILL/power loss cannot be handled by shell traps, so keep
the printed backup path and independent Plex backups.
