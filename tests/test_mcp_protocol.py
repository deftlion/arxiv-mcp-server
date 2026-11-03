"""Offline wire-level checks against the MCP SDK 2 stdio and HTTP clients."""

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import sys

import httpx
from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
import pytest
import uvicorn

from arxiv_mcp_server import server as server_module
from arxiv_mcp_server.prompts.prompts import PROMPTS
from arxiv_mcp_server.tools import list_papers as list_module
from arxiv_mcp_server.tools import read_paper as read_module
from arxiv_mcp_server.tools.content import DEFAULT_MAX_CHARS


@asynccontextmanager
async def protocol_transport(transport, tmp_path, monkeypatch):
    if transport == "stdio":
        source = str(Path(__file__).resolve().parents[1] / "src")
        env = {
            **os.environ,
            "PYTHONPATH": source,
            "HOME": str(tmp_path),
            "TRANSPORT": "stdio",
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "arxiv_mcp_server", "--storage-path", str(tmp_path)],
            env=env,
            cwd=tmp_path,
        )
        async with stdio_client(params) as streams:
            yield streams
        return

    # Each tool module owns a Settings instance; isolate every one this test calls.
    for module in (list_module, read_module):
        monkeypatch.setattr(
            module.settings, "_get_storage_path_from_args", lambda: tmp_path
        )
    manager = StreamableHTTPSessionManager(
        app=server_module.server,
        security_settings=server_module._transport_security_settings(),
    )
    app = server_module._build_http_app(manager)
    ready = asyncio.Event()

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            ready.set()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        config = uvicorn.Config(app, lifespan="off", log_level="warning")
        http_server = ReadyServer(config)
        async with manager.run():
            task = asyncio.create_task(http_server.serve(sockets=[listener]))
            try:
                await ready.wait()
                url = f"http://127.0.0.1:{port}"
                async with httpx.AsyncClient() as client:
                    health = await client.get(f"{url}/healthz")
                    assert health.status_code == 200
                    bad_host = await client.post(
                        f"{url}/mcp/",
                        headers={
                            "host": "attacker.example",
                            "content-type": "application/json",
                        },
                    )
                    assert bad_host.status_code == 421
                    bad_origin = await client.post(
                        f"{url}/mcp/",
                        headers={
                            "origin": "https://attacker.example",
                            "content-type": "application/json",
                        },
                    )
                    assert bad_origin.status_code == 403
                async with streamable_http_client(f"{url}/mcp/") as streams:
                    yield streams
            finally:
                http_server.should_exit = True
                await task


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_sdk2_protocol_surface(transport, tmp_path, monkeypatch):
    """Real clients discover, render prompts, read bounded text and see tool errors."""
    paper_id = "1706.03762"
    content = "Cached offline paper. " * 2000
    (tmp_path / f"{paper_id}.md").write_text(content, encoding="utf-8")

    async with asyncio.timeout(30):
        async with protocol_transport(transport, tmp_path, monkeypatch) as streams:
            async with ClientSession(*streams, read_timeout_seconds=10) as session:
                initialized = await session.initialize()
                assert (
                    initialized.server_info.version
                    == server_module.settings.APP_VERSION
                )
                assert initialized.capabilities.tools is not None
                assert initialized.capabilities.prompts is not None
                assert initialized.capabilities.resources is None

                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    tool.name for tool in server_module.TOOLS
                }
                assert all(tool.input_schema for tool in tools.tools)
                # No output schemas are advertised: results are text blocks, as in v1.
                assert all(tool.output_schema is None for tool in tools.tools)

                prompts = await session.list_prompts()
                assert {prompt.name for prompt in prompts.prompts} == set(PROMPTS)
                prompt = await session.get_prompt(
                    "summarize_paper", {"paper_id": paper_id}
                )
                assert paper_id in prompt.messages[0].content.text
                with pytest.raises(MCPError, match="Missing required argument"):
                    await session.get_prompt("summarize_paper", {})
                with pytest.raises(MCPError, match="Prompt not found"):
                    await session.get_prompt("not_a_prompt", {})

                listed = await session.call_tool("list_papers", {})
                assert not listed.is_error
                assert paper_id in listed.content[0].text
                read = await session.call_tool("read_paper", {"paper_id": paper_id})
                assert not read.is_error
                payload = json.loads(read.content[0].text)
                assert payload["returned_chars"] == DEFAULT_MAX_CHARS
                assert payload["is_truncated"] is True
                assert payload["next_start"] == DEFAULT_MAX_CHARS
                assert payload["content_length"] == len(content)

                for name, arguments, error_text in [
                    ("read_paper", {}, "required property"),
                    ("read_paper", {"paper_id": 123}, "not of type"),
                    ("list_papers", {"unexpected": True}, "Additional properties"),
                    ("not_a_tool", {}, "Unknown tool"),
                    ("read_paper", {"paper_id": "0000.00000"}, "not found"),
                ]:
                    result = await session.call_tool(name, arguments)
                    assert result.is_error, (name, result)
                    assert error_text.lower() in result.content[0].text.lower()
                assert not (await session.call_tool("list_papers")).is_error
