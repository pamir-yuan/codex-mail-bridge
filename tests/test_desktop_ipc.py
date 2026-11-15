import unittest
from unittest.mock import Mock, patch
from codex_mail_bridge.desktop_ipc import DesktopClient, DesktopError


class DesktopSubmissionTests(unittest.TestCase):
    def client(self):
        client = object.__new__(DesktopClient)
        client.owner = Mock(return_value='owner')
        client.start_turn = Mock(return_value={'requestId':'idle-turn'})
        return client

    def test_busy_chat_is_steered_without_new_turn(self):
        client = self.client()
        client.request = Mock(return_value={'requestId':'active-turn'})
        result = client.submit_reply('chat','继续')
        self.assertEqual(result['desktop_method'],'steer')
        client.start_turn.assert_not_called()
        args = client.request.call_args.args
        self.assertEqual(args[0],'thread-follower-steer-turn')
        self.assertEqual(args[1]['restoreMessage']['context'],{})
        self.assertEqual(args[1]['restoreMessage']['id'],args[1]['clientUserMessageId'])

    def test_explicit_idle_state_starts_one_turn(self):
        client = self.client()
        client.request = Mock(side_effect=DesktopError('idle',idle=True))
        self.assertEqual(client.submit_reply('chat','继续')['desktop_method'],'start')
        client.start_turn.assert_called_once_with('chat','继续')

    def test_ambiguous_error_never_retries_as_new_turn(self):
        for error in [TimeoutError('timeout'), DesktopError('unknown rejection')]:
            client = self.client()
            client.request = Mock(side_effect=error)
            with self.assertRaises(type(error)):
                client.submit_reply('chat','继续')
            client.start_turn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
