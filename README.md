# Codex Mail Bridge

[简体中文](README.zh-CN.md) · Experimental macOS preview · MIT

Send an email notification from a Codex chat, reply from your phone, and route
the new reply text back to the originating desktop chat.

This is a small local application with an optional MCP interface. The desktop
adapter uses a **private, versioned IPC protocol** and may need updates after a
Codex Desktop upgrade. It is an independent project, not an OpenAI product.

## What it does

- SMTP notifications bound to the real originating chat UUID.
- Read-only IMAP polling, matched by email references and a random notification marker.
- Learning server-assigned Message-IDs when a provider rewrites outgoing IDs.
- Plain-text / HTML reply extraction, common quote removal, loop prevention and deduplication.
- Submission into an active desktop turn, with a fresh turn only after an explicit idle response.
- CLI, two MCP tools, and an opt-in macOS login service.

The initial scope is **one mailbox sending notifications to itself**, using the
same login and app password for SMTP and IMAP. The monitored inbox must receive
the original notification so that rewritten IDs can be learned. Arbitrary
external recipients and multiple mailbox accounts are not supported in 0.1.

Automatic notification on every chat completion, crash monitoring, guaranteed
delivery, attachments as commands, and multi-user access are not included.

## Install from a local checkout

Use Python 3.11 or newer on macOS. Keep the checkout and its environment at a
stable location if you install a background service from it.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ".[mcp]"
codex-mail-bridge --version
```

No GitHub repository or package-registry publication is required. The base
package has no third-party runtime dependencies; the `mcp` extra adds the MCP SDK.

## Configure your mailbox

```sh
codex-mail-bridge init
codex-mail-bridge doctor --network
```

The setup asks for your provider's SMTP and IMAP endpoints and hides password
entry. Enable these protocols with your provider and use an app password or
authorization code where required. Setup does not send mail or install a service.
The optional network check performs only an IMAP TLS login; it is not a complete
delivery or desktop compatibility check.

For manual configuration, `codex-mail-bridge init --example` creates a private
template. Edit its placeholder values, then run `codex-mail-bridge set-password`.
The repository's [example](examples/config.example.json) contains no credentials.

Connection settings go to `~/.config/codex-mail-bridge/config.json`; credentials
go to a separate `credentials.json` with mode 0600 in that mode-0700 directory.
`CODEX_MAIL_BRIDGE_PASSWORD` is an alternative for foreground commands. Do not
paste credentials into chat, shell arguments, or this repository.

## First notification and reply

Start the listener in another terminal:

```sh
codex-mail-bridge listen
```

From a shell tool **inside the target Codex chat**, send:

```sh
codex-mail-bridge send --title 'Your input is needed' 'Please review the result.'
```

The CLI reads `CODEX_THREAD_ID` in that shell. Outside Codex, supply the actual
UUID with `--thread-id`. A missing ID is an error; `--one-way` explicitly sends
an email without reply routing. Use `--dry-run` to preview without credentials
or network access.

On your phone, **reply directly to that email and write above the quoted text**.
New text is submitted to the same chat. Default polling is 15 seconds. The Mac
must be online, with the desktop app running, signed in, and owning the chat.
Replies are ordinary user input and inherit that chat's execution permissions.
Read [the trust model](SECURITY.md) before enabling the bridge.

## MCP

```sh
codex-mail-bridge mcp-config
```

Add the printed server table to your existing user-level Codex configuration,
preserving other settings, then reload MCP or open a new local chat. Generation
does not modify Codex configuration. It prints the active Python interpreter,
so invoke it from the environment in which you installed the package.

Tools:

| Tool | Input / purpose |
|---|---|
| `send_notification` | `title`, `message`, **real `thread_id`** |
| `notification_status` | Heartbeat and delivery counts; no message contents |

Always provide the current chat's UUID to MCP. A shell tool in that chat can
read `CODEX_THREAD_ID`; the MCP process is not assumed to know which chat called
it. Never freeze a thread UUID into a global server configuration.

Authoritative Codex setup reference: [local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp#connect-codex-to-an-mcp-server).

## Background service and removal

After configuring a private local credentials file:

```sh
codex-mail-bridge service install --dry-run
codex-mail-bridge service install
codex-mail-bridge status
```

The opt-in installer creates only `org.codexmailbridge.listener` for the current
macOS user. It does not register MCP or edit other services. Use `--replace`
only when updating this project's existing service definition. Keep its Python
environment installed. Shell-only password variables are not copied into the plist.

```sh
codex-mail-bridge service uninstall
```

Uninstalling the service retains private configuration and history. Remove the
MCP table you added and uninstall the package with `python -m pip uninstall
codex-mail-bridge` when desired. Review and delete the private config/state
directories yourself if you also want to remove credentials and delivery records.

## Limits and compatibility

- Desktop submission is experimental and macOS-only. See [compatibility](docs/compatibility.md).
- The original prototype received a real mobile reply in an active chat. The
  standalone package is validated with isolated tests; idle recovery still needs
  an explicit live end-to-end test on each supported desktop build.
- Notifications expire after 14 days. Messages larger than 512 KiB and new reply
  bodies over 24,000 characters are not forwarded; attachments are not commands.
- Failed or uncertain desktop submissions are recorded, not automatically
  replayed. Check status and logs before manually acting. There is no replay UI.
- IMAP reconnects after transient errors. A changed UIDVALIDITY requires manual
  review; historical messages are not blindly replayed.
- This is a single-user correlation mechanism, not cryptographic email-sender
  authentication or a general-purpose remote execution gateway.

More: [configuration](docs/configuration.md), [architecture](docs/architecture.md),
[security](SECURITY.md), [development](CONTRIBUTING.md), [local release validation](docs/validation.md).
