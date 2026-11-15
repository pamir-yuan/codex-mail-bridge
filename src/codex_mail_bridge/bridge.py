#!/usr/bin/env python3
"""Local email-to-Codex bridge. No mailbox contents are logged."""
import contextlib
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
import fcntl
import imaplib
import logging
import os
import re
import secrets
import signal
import sqlite3
import ssl
import sys
import time
import uuid

from . import mail as notify
from .desktop_ipc import DesktopClient
from .paths import state_dir, desktop_state_db

STATE_DIR = state_dir()
LOG = logging.getLogger('email-bridge')
MAX_MAIL_BYTES = 512 * 1024
MAX_REPLY_CHARS = 24000
TTL_SECONDS = 14 * 86400


class BridgeError(Exception):
    pass


def settings():
    return notify.read_config(notify.DEFAULT_CONFIG)


def store():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE_DIR.chmod(0o700)
    path = STATE_DIR / 'bridge.sqlite3'
    if path.is_symlink():
        raise BridgeError('State file must not be a symlink')
    # Restrict permissions before sqlite creates journals as well.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    path.chmod(0o600)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript('''
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS notifications(
        id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, message_id TEXT UNIQUE NOT NULL,
        recipient TEXT NOT NULL, title TEXT NOT NULL, created REAL NOT NULL,
        status TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS replies(
        mail_key TEXT PRIMARY KEY, message_id TEXT UNIQUE NOT NULL,
        notification_id TEXT NOT NULL, status TEXT NOT NULL,
        created REAL NOT NULL, queue_id TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS message_aliases(
        message_id TEXT PRIMARY KEY, notification_id TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      INSERT OR IGNORE INTO message_aliases SELECT message_id,id FROM notifications;
    ''')
    return db


def meta(db, key, value=None):
    if value is not None:
        with db:
            db.execute('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, str(value)))
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else None


@contextlib.contextmanager
def database():
    db = store()
    try:
        yield db
    finally:
        db.close()


def thread_info(thread_id):
    try:
        thread_id = str(uuid.UUID(thread_id))
    except (ValueError, TypeError, AttributeError):
        raise BridgeError('A real Codex thread UUID is required; never guess a chat name') from None
    uri = desktop_state_db().resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        row = db.execute('SELECT title,cwd,archived FROM threads WHERE id=?', (thread_id,)).fetchone()
    if not row or row[2]:
        raise BridgeError('Target chat does not exist locally or is archived')
    return {'id': thread_id, 'title': row[0], 'cwd': row[1]}


def imap_connection():
    cfg = settings()
    mail = notify.read_config(notify.DEFAULT_CONFIG)
    connection = imaplib.IMAP4_SSL(cfg['imap_host'], cfg['imap_port'],
                                 ssl_context=ssl.create_default_context(), timeout=25)
    try:
        connection.login(mail['username'], notify.read_password(notify.DEFAULT_CONFIG))
        status, _ = connection.select(cfg['mailbox'], readonly=True)
        if status != 'OK':
            raise BridgeError('Unable to open the configured mailbox read-only')
        return connection
    except BaseException:
        with contextlib.suppress(Exception):
            connection.logout()
        raise


def baseline(db, connection):
    validity = connection.response('UIDVALIDITY')[1][0].decode()
    next_uid = int(connection.response('UIDNEXT')[1][0])
    previous = meta(db, 'uidvalidity')
    if previous is None:
        meta(db, 'uidvalidity', validity)
        meta(db, 'last_uid', next_uid - 1)
    elif previous != validity:
        # Do not silently discard replies after a mailbox UID reset.
        raise BridgeError('Mailbox UIDVALIDITY changed; reset cursor requires manual review')
    return validity


def initialize_mailbox():
    with database() as db:
        connection = imap_connection()
        try:
            baseline(db, connection)
        finally:
            with contextlib.suppress(Exception):
                connection.logout()
    return {'imap': 'ready'}


def send_notification(title, message, thread_id=None):
    if not isinstance(title, str) or not title.strip() or len(title) > 180 or '\n' in title or '\r' in title:
        raise BridgeError('Title must be a nonempty single line, at most 180 characters')
    if not isinstance(message, str) or not message.strip() or len(message) > 24000:
        raise BridgeError('Message must contain 1–24000 characters')
    info = thread_info(thread_id or os.environ.get('CODEX_THREAD_ID'))
    cfg = notify.read_config(notify.DEFAULT_CONFIG)
    if len(cfg['to']) != 1:
        raise BridgeError('Reply-enabled notifications require exactly one configured recipient')
    with database() as db:
        if meta(db, 'uidvalidity') is None:
            initialize_mailbox()
        identifier = secrets.token_hex(24)
        mid = f'<codex-reply-{identifier}@bridge.test>'
        body = (f'{message.strip()}\n\n'
                f'Chat: {info["title"]}\n'
                'Reply directly to this email and write new text above the quoted original.\n'
                'The local listener routes your new text back to this chat. Do not include credentials.')
        mail = notify.build_message(cfg, title.strip(), body)
        mail.replace_header('Message-ID', mid)
        mail['Auto-Submitted'] = 'auto-generated'
        # QQ Mail rewrites Message-ID. This independent random header lets the
        # listener learn its canonical ID from the delivered original message.
        mail['X-Codex-Email-Bridge'] = 'notification; id=' + identifier
        with db:
            db.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,?)',
                       (identifier, info['id'], mid, cfg['to'][0].lower(), title.strip(), time.time(), 'sending'))
            db.execute('INSERT INTO message_aliases VALUES (?,?)',(mid,identifier))
        try:
            # notify.deliver's human-readable stdout would corrupt MCP's stdio channel.
            with contextlib.redirect_stdout(sys.stderr):
                result = notify.deliver(cfg, notify.read_password(notify.DEFAULT_CONFIG), mail)
            if result:
                raise BridgeError('SMTP did not accept the notification')
        except BaseException:
            with db:
                db.execute('UPDATE notifications SET status=? WHERE id=?', ('send_failed', identifier))
            raise
        with db:
            db.execute('UPDATE notifications SET status=? WHERE id=?', ('sent', identifier))
    return {'status': 'smtp_accepted', 'reply_enabled': True, 'thread_id': info['id'],
            'note': 'Direct email replies are relayed to this exact chat; phone delivery is not independently verified.'}


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.skipped = 0
    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        quoted = tag in ('blockquote', 'script', 'style') or any(
            item in (attr.get('class', '') + ' ' + attr.get('id', '')).lower()
            for item in ('gmail_quote', 'divrplyfwdmsg', 'qqmail_quote'))
        if self.skipped:
            if tag not in ('br','img','hr','meta','link','input','wbr'):
                self.skipped += 1
        elif quoted:
            self.skipped = 1
        elif tag in ('br','p','div','li','tr','hr'):
            self.output.append('\n')
    def handle_endtag(self, tag):
        if self.skipped:
            if tag not in ('br','img','hr','meta','link','input','wbr'):
                self.skipped -= 1
        elif tag in ('p','div','li','tr'):
            self.output.append('\n')
    def handle_data(self, data):
        if not self.skipped:
            self.output.append(data)


QUOTE_LINE = re.compile(
    r'^\s*(?:>.*|On .{1,350}wrote:|在.{1,350}写道[：:]|'
    r'[-_－—]{2,}\s*(?:Original Message|原始邮件|原邮件|转发邮件).{0,80}|'
    r'(?:发件人|寄件者|From)\s*[:：].*)$', re.I)
SIGNATURE = re.compile(r'^\s*(?:--\s*|(?:发自我的|发送自|Sent from my|获取 Outlook).*)$', re.I)


def extract_reply(message):
    part = message.get_body(preferencelist=('plain', 'html'))
    if part is None:
        raise BridgeError('No supported text body in the email reply')
    text = part.get_content()
    if not isinstance(text, str):
        raise BridgeError('Unable to decode email text')
    if part.get_content_type() == 'text/html':
        parser = TextHTML()
        parser.feed(text)
        text = ''.join(parser.output)
    lines = []
    for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        if QUOTE_LINE.match(line) or SIGNATURE.match(line):
            break
        lines.append(line.rstrip())
    result = '\n'.join(lines).strip()
    if not result or len(result) > MAX_REPLY_CHARS:
        raise BridgeError('Reply is empty after removing quotes, or exceeds 24000 characters')
    return result


def match_notification(db, message):
    if str(message.get('Auto-Submitted', 'no')).lower() != 'no' or message.get('X-Codex-Email-Bridge'):
        return None
    refs = re.findall(r'<[^<>\s]+>', str(message.get('References', '')) + ' ' + str(message.get('In-Reply-To', '')))
    matches = []
    for ref in dict.fromkeys(refs):
        row = db.execute('SELECT n.* FROM notifications n WHERE (n.message_id=? OR n.id IN '
                         '(SELECT notification_id FROM message_aliases WHERE message_id=?)) '
                         'AND n.status=? AND n.created>?',
                         (ref, ref, 'sent', time.time()-TTL_SECONDS)).fetchone()
        if row:
            matches.append(row)
    if not matches or len({r['thread_id'] for r in matches}) != 1:
        return None
    selected = matches[-1]
    senders = [addr.lower() for _,addr in getaddresses(message.get_all('From', []))]
    if senders != [selected['recipient']]:
        return None
    return selected


def register_outgoing(db, message):
    """Learn server-rewritten Message-ID only from a matching random header."""
    marker = re.fullmatch(r'notification;\s*id=([0-9a-f]{48})',
                          str(message.get('X-Codex-Email-Bridge','')).strip())
    mid = str(message.get('Message-ID','')).strip()
    if not marker or not re.fullmatch(r'<[^<>\s]+>',mid):
        return False
    notice = db.execute("SELECT * FROM notifications WHERE id=? AND status IN ('sending','sent')",(marker[1],)).fetchone()
    if notice is None:
        return False
    cfg = notify.read_config(notify.DEFAULT_CONFIG)
    senders = [a.lower() for _,a in getaddresses(message.get_all('From',[]))]
    recipients = [a.lower() for _,a in getaddresses(message.get_all('To',[]))]
    if senders != [cfg['from'].lower()] or notice['recipient'] not in recipients:
        return False
    with db:
        db.execute('INSERT OR IGNORE INTO message_aliases VALUES (?,?)',(mid,notice['id']))
    return True


def dispatch(thread_id, reply_text):
    info = thread_info(thread_id)
    body = ('[Direct reply to your notification email]\n' + reply_text)
    with DesktopClient() as desktop:
        return desktop.submit_reply(info['id'],body)


def process_reply(db, raw, mail_key, dispatch_fn=dispatch):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    notification = match_notification(db, message)
    if notification is None:
        return 'ignored'
    mid = str(message.get('Message-ID','')).strip()
    if not mid or len(mid) > 998:
        return 'ignored'
    try:
        text = extract_reply(message)
    except BridgeError:
        return 'empty_or_unsupported'
    with db:
        inserted = db.execute('INSERT OR IGNORE INTO replies VALUES (?,?,?,?,?,?,?)',
                              (mail_key, mid, notification['id'], 'delivering', time.time(), None, None)).rowcount
    if not inserted:
        return 'duplicate'
    try:
        result = dispatch_fn(notification['thread_id'], text)
    except Exception as error:
        # Keep uncertain submissions for review instead of blindly submitting twice.
        with db:
            db.execute('UPDATE replies SET status=?,error=? WHERE mail_key=?',
                       ('failed', type(error).__name__, mail_key))
        LOG.error('reply_delivery_failed kind=%s; review required', type(error).__name__)
        return 'failed'
    status = result.get('status') or ('queued_resume_warning' if result.get('resume_warning') else 'queued')
    with db:
        db.execute('UPDATE replies SET status=?,queue_id=? WHERE mail_key=?', (status, result['queue_id'], mail_key))
    LOG.info('reply_submitted status=%s', status)
    return status


def poll_once():
    with database() as db:
        connection = imap_connection()
        try:
            validity = baseline(db, connection)
            last = int(meta(db, 'last_uid'))
            status, values = connection.uid('search', None, 'UID', f'{last+1}:*')
            if status != 'OK':
                raise BridgeError('IMAP UID search failed')
            counts = {}
            for uid in sorted({int(i) for i in values[0].split() if int(i) > last}):
                status, headers = connection.uid('fetch', str(uid),
                    '(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO MESSAGE-ID REFERENCES IN-REPLY-TO AUTO-SUBMITTED X-CODEX-EMAIL-BRIDGE)])')
                if status != 'OK':
                    raise BridgeError('IMAP header fetch failed')
                header = next((v for v in headers if isinstance(v, tuple)), None)
                if header is None:
                    meta(db, 'last_uid', uid)
                    continue
                parsed = BytesParser(policy=policy.default).parsebytes(header[1])
                register_outgoing(db, parsed)
                candidate = match_notification(db, parsed)
                size = re.search(rb'RFC822.SIZE (\d+)', header[0])
                outcome = 'ignored'
                if candidate and size and int(size[1]) <= MAX_MAIL_BYTES:
                    status, full = connection.uid('fetch', str(uid), '(BODY.PEEK[])')
                    if status != 'OK':
                        raise BridgeError('IMAP reply fetch failed')
                    raw = next((v[1] for v in full if isinstance(v, tuple)), None)
                    if raw is None:
                        raise BridgeError('IMAP reply fetch returned no body')
                    outcome = process_reply(db, raw, f'{validity}:{uid}')
                counts[outcome] = counts.get(outcome,0)+1
                meta(db, 'last_uid', uid)
            meta(db, 'last_poll', time.time())
            meta(db, 'last_poll_error', '')
            return counts
        finally:
            with contextlib.suppress(Exception):
                connection.logout()


def status_report():
    result = {'smtp_configured': notify.DEFAULT_CONFIG.exists(),
              'imap_initialized': False, 'last_poll_at': None,
              'last_poll_age_seconds': None, 'last_poll_error': '',
              'sent_notifications': 0, 'reply_statuses': {}}
    path = STATE_DIR/'bridge.sqlite3'
    if not path.exists():
        return result
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory = sqlite3.Row
        last_poll = meta(db, 'last_poll')
        return {'smtp_configured': notify.DEFAULT_CONFIG.exists(),
                'imap_initialized': meta(db,'uidvalidity') is not None,
                'last_poll_at': datetime.fromtimestamp(float(last_poll),timezone.utc).isoformat() if last_poll else None,
                'last_poll_age_seconds': round(time.time()-float(last_poll)) if last_poll else None,
                'last_poll_error': meta(db,'last_poll_error'),
                'sent_notifications': db.execute("SELECT count(*) FROM notifications WHERE status='sent'").fetchone()[0],
                'reply_statuses': dict(db.execute('SELECT status,count(*) FROM replies GROUP BY status').fetchall())}


def listen():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (STATE_DIR / 'listener.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise BridgeError('A listener is already running') from None
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info('listener_started')
    while not stopped:
        try:
            poll_once()
        except Exception as error:
            # Network reconnection never resubmits an already recorded reply.
            LOG.error('poll_failed kind=%s', type(error).__name__)
            with database() as db:
                meta(db, 'last_poll_error', type(error).__name__)
        for _ in range(settings()['poll_seconds']):
            if stopped:
                break
            time.sleep(1)
    LOG.info('listener_stopped')
