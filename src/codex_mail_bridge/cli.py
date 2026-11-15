"""Command-line entry points; importing the package performs no setup or network IO."""
import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import platform
import sys

from . import __version__
from .config import ConfigError, example_config, load, read_password, validate, write_private_json
from .paths import config_dir, state_dir, desktop_socket, desktop_state_db


def initialize(example=False, no_password=False):
    target = config_dir()/"config.json"
    if target.exists() or target.is_symlink():
        raise ConfigError("Configuration already exists; edit it locally or use set-password")
    value = example_config()
    if not example:
        if not sys.stdin.isatty():
            raise ConfigError("Interactive setup requires a terminal; use init --example for a template")
        email = input("Your mailbox address (sender and recipient): ").strip()
        value.update({"username": email, "from": email, "to": email})
        value["smtp_host"] = input("SMTP host: ").strip()
        value["imap_host"] = input("IMAP host: ").strip()
        security = input("SMTP security [ssl/starttls, default ssl]: ").strip() or "ssl"
        value["security"] = security
        port = input(f"SMTP port [default {465 if security == 'ssl' else 587}]: ").strip()
        value["port"] = int(port) if port else (465 if security == "ssl" else 587)
        imap_port = input("IMAP TLS port [default 993]: ").strip()
        value["imap_port"] = int(imap_port) if imap_port else 993
        value["mailbox"] = input("IMAP folder [default INBOX]: ").strip() or "INBOX"
    validate(value)
    write_private_json(target,value)
    if not example and not no_password:
        set_password()
    return {"status":"example_created" if example else "configured", "config_file":str(target),
            "note":"No email was sent and no service was installed"}


def set_password():
    if not sys.stdin.isatty():
        raise ConfigError("Run set-password in a terminal; never pass credentials in CLI arguments")
    value = getpass.getpass("Mailbox app password / authorization code (hidden): ")
    if not value or any(c in value for c in "\r\n\x00"):
        raise ConfigError("A nonempty, single-line app password is required")
    write_private_json(config_dir()/"credentials.json", {"password":value}, overwrite=True)
    return {"status":"credentials_saved", "note":"Stored only in the private local configuration directory"}


def doctor(network=False):
    result = {"version":__version__, "platform":platform.system(),
              "desktop_supported":sys.platform=="darwin", "config_present":False,
              "credentials_present":bool(os.environ.get("CODEX_MAIL_BRIDGE_PASSWORD")) or (config_dir()/"credentials.json").is_file(),
              "desktop_socket_present":desktop_socket().is_socket(),
              "desktop_state_db_present":desktop_state_db().is_file()}
    try:
        load()
        result["config_present"] = True
    except ConfigError:
        result["configuration_status"] = "missing_or_invalid"
    if network:
        if not result["config_present"]:
            raise ConfigError("Configure a mailbox before network checks")
        from .bridge import imap_connection
        connection = imap_connection()
        try:
            result["imap_tls_login"] = "ok"
        finally:
            connection.logout()
        # Network checks never send a message or begin a Codex turn.
    return result


def mcp_config():
    result = ('[mcp_servers.codex_mail_bridge]\ncommand = '+json.dumps(sys.executable)+
              '\nargs = ["-m", "codex_mail_bridge", "mcp"]\nenabled = true\n')
    environment = {k:os.environ[k] for k in (
        "CODEX_MAIL_BRIDGE_CONFIG_DIR", "CODEX_MAIL_BRIDGE_STATE_DIR", "CODEX_HOME",
        "CODEX_MAIL_BRIDGE_IPC_SOCKET", "CODEX_MAIL_BRIDGE_CODEX_STATE_DB") if k in os.environ}
    if environment:
        result += '\n[mcp_servers.codex_mail_bridge.env]\n'
        for key,value in environment.items():
            result += key+' = '+json.dumps(value)+'\n'
    return result


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog="codex-mail-bridge",description="Local email notifications and reply routing for Codex Desktop (experimental macOS)")
    parser.add_argument("--version",action="version",version=__version__)
    sub = parser.add_subparsers(dest="command",required=True)
    init = sub.add_parser("init",help="Create private configuration; no network requests")
    init.add_argument("--example",action="store_true")
    init.add_argument("--no-password",action="store_true")
    sub.add_parser("set-password",help="Save an app password using hidden terminal input")
    send = sub.add_parser("send",help="Send one notification; no automatic retries")
    send.add_argument("message")
    send.add_argument("--title",default="Codex task notification")
    send.add_argument("--thread-id",default=os.environ.get("CODEX_THREAD_ID"))
    send.add_argument("--one-way",action="store_true",help="Send without chat reply routing")
    send.add_argument("--dry-run",action="store_true")
    for command in ("mailbox-init","listen","poll","status","mcp","mcp-config"):
        sub.add_parser(command)
    check = sub.add_parser("doctor")
    check.add_argument("--network",action="store_true",help="Test an IMAP TLS login; no messages or model turns")
    service = sub.add_parser("service")
    service.add_argument("action",choices=["install","uninstall"])
    service.add_argument("--dry-run",action="store_true")
    service.add_argument("--replace",action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.example,args.no_password)
        elif args.command == "set-password":
            result = set_password()
        elif args.command == "doctor":
            result = doctor(args.network)
        elif args.command == "mcp-config":
            print(mcp_config(),end="")
            return 0
        elif args.command == "mcp":
            from .mcp_server import run
            run()
            return 0
        elif args.command == "service":
            from . import service
            if args.action == "uninstall" and args.dry_run:
                print("Would stop and remove only "+service.LABEL+"; configuration and state would be retained")
            else:
                print(service.install(args.dry_run,args.replace) if args.action=="install" else service.uninstall())
            return 0
        elif args.command == "send":
            from . import mail
            if not args.message.strip() or len(args.message)>24000:
                raise ConfigError("Message must contain 1–24000 characters")
            if not args.title.strip() or len(args.title)>180 or any(c in args.title for c in "\r\n\x00"):
                raise ConfigError("Title must be one line, at most 180 characters")
            cfg = load()
            if args.dry_run:
                result = {"status":"dry_run", "title":args.title,"message":args.message,
                          "reply_enabled":bool(args.thread_id) and not args.one_way,
                          "credentials_read":False,"network_used":False}
            elif args.one_way:
                message = mail.build_message(cfg,args.title,args.message)
                return mail.deliver(cfg,read_password(),message)
            else:
                if not args.thread_id:
                    raise ConfigError("Pass the real --thread-id, run inside Codex, or explicitly choose --one-way")
                from .bridge import send_notification
                result = send_notification(args.title,args.message,args.thread_id)
        else:
            from . import bridge
            if args.command == "status":
                result = bridge.status_report()
            elif args.command == "mailbox-init":
                result = bridge.initialize_mailbox()
            elif args.command == "poll":
                result = bridge.poll_once()
            else:
                load()  # Fail fast instead of running a misconfigured service forever.
                logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
                bridge.listen()
                return 0
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except ConfigError as error:
        print(str(error),file=sys.stderr)
        return 2
    except ImportError:
        print('Install the MCP extra to use this command: pip install ".[mcp]"',file=sys.stderr)
        return 2
    except Exception as error:
        # Provider and desktop errors can echo submitted content. Do not log them.
        print(f"Operation failed ({type(error).__name__}); inspect local settings and service status",file=sys.stderr)
        return 1
