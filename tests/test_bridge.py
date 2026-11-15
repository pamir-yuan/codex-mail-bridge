from email.message import EmailMessage
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_mail_bridge import bridge


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(bridge, 'STATE_DIR', Path(self.temp.name))
        self.path_patch.start()
        self.db = bridge.store()
        self.add_notice('notice1', 'thread-a', '<codex-reply-random-one@bridge.test>')
        self.calls = []

    def tearDown(self):
        self.db.close()
        self.path_patch.stop()
        self.temp.cleanup()

    def add_notice(self, identifier, thread, mid, created=None):
        with self.db:
            self.db.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,?)',
                (identifier, thread, mid, 'user@example.com', '任务需要回复', created or time.time(), 'sent'))

    def email(self, body='可以继续\n\nOn Sunday, Codex wrote:\n> 不应转交的旧指令'):
        m = EmailMessage()
        m['From'] = 'User <user@example.com>'
        m['To'] = 'user@example.com'
        m['Message-ID'] = '<reply-1@example.com>'
        m['In-Reply-To'] = '<codex-reply-random-one@bridge.test>'
        m.set_content(body)
        return m

    def dispatch(self, thread, text):
        self.calls.append((thread, text))
        return {'queue_id': 'queue-1', 'resume_warning': False}

    def process(self, m, key='1:100'):
        return bridge.process_reply(self.db, m.as_bytes(), key, self.dispatch)

    def test_routes_only_new_text_to_original_thread(self):
        self.assertEqual(self.process(self.email()), 'queued')
        self.assertEqual(self.calls, [('thread-a', '可以继续')])

    def test_same_message_not_replayed_with_different_uid(self):
        m = self.email()
        self.process(m)
        self.assertEqual(self.process(m, '1:101'), 'duplicate')
        self.assertEqual(len(self.calls), 1)

    def test_sender_and_random_reference_required(self):
        for field, value in [('From', 'stranger@example.com'),
                             ('In-Reply-To', '<unknown@bridge.test>')]:
            m = self.email()
            m.replace_header(field,value)
            self.assertEqual(self.process(m), 'ignored')
        self.assertEqual(self.calls, [])

    def test_outgoing_and_auto_reply_do_not_loop(self):
        for field, value in [('Auto-Submitted','auto-replied'),
                             ('X-Codex-Email-Bridge','notification')]:
            m = self.email()
            m[field] = value
            self.assertEqual(self.process(m), 'ignored')

    def test_two_different_threads_are_ambiguous(self):
        self.add_notice('notice2','thread-b','<codex-reply-random-two@bridge.test>')
        m = self.email()
        m['References'] = '<codex-reply-random-two@bridge.test>'
        self.assertEqual(self.process(m), 'ignored')

    def test_reference_only_and_chinese_quote(self):
        m = self.email('采用第二个方案。\n\n------------------ 原始邮件 ------------------\n发件人：Codex\n旧指令')
        del m['In-Reply-To']
        m['References'] = '<codex-reply-random-one@bridge.test>'
        self.assertEqual(self.process(m), 'queued')
        self.assertEqual(self.calls[0][1], '采用第二个方案。')

    def test_html_only_drops_quotes_scripts_and_attachments(self):
        m = self.email()
        m.set_content('<div>中文意见</div><blockquote><p>旧指令</p></blockquote><script>bad()</script>',subtype='html')
        m.add_attachment(b'not a command', maintype='text', subtype='plain', filename='instructions.txt')
        self.assertEqual(self.process(m), 'queued')
        self.assertEqual(self.calls[0][1], '中文意见')

    def test_empty_quoted_only_not_forwarded(self):
        self.assertEqual(self.process(self.email('> 旧内容\n')), 'empty_or_unsupported')
        self.assertEqual(self.calls, [])

    def test_self_closing_images_inside_html_quote_stay_ignored(self):
        m = self.email()
        m.set_content('<div>Proceed</div><blockquote><img src="cid:old"/><br/>old command</blockquote>', subtype='html')
        self.assertEqual(self.process(m), 'queued')
        self.assertEqual(self.calls[0][1], 'Proceed')

    def test_command_option_is_not_mistaken_for_signature(self):
        self.assertEqual(self.process(self.email('Use this option:\n--verbose\n\n-- \nSignature')), 'queued')
        self.assertEqual(self.calls[0][1], 'Use this option:\n--verbose')

    def test_expired_notification_not_accepted(self):
        with self.db:
            self.db.execute('UPDATE notifications SET created=?', (time.time()-bridge.TTL_SECONDS-1,))
        self.assertEqual(self.process(self.email()), 'ignored')

    def test_uncertain_delivery_is_not_automatically_repeated(self):
        def failure(*_):
            self.calls.append('attempt')
            raise TimeoutError('private content must not be logged')
        m = self.email()
        with self.assertLogs(bridge.LOG,level='ERROR') as logs:
            self.assertEqual(bridge.process_reply(self.db,m.as_bytes(),'1:100',failure),'failed')
        self.assertNotIn('private content',''.join(logs.output))
        self.assertEqual(bridge.process_reply(self.db,m.as_bytes(),'1:101',failure),'duplicate')
        self.assertEqual(len(self.calls),1)

    def test_provider_rewritten_message_id_still_routes(self):
        identifier = 'a'*48
        self.add_notice(identifier,'thread-c','<local-original@bridge.test>')
        original = EmailMessage()
        original['From'] = 'user@example.com'
        original['To'] = 'user@example.com'
        original['Message-ID'] = '<provider-rewritten@example.test>'
        original['X-Codex-Email-Bridge'] = 'notification; id=' + identifier
        with patch.object(bridge.notify,'read_config',return_value={'from':'user@example.com'}):
            self.assertTrue(bridge.register_outgoing(self.db,original))
        m = self.email()
        m.replace_header('In-Reply-To','<provider-rewritten@example.test>')
        self.assertEqual(self.process(m),'queued')
        self.assertEqual(self.calls[0][0],'thread-c')


if __name__ == '__main__':
    unittest.main()
