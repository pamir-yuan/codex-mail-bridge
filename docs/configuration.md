# Configuration

Use `codex-mail-bridge init` for interactive configuration, or `init --example`
followed by local edits and `set-password`. These commands do not send emails,
touch Codex configuration, or install services.

The example in `examples/config.example.json` contains reserved placeholders.
Replace both hosts and the mailbox values with your provider's settings.

| Field | Meaning |
|---|---|
| `smtp_host` | SMTP hostname, without a URL scheme |
| `port` | SMTP TLS port, typically provider-specific 465 or 587 |
| `security` | `ssl` for TLS from connection start; `starttls` for TLS before authentication |
| `username` | Shared SMTP / IMAP account login |
| `from`, `to` | Same self-notification email address; one recipient only |
| `imap_host`, `imap_port` | IMAP TLS endpoint, commonly port 993 |
| `mailbox` | Folder containing both original self-notifications and incoming replies |
| `poll_seconds` | Integer 5–300; default 15 |

IMAP always uses TLS; plaintext SMTP and disabled certificate verification are
not supported. The current implementation uses one password for both protocols.

## Private locations

| Location | Contents |
|---|---|
| `~/.config/codex-mail-bridge/config.json` | Connection settings, no password |
| `~/.config/codex-mail-bridge/credentials.json` | App password; private local file |
| `~/.local/state/codex-mail-bridge/bridge.sqlite3` | Notification-to-chat map, email identifiers, subject, recipient, delivery metadata |
| `~/.local/state/codex-mail-bridge/listener.log` | Service timestamps and error types, no email body or credential values |
| `~/Library/LaunchAgents/org.codexmailbridge.listener.plist` | Optional login-service definition |

The database includes private metadata and correlation capabilities. Do not
attach it to issue reports. The source distribution includes none of these files.

## Environment variables

- `CODEX_MAIL_BRIDGE_PASSWORD`: foreground app password; overrides the local credential file.
- `CODEX_MAIL_BRIDGE_CONFIG_DIR`: private connection and credential directory.
- `CODEX_MAIL_BRIDGE_STATE_DIR`: private database and log directory.
- `CODEX_HOME`: Codex profile home; default `~/.codex`.
- `CODEX_MAIL_BRIDGE_IPC_SOCKET`: explicit override for the desktop socket.
- `CODEX_MAIL_BRIDGE_CODEX_STATE_DB`: explicit override for the compatible local thread index.
- `CODEX_THREAD_ID`: read by the CLI when invoked inside the originating chat.

The generated MCP and service settings forward only location variables, not
passwords or a captured `CODEX_THREAD_ID`. A login service requires a local
credential file because an ordinary terminal's environment is not inherited.

## Status and failure handling

`doctor` checks local availability without network traffic or creating message
state. `doctor --network` additionally performs a read-only IMAP TLS login.
`status` reads counts and heartbeat without creating a database.

`smtp_accepted` means SMTP accepted the email, not that the user received it.
`desktop_accepted` means the desktop accepted input, not that the model finished
the requested work. Failed or interrupted submissions require review before
replay, which currently has no automatic CLI command.
