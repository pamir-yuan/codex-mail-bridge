# Security and privacy

This program can turn an email reply into input for a coding agent. The input
inherits the permissions of the existing chat. Use it only for a mailbox and
local machine you control.

## Current trust boundary

- Single self-notification mailbox; no arbitrary recipients or multi-user access.
- TLS certificate verification for SMTP and IMAP.
- Exact parsed sender address plus references to an independently random known notification.
- No matching by subject alone. Ambiguous references, automated replies and
  outgoing notification messages are ignored.
- Quote removal and size limits reduce accidental forwarding of old content.
- Body attachments are not interpreted as commands.

These checks are **correlation, not cryptographic sender authentication**. The
program does not validate DKIM, DMARC or S/MIME. Email headers can be forged, and
anyone obtaining a notification's reference/correlation capability may be able
to construct a matching reply. Mailbox compromise or forwarding a notification
can expose that capability. This preview is not a hardened public remote-command
gateway. Do not give it access to untrusted shared mailboxes.

## Storage

Connection settings, credentials and delivery state are outside the source tree.
Credential files require mode 0600 in a mode-0700 directory and are not read
through symlinks. Provider errors are reduced to exception types so they cannot
echo submitted content into logs. No telemetry is implemented.

The state database contains email identifiers, recipients, titles and chat
references. Treat it as private even though reply bodies are not stored there.
The desktop and its usual conversation history can retain the submitted text.

Never commit credentials, raw `.eml` files, databases, live logs, authentication
headers or a personal copy of application state. Ignore rules and the public-tree
checker are additional checks, not a guarantee that arbitrary future files are safe.

## Delivery and execution

The desktop IPC protocol and local thread-index schema are private and may
change. Protocol rejection is recorded as a failed submission. Failed or
uncertain replies are not automatically retried because the desktop may already
have accepted them. Review the original chat before manually resending anything.

## Reporting

Use GitHub's [private vulnerability reporting](https://github.com/pamir-yuan/codex-mail-bridge/security/advisories/new)
to report a suspected vulnerability to the maintainers. Do not post credentials
in public issues or attach live mailbox / chat data. Describe issues using
synthetic messages and redacted steps.
