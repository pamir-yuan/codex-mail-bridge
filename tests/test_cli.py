import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from codex_mail_bridge import bridge, cli, config, service


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config_dir=Path(self.temp.name)/'config'
        self.state_dir=Path(self.temp.name)/'state'
        self.env=patch.dict(os.environ,{'CODEX_MAIL_BRIDGE_CONFIG_DIR':str(self.config_dir),
                                      'CODEX_MAIL_BRIDGE_STATE_DIR':str(self.state_dir),
                                      'CODEX_MAIL_BRIDGE_PASSWORD':'fixture-not-a-real-secret',
                                      'CODEX_THREAD_ID':'fixture-not-to-be-captured'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def invoke(self,args):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=cli.main(args)
        return code,output.getvalue()

    def test_example_init_never_writes_credentials_or_starts_services(self):
        code,text=self.invoke(['init','--example'])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(text)['status'],'example_created')
        self.assertTrue((self.config_dir/'config.json').is_file())
        self.assertFalse((self.config_dir/'credentials.json').exists())
        self.assertFalse(self.state_dir.exists())

    def test_dry_run_never_reads_password_or_uses_network(self):
        self.invoke(['init','--example'])
        with patch.object(cli,'read_password',side_effect=AssertionError('credentials must not be read')):
            code,text=self.invoke(['send','hello','--dry-run'])
        self.assertEqual(code,0)
        self.assertFalse(json.loads(text)['network_used'])
        self.assertNotIn('fixture-not-a-real-secret',text)

    def test_mcp_config_does_not_capture_secret_or_current_thread(self):
        code,text=self.invoke(['mcp-config'])
        self.assertEqual(code,0)
        self.assertIn('codex_mail_bridge',text)
        self.assertNotIn('PASSWORD',text)
        self.assertNotIn('CODEX_THREAD_ID',text)
        self.assertNotIn('fixture-not-to-be-captured',text)

    def test_generated_service_is_portable_and_has_no_secret(self):
        value=plistlib.loads(service.plist_bytes())
        self.assertEqual(value['ProgramArguments'][1:],['-m','codex_mail_bridge','listen'])
        self.assertNotIn('CODEX_MAIL_BRIDGE_PASSWORD',value['EnvironmentVariables'])
        self.assertNotIn('CODEX_THREAD_ID',value['EnvironmentVariables'])

    def test_status_does_not_create_runtime_files(self):
        with patch.object(bridge,'STATE_DIR',self.state_dir):
            value=bridge.status_report()
        self.assertEqual(value['sent_notifications'],0)
        self.assertFalse(self.state_dir.exists())

    def test_uncaught_provider_error_does_not_echo_credentials(self):
        self.invoke(['init','--example'])
        error=io.StringIO()
        with patch.object(bridge,'send_notification',side_effect=RuntimeError('fixture-private-content')):
            with contextlib.redirect_stderr(error):
                code,_=self.invoke(['send','hello','--thread-id','fixture-id'])
        self.assertEqual(code,1)
        self.assertNotIn('fixture-private-content',error.getvalue())


if __name__ == '__main__':unittest.main()
