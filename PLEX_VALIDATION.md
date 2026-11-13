# Live Plex validation checklist

Status: **deferred at the user's request on 13 November 2026**. No real Plex
server tests have been run. Offline checks do not establish AgentKit compatibility.

Use an isolated audiobook library and a backup of its Plex database. Record the
server version, OS, bundle revision, test date, and result/log evidence per case.

| Case | Procedure and expected result | Status |
| --- | --- | --- |
| Startup | Install reviewed bundle; restart; confirm agent registration and no import, syntax, or permission errors in fresh logs. | Pending |
| Unicode | Refresh Swedish titles, authors, and descriptions with accented names, numeric punctuation entities, and non-BMP characters; verify correct text and no traceback. | Pending |
| Matching | Test exact IDs, same-title/different-author books, manual selection, and unavailable recordings; verify correct provider identity or safe local fallback. | Pending |
| Locked fields | Lock title, summary, and artwork in Plex; refresh normally and forcibly; verify locks remain respected. | Pending |
| Multipart books | Refresh a book with several files; verify total runtime, edition choice, and artwork without duplicate duration. | Pending |
| Provider outage | On the test server, simulate a provider timeout/error, refresh a previously matched book, then restore access; verify useful metadata survives and later refresh recovers. | Pending |
| Upgrade | Install over an existing bundle; confirm backup path, version, service activation, and agent registration. | Pending |
| Rollback | In an isolated deployment, induce startup failure in a disposable candidate; verify previous bundle is restored and Plex starts. Never corrupt the only backup. | Pending |

After each case, capture only relevant fresh log entries, removing tokens and
private paths before sharing. Check the result in Plex and the audiobook client.
Restore temporary network changes and retain backups until validation finishes.
