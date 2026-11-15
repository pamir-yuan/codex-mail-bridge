"""Connection settings and private credentials for a single self-notifying mailbox."""
import json
import os
from pathlib import Path
import stat
import tempfile
from email.utils import parseaddr

from .paths import config_dir


class ConfigError(Exception):
    pass


def example_config():
    return {
        "smtp_host": "smtp.example.com", "port": 465, "security": "ssl",
        "username": "you@example.com", "from": "you@example.com", "to": "you@example.com",
        "imap_host": "imap.example.com", "imap_port": 993, "mailbox": "INBOX", "poll_seconds": 15,
    }


def single_line(value, name):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\x00"):
        raise ConfigError(f"{name} must be a nonempty single line")
    return value.strip()


def email_address(value):
    value = single_line(value, "email address")
    name, address = parseaddr(value)
    if name or address != value or address.count("@") != 1 or any(c.isspace() for c in address):
        raise ConfigError("Use a single ASCII email address without a display name")
    local, domain = address.rsplit("@", 1)
    if not local or not domain:
        raise ConfigError("Invalid email address")
    try:
        address.encode("ascii")
    except UnicodeEncodeError:
        raise ConfigError("Mailbox addresses must be ASCII; message text can be Unicode") from None
    return address


def _port(value, name):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ConfigError(f"{name} must be an integer from 1 to 65535")
    return value


def validate(config):
    if not isinstance(config, dict):
        raise ConfigError("Configuration must be a JSON object")
    if any(k in config for k in ("password", "smtp_password", "imap_password", "token", "api_key")):
        raise ConfigError("Store credentials separately, not in config.json")
    result = dict(config)
    for key in ("smtp_host", "imap_host", "username", "mailbox"):
        result[key] = single_line(config.get(key), key)
    for key in ("smtp_host", "imap_host"):
        if "://" in result[key] or "/" in result[key] or any(c.isspace() for c in result[key]):
            raise ConfigError(f"{key} must be a host name, not a URL")
    if config.get("security") not in ("ssl", "starttls"):
        raise ConfigError("security must be ssl or starttls; plaintext SMTP is unsupported")
    result["port"] = _port(config.get("port"), "port")
    result["imap_port"] = _port(config.get("imap_port", 993), "imap_port")
    recipient = config.get("to")
    if isinstance(recipient, list):
        if len(recipient) != 1:
            raise ConfigError("Exactly one self-notification recipient is supported")
        recipient = recipient[0]
    result["from"] = email_address(config.get("from"))
    recipient = email_address(recipient)
    if result["from"].casefold() != recipient.casefold():
        raise ConfigError("Version 0.1 requires the sender and recipient to be the same mailbox")
    result["to"] = [recipient]
    poll = config.get("poll_seconds", 15)
    if type(poll) is not int or not 5 <= poll <= 300:
        raise ConfigError("poll_seconds must be an integer from 5 to 300")
    result["poll_seconds"] = poll
    return result


def load(path=None):
    path = Path(path) if path is not None else config_dir()/"config.json"
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise ConfigError("Run codex-mail-bridge init to configure a mailbox") from None
    except (OSError, UnicodeError, ValueError):
        raise ConfigError("Unable to read configuration; check JSON format and file permissions") from None


def write_private_json(path, value, overwrite=False):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise ConfigError("Private configuration paths must not be symlinks")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists() and not overwrite:
        raise ConfigError("Configuration already exists; refusing to overwrite it")
    handle, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber installation, including concurrent init calls.
            os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_password(config_path=None):
    value = os.environ.get("CODEX_MAIL_BRIDGE_PASSWORD")
    if value is None:
        parent = Path(config_path).parent if config_path is not None else config_dir()
        path = parent/"credentials.json"
        try:
            if path.is_symlink() or parent.is_symlink():
                raise ConfigError("Credential paths must not be symlinks")
            if stat.S_IMODE(parent.stat().st_mode) != 0o700:
                raise ConfigError("Credential directory permissions must be 0700")
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ConfigError("Credential file must be a regular file with permissions 0600")
            value = json.loads(path.read_text(encoding="utf-8")).get("password")
        except FileNotFoundError:
            raise ConfigError("No credentials: run init or set CODEX_MAIL_BRIDGE_PASSWORD") from None
        except (OSError, ValueError, AttributeError):
            raise ConfigError("Unable to read private credentials") from None
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00"):
        raise ConfigError("Mailbox password/app password must be nonempty single-line text")
    return value
