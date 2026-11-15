"""MCP transport adapter. Credentials are never accepted as tool arguments."""
import os
from . import bridge


def create_server():
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("codex-mail-bridge",instructions=(
        "Send email notifications only when the user has authorized them. Direct replies are routed back to the exact originating chat. "
        "Always pass the actual current thread UUID; obtain CODEX_THREAD_ID from a shell tool in that chat, never guess a title. "
        "Credentials and the self-notification mailbox are configured locally. Do not pass credentials or arbitrary recipients. "
        "SMTP acceptance does not prove user receipt. Do not blindly retry failed or ambiguous sends. "
        "This tool does not configure automatic end-of-turn notifications or crash monitoring."))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,
                                            idempotentHint=False,openWorldHint=True))
    def send_notification(title: str, message: str, thread_id: str) -> dict:
        """Send an authorized email notification bound to the real originating Codex chat UUID."""
        try:
            return bridge.send_notification(title,message,thread_id)
        except Exception as error:
            raise ValueError(f"Notification failed ({type(error).__name__}); check local configuration") from None

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,
                                            idempotentHint=True,openWorldHint=False))
    def notification_status() -> dict:
        """Read bridge heartbeat and delivery counts without exposing mail contents or credentials."""
        return bridge.status_report()

    return server


def run():
    os.umask(0o077)
    create_server().run(transport="stdio")


if __name__ == "__main__":
    run()
