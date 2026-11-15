"""Exercise the real stdio transport without mail or desktop connections."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP SDK is not installed')
class MCPTransportTests(unittest.TestCase):
    def test_stdio_tools_and_isolated_error_path(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def exercise(root):
            environment = dict(os.environ)
            environment.pop('CODEX_MAIL_BRIDGE_PASSWORD', None)
            environment.pop('CODEX_THREAD_ID', None)
            environment.update({
                'HOME': str(root),
                'CODEX_HOME': str(root/'desktop'),
                'CODEX_MAIL_BRIDGE_CONFIG_DIR': str(root/'configuration'),
                'CODEX_MAIL_BRIDGE_STATE_DIR': str(root/'state'),
                'CODEX_MAIL_BRIDGE_IPC_SOCKET': str(root/'absent.sock'),
                'CODEX_MAIL_BRIDGE_CODEX_STATE_DB': str(root/'absent.sqlite'),
            })
            parameters = StdioServerParameters(
                command=sys.executable, args=['-m', 'codex_mail_bridge', 'mcp'], env=environment)
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                    self.assertEqual(set(tools), {'send_notification', 'notification_status'})
                    self.assertIn('thread_id', tools['send_notification'].inputSchema['required'])
                    status = await session.call_tool('notification_status', {})
                    self.assertFalse(status.isError)
                    rejected = await session.call_tool('send_notification', {
                        'title': 'Test', 'message': 'No mail must be sent', 'thread_id': 'invalid-thread'})
                    self.assertTrue(rejected.isError)
            self.assertFalse((root/'state').exists())
            self.assertFalse((root/'configuration').exists())

        with tempfile.TemporaryDirectory() as temporary:
            asyncio.run(exercise(Path(temporary)))


if __name__ == '__main__':
    unittest.main()
