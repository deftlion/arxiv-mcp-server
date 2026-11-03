"""
Arxiv MCP Server
===============

This module implements an MCP server for interacting with arXiv.
"""

import json
import logging
from typing import Any

import uvicorn
from jsonschema.exceptions import best_match
from jsonschema.validators import validator_for
from mcp import MCPError, types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from .config import Settings, close_arxiv_client
from .prompts.handlers import get_prompt as handler_get_prompt
from .prompts.handlers import list_prompts as handler_list_prompts
from .tools import (
    abstract_tool,
    check_alerts_tool,
    citation_graph_tool,
    download_tool,
    export_citations_tool,
    get_paper_latex_section_tool,
    get_paper_latex_tool,
    handle_check_alerts,
    handle_citation_graph,
    handle_download,
    handle_export_citations,
    handle_get_abstract,
    handle_get_paper_latex,
    handle_get_paper_latex_section,
    handle_get_paper_outline,
    handle_list_paper_latex_sections,
    handle_list_papers,
    handle_list_watches,
    handle_read_paper,
    handle_read_paper_section,
    handle_reindex,
    handle_search,
    handle_search_paper_text,
    handle_semantic_search,
    handle_unwatch_topic,
    handle_watch_topic,
    list_paper_latex_sections_tool,
    list_tool,
    list_watches_tool,
    outline_tool,
    read_section_tool,
    read_tool,
    reindex_tool,
    search_text_tool,
    search_tool,
    semantic_search_tool,
    unwatch_topic_tool,
    watch_topic_tool,
)
from .tools.download import shutdown_background_tasks

settings = Settings()
logger = logging.getLogger("arxiv-mcp-server")
logger.setLevel(logging.INFO)


TOOLS: list[types.Tool] = [
    search_tool,
    download_tool,
    list_tool,
    read_tool,
    abstract_tool,
    semantic_search_tool,
    reindex_tool,
    citation_graph_tool,
    export_citations_tool,
    watch_topic_tool,
    check_alerts_tool,
    list_watches_tool,
    unwatch_topic_tool,
    get_paper_latex_tool,
    list_paper_latex_sections_tool,
    get_paper_latex_section_tool,
    outline_tool,
    read_section_tool,
    search_text_tool,
]
_TOOL_VALIDATORS = {
    tool.name: validator_for(tool.input_schema)(tool.input_schema) for tool in TOOLS
}


async def list_tools() -> list[types.Tool]:
    """List available arXiv research tools."""
    return list(TOOLS)


def _tool_error_message(result: list[types.TextContent]) -> str | None:
    """Return the error text if a tool result is an error payload."""
    if len(result) != 1 or result[0].type != "text":
        return None

    text = result[0].text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text if text.startswith("Error:") else None

    if isinstance(payload, dict) and payload.get("status") == "error":
        return text
    return None


