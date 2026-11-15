import importlib.util
from pathlib import Path
import unittest

CHECKER=Path(__file__).resolve().parents[1]/'scripts/check_public_tree.py'
spec=importlib.util.spec_from_file_location('public_checker',CHECKER)
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicTreeChecks(unittest.TestCase):
    def test_reserved_example_addresses_allowed(self):
        self.assertEqual(checker.inspect('example.txt',b'you@example.com other@provider.test'),[])

    def test_unapproved_mailbox_detected_without_echoing_it(self):
        address=b'person@' + b'private-mail.invalid-domain.org'
        result=checker.inspect('fixture.txt',address)
        self.assertTrue(result)
        self.assertNotIn(address.decode(),str(result))

    def test_private_database_file_is_rejected(self):
        self.assertTrue(checker.inspect('bridge.sqlite3',b''))


if __name__=='__main__':unittest.main()
