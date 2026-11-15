#!/usr/bin/env python3
"""Send a short task notification over authenticated, encrypted SMTP."""

from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import smtplib
import ssl
import sys


from .config import ConfigError, load as read_config, read_password
from .paths import config_dir

DEFAULT_CONFIG = config_dir() / "config.json"
TIMEOUT_SECONDS = 15


def build_message(config, subject, body):
    message = EmailMessage()
    message["From"] = config["from"]
    message["To"] = ", ".join(config["to"])
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(body, charset="utf-8")
    return message


def deliver(config, password, message):
    context = ssl.create_default_context()
    if config["security"] == "ssl":
        connection = smtplib.SMTP_SSL(
            config["smtp_host"], config["port"], timeout=TIMEOUT_SECONDS, context=context
        )
    else:
        connection = smtplib.SMTP(
            config["smtp_host"], config["port"], timeout=TIMEOUT_SECONDS
        )
    with connection as smtp:
        if config["security"] == "starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(config["username"], password)
        refused = smtp.send_message(message, from_addr=config["from"], to_addrs=config["to"])
        if refused:
            print("SMTP did not accept all recipients; not retried.", file=sys.stderr)
            return 1
    print("SMTP accepted the email; mailbox delivery and user receipt are not independently verified.")
    return 0
