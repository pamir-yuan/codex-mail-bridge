"""Runtime locations; no user configuration is stored in the source tree."""
import os
from pathlib import Path


def config_dir():
    return Path(os.environ.get("CODEX_MAIL_BRIDGE_CONFIG_DIR", "~/.config/codex-mail-bridge")).expanduser()


def state_dir():
    return Path(os.environ.get("CODEX_MAIL_BRIDGE_STATE_DIR", "~/.local/state/codex-mail-bridge")).expanduser()


def codex_home():
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def desktop_socket():
    return Path(os.environ.get("CODEX_MAIL_BRIDGE_IPC_SOCKET", str(codex_home()/"ipc/ipc.sock"))).expanduser()


def desktop_state_db():
    return Path(os.environ.get("CODEX_MAIL_BRIDGE_CODEX_STATE_DB", str(codex_home()/"state_5.sqlite"))).expanduser()
