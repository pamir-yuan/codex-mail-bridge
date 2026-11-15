# Desktop compatibility

Status: experimental macOS-only adapter. No stable upstream desktop messaging
API is claimed. The package does not require a Codex CLI executable at runtime
to submit replies, and it does not modify an application bundle.

The prototype protocol was observed with desktop version `26.1106.51428`, build
`26605`, and its bundled CLI `0.167.0-alpha.4.1`. These are observations, not a
promise that every build in a version range works. A real mobile reply was
observed in an active chat in the prototype; package preparation uses isolated
tests. Real idle recovery, sleep/wake and application-upgrade behavior need
additional end-to-end validation.

## Transport seam

The default socket is `CODEX_HOME/ipc/ipc.sock`. It uses four-byte little-endian
length framing followed by UTF-8 JSON, not app-server JSONL or MCP messages.

The independently implemented client registers, discovers the desktop owner of
the target UUID, and directs requests to that owner. It uses the installed
protocol's request versions:

| Method | Version | Purpose |
|---|---|---|
| `initialize` | 0 | Register a local bridge client |
| `thread-owner-discovery` | 1 | Find the owner of the exact chat |
| `thread-follower-steer-turn` | 1 | Add input to an active turn |
| `thread-follower-start-turn` | 2 | Start an idle chat turn, inheriting its settings |

Only an explicit no-active-turn response permits the idle fallback. A timeout,
unknown error or disconnected socket never causes an automatic second attempt.
The adapter ignores unrelated broadcasts and correlates responses by request ID.

The default read-only thread index is `CODEX_HOME/state_5.sqlite`, using its
`threads` table to validate the target and reject archived chats. This is another
private format, not a general stable Codex API. Explicit path overrides exist
for testing and compatible profiles; arbitrary new database schemas are not inferred.

Do not point an app-server `--remote` option at this socket. If an upstream
stable messaging API becomes suitable, replace the adapter seam while keeping
the email correlation layer.
