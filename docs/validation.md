# Local release validation

Validated on 2026-11-15, before any repository or package publication.
This is a local preview, not a live compatibility certification.

## Completed checks

- Built both a source archive and a wheel using the PEP 517 build frontend.
  The wheel was built from the source archive.
- Installed the wheel in a temporary Python 3.14 environment outside the checkout.
- Ran all **34 tests successfully** against that installed package, including
  real MCP stdio initialization, tool discovery, a read-only status request and
  rejection of an invalid target before any network or state creation.
- Exercised nine installed CLI commands from a separate temporary working
  directory: version, help, status, example setup, send preview, local doctor,
  MCP config generation, service-install preview and service-uninstall preview.
  These checks used an isolated home, configuration, state and desktop profile.
  No credential file, service, message state, SMTP connection or desktop turn
  was created.
- Checked source files and both distribution archives for non-example email
  literals, absolute personal home paths, literal session UUIDs, selected secret
  formats and forbidden credential/runtime files. No findings remained.
- Initialized a local Git repository with no commits or remotes. The private
  prototype's source and running service were left in place.

Tests cover reference correlation, provider-rewritten identifiers, cross-chat
ambiguity, sender mismatch, automated loops, replay deduplication, expiration,
plain-text / HTML quote removal, self-closing HTML elements, preserving command
options, active steering, explicit idle fallback, uncertain submission handling,
private credential permissions and MCP/configuration isolation.

## Not established by these checks

The original prototype received a real mobile reply in an active desktop chat.
The independent package was not connected to a real mailbox during packaging.
Real idle-chat recovery, sleep/wake, provider-specific failures and compatibility
after desktop upgrades still need explicit end-to-end validation. See
[compatibility](compatibility.md) and [security](../SECURITY.md).

CI is prepared for macOS with Python 3.11 and 3.14, but has not run on GitHub.
No publishing or deployment workflow is included.

## Repeat locally

Follow [Contributing](../CONTRIBUTING.md) to install development dependencies,
run tests, build, and inspect archives. With the optional MCP SDK absent, the
stdio integration test is skipped; install the `mcp` extra to run all 34 tests.
Use a fresh temporary environment and the documented path overrides for any
installed-package checks. Never use a daily mailbox or real desktop profile for
synthetic tests.

The public-tree checker is a targeted review aid, not a complete secret scanner.
It cannot establish that arbitrary opaque strings or future additions contain
no private information. Review the staged files before eventual publication.