async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls for arXiv research functionality."""
    logger.debug(f"Calling tool {name} with arguments {arguments}")
    try:
        if name == "search_papers":
            result = await handle_search(arguments)
        elif name == "download_paper":
            result = await handle_download(arguments)
        elif name == "list_papers":
            result = await handle_list_papers(arguments)
        elif name == "read_paper":
            result = await handle_read_paper(arguments)
        elif name == "get_abstract":
            result = await handle_get_abstract(arguments)
        elif name == "semantic_search":
            result = await handle_semantic_search(arguments)
        elif name == "reindex":
            result = await handle_reindex(arguments)
        elif name == "citation_graph":
            result = await handle_citation_graph(arguments)
        elif name == "export_citations":
            result = await handle_export_citations(arguments)
        elif name == "watch_topic":
            result = await handle_watch_topic(arguments)
        elif name == "check_alerts":
            result = await handle_check_alerts(arguments)
        elif name == "list_watches":
            result = await handle_list_watches(arguments)
        elif name == "unwatch_topic":
            result = await handle_unwatch_topic(arguments)
        elif name == "get_paper_latex":
            result = await handle_get_paper_latex(arguments)
        elif name == "list_paper_latex_sections":
            result = await handle_list_paper_latex_sections(arguments)
        elif name == "get_paper_latex_section":
            result = await handle_get_paper_latex_section(arguments)
        elif name == "get_paper_outline":
            result = await handle_get_paper_outline(arguments)
        elif name == "read_paper_section":
            result = await handle_read_paper_section(arguments)
        elif name == "search_paper_text":
            result = await handle_search_paper_text(arguments)
        else:
            result = [
                types.TextContent(type="text", text=f"Error: Unknown tool {name}")
            ]

        if error_message := _tool_error_message(result):
            raise RuntimeError(error_message)
        return result
    except Exception as e:
        logger.error(f"Tool error: {e!s}")
        raise


async def _list_prompts(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListPromptsResult:
    return types.ListPromptsResult(prompts=await handler_list_prompts())


async def _get_prompt(
    ctx: ServerRequestContext, params: types.GetPromptRequestParams
) -> types.GetPromptResult:
    try:
        return await handler_get_prompt(params.name, params.arguments)
    except ValueError as exc:
        raise MCPError(code=types.INVALID_PARAMS, message=str(exc)) from exc


async def _list_tools(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=await list_tools())


async def _call_tool(
    ctx: ServerRequestContext, params: types.CallToolRequestParams
) -> types.CallToolResult:
    # SDK 2 no longer validates arguments or converts tool exceptions to results.
    arguments = params.arguments or {}
    try:
        validator = _TOOL_VALIDATORS.get(params.name)
        if validator and (error := best_match(validator.iter_errors(arguments))):
            message = f"Input validation error: {error.message}"
        else:
            # Unknown tool names fall through to call_tool's error branch.
            return types.CallToolResult(
                content=list(await call_tool(params.name, arguments))
            )
    # Tool failures must reach clients as is_error results, not protocol errors.
    except Exception as exc:
        message = str(exc) or type(exc).__name__
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )


server = Server(
    settings.APP_NAME,
    version=settings.APP_VERSION,
    on_list_prompts=_list_prompts,
    on_get_prompt=_get_prompt,
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)


def _csv_settings(value: str) -> list[str]:
    """Parse a comma-separated environment setting into non-empty strings."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _transport_security_settings() -> TransportSecuritySettings:
    """Build explicit DNS rebinding protection for Streamable HTTP."""
    host = settings.HOST
    port = settings.PORT
    loopback_hosts = {"127.0.0.1", "localhost", "[::1]"}
    allowed_hosts = {
        host,
        f"{host}:{port}",
        *(f"{h}:*" for h in loopback_hosts),
        *loopback_hosts,
    }
    allowed_hosts.update(_csv_settings(settings.ALLOWED_HOSTS))

    origin_hosts = {host, *loopback_hosts}
    allowed_origins = {
        f"http://{origin_host}:{port}" for origin_host in origin_hosts
    } | {f"https://{origin_host}:{port}" for origin_host in origin_hosts}
    allowed_origins.update(
        f"{scheme}://{loopback}:*"
        for scheme in ("http", "https")
        for loopback in loopback_hosts
    )
    allowed_origins.update(_csv_settings(settings.ALLOWED_ORIGINS))

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(allowed_hosts),
        allowed_origins=sorted(allowed_origins),
    )


async def _run_stdio() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def _healthz(_request):
    """Liveness probe for HTTP deploys. Process up means ready."""
    return PlainTextResponse("ok")


def _build_http_app(session_manager) -> Starlette:
    """HTTP app: MCP mount plus a deploy probe. stdio does not use this."""
    return Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Mount("/mcp", app=session_manager.handle_request),
        ]
    )


async def _run_streamable_http() -> None:
    """Run the MCP server over Streamable HTTP."""
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=False,
        security_settings=_transport_security_settings(),
    )
    starlette_app = _build_http_app(session_manager)
    config = uvicorn.Config(
        starlette_app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
    uvicorn_server = uvicorn.Server(config)
    logger.info(
        "Starting streamable HTTP transport on %s:%s", settings.HOST, settings.PORT
    )
    async with session_manager.run():
        await uvicorn_server.serve()


async def main():
    """Run the server async context and release process-wide resources."""
    try:
        transport = settings.TRANSPORT.lower().replace("-", "_")
        if transport in {"stdio", ""}:
            await _run_stdio()
        elif transport in {"http", "streamable_http"}:
            await _run_streamable_http()
        else:
            raise ValueError(
                f"Unsupported transport {settings.TRANSPORT!r}; expected 'stdio' or 'http'"
            )
    finally:
        await shutdown_background_tasks()
        close_arxiv_client()
