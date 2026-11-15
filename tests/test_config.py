import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_mail_bridge import config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)/'private'
        self.env = patch.dict(os.environ,{'CODEX_MAIL_BRIDGE_CONFIG_DIR':str(self.directory)})
        self.env.start()
        self.clear_password = patch.dict(os.environ)
        self.clear_password.start()
        os.environ.pop('CODEX_MAIL_BRIDGE_PASSWORD',None)

    def tearDown(self):
        self.clear_password.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_example_contains_connection_details_only(self):
        value = config.validate(config.example_config())
        self.assertEqual(value['to'],['you@example.com'])
        self.assertNotIn('password',value)

    def test_private_json_permissions_and_no_clobber(self):
        target=self.directory/'config.json'
        config.write_private_json(target,config.example_config())
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.directory.stat().st_mode & 0o777,0o700)
        with self.assertRaises(config.ConfigError):
            config.write_private_json(target,{'replace':True})
        self.assertIn('smtp_host',json.loads(target.read_text()))

    def test_credentials_are_separate_and_checked(self):
        config.write_private_json(self.directory/'credentials.json',{'password':'fixture-app-password'})
        self.assertEqual(config.read_password(),'fixture-app-password')
        (self.directory/'credentials.json').chmod(0o644)
        with self.assertRaises(config.ConfigError):config.read_password()

    def test_shell_metacharacters_are_data_not_commands(self):
        fixture="fixture-quote'$(not-a-command)"
        config.write_private_json(self.directory/'credentials.json',{'password':fixture})
        self.assertEqual(config.read_password(),fixture)

    def test_environment_credentials_do_not_require_files(self):
        with patch.dict(os.environ,{'CODEX_MAIL_BRIDGE_PASSWORD':'fixture-env-password'}):
            self.assertEqual(config.read_password(),'fixture-env-password')
        self.assertFalse(self.directory.exists())

    def test_refuses_credentials_in_connection_config(self):
        with self.assertRaises(config.ConfigError):
            config.validate({**config.example_config(),'password':'fixture-password'})

    def test_refuses_other_recipient_and_plaintext_transport(self):
        for update in ({'to':'someone-else@example.com'},{'security':'plain'},{'poll_seconds':True}):
            with self.assertRaises(config.ConfigError):config.validate({**config.example_config(),**update})

    def test_symlink_private_file_is_not_read_or_overwritten(self):
        self.directory.mkdir(mode=0o700)
        outside=Path(self.temp.name)/'outside.json'
        outside.write_text('{"password":"fixture-password"}')
        (self.directory/'credentials.json').symlink_to(outside)
        with self.assertRaises(config.ConfigError):config.read_password()
        with self.assertRaises(config.ConfigError):
            config.write_private_json(self.directory/'credentials.json',{},overwrite=True)
        self.assertIn('fixture-password',outside.read_text())


if __name__ == '__main__':unittest.main()
