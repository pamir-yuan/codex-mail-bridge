# Contributing

Use Python 3.11 or newer in an isolated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[mcp,dev]"
python -m unittest discover -s tests -v
python scripts/check_public_tree.py
python -m build
python scripts/check_public_tree.py --archives
```

Tests use temporary directories, synthetic mail and mocked desktop calls.
Never run test listeners against your daily mailbox or load personal Codex
threads. Set the documented config, state and CODEX_HOME overrides when making
local experiments. Unit tests are not a live compatibility claim.

Preserve these properties when changing the implementation:

- Explicit real target UUID, exact mailbox matching and random reference correlation.
- No credentials in tool arguments, application logs, repository or distribution archives.
- Safe behavior after a provider rewrites Message-ID.
- No automatic second desktop submission after an uncertain response.
- MCP stdout contains protocol messages only; diagnostics go to stderr.
- Installing the Python package alone performs no mailbox, service or Codex configuration changes.

Document a desktop protocol change with synthetic fixtures and the observed
public application version. Do not commit extracted proprietary application
code, local reverse-engineering artifacts, account data or copied chat histories.
