"""Install a separate macOS user service only on an explicit CLI request."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from .config import ConfigError, load
from .paths import config_dir, state_dir

LABEL = "org.codexmailbridge.listener"


def plist_path():
    return Path.home()/"Library/LaunchAgents"/(LABEL+".plist")


def plist_bytes():
    # Preserve a virtual environment's interpreter path; resolving symlinks
    # would accidentally switch to an interpreter without the installed package.
    environment = {"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("CODEX_MAIL_BRIDGE_CONFIG_DIR", "CODEX_MAIL_BRIDGE_STATE_DIR", "CODEX_HOME",
                "CODEX_MAIL_BRIDGE_IPC_SOCKET", "CODEX_MAIL_BRIDGE_CODEX_STATE_DB"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "codex_mail_bridge", "listen"],
        "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 30,
        "EnvironmentVariables": environment,
        "StandardOutPath": str(state_dir()/"listener.stdout.log"),
        "StandardErrorPath": str(state_dir()/"listener.log"),
    })


def _run(*args, allow_missing=False):
    result = subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=20)
    if result.returncode and not allow_missing:
        raise ConfigError("launchctl failed; inspect the user service in your local terminal")
    return result.returncode


def install(dry_run=False, replace=False):
    if sys.platform != "darwin":
        raise ConfigError("The desktop bridge and service installer currently support macOS only")
    data = plist_bytes()
    if dry_run:
        return data.decode()
    load()
    if not (config_dir()/"credentials.json").is_file():
        raise ConfigError("The login service needs a local credentials file; run set-password first")
    target = plist_path()
    if target.is_symlink() or (target.exists() and not replace):
        raise ConfigError("Service file already exists; use --replace to update this service")
    state_dir().mkdir(parents=True, mode=0o700, exist_ok=True)
    state_dir().chmod(0o700)
    target.parent.mkdir(parents=True, exist_ok=True)
    if replace:
        _run("bootout", f"gui/{os.getuid()}/"+LABEL, allow_missing=True)
    target.write_bytes(data)
    target.chmod(0o600)
    _run("bootstrap", f"gui/{os.getuid()}", str(target))
    return "Installed the current user's background service"


def uninstall():
    if sys.platform != "darwin":
        raise ConfigError("The service installer currently supports macOS only")
    target = plist_path()
    if target.is_symlink():
        raise ConfigError("Refusing to remove a symlinked service file")
    if target.exists():
        _run("bootout", f"gui/{os.getuid()}/"+LABEL, allow_missing=True)
        target.unlink()
    return "Service removed; private configuration and message records were retained"
