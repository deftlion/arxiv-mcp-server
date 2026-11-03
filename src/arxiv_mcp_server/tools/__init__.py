"""Tool definitions for the arXiv MCP server."""

from .alerts import (
    check_alerts_tool,
    handle_check_alerts,
    handle_list_watches,
    handle_unwatch_topic,
    handle_watch_topic,
    list_watches_tool,
    unwatch_topic_tool,
    watch_topic_tool,
)
from .citation_graph import citation_graph_tool, handle_citation_graph
from .download import download_tool, handle_download
from .export_citations import export_citations_tool, handle_export_citations
from .get_abstract import abstract_tool, handle_get_abstract
from .latex import (
    get_paper_latex_section_tool,
    get_paper_latex_tool,
    handle_get_paper_latex,
    handle_get_paper_latex_section,
    handle_list_paper_latex_sections,
    list_paper_latex_sections_tool,
)
from .list_papers import handle_list_papers, list_tool
from .paper_outline import (
    handle_get_paper_outline,
    handle_read_paper_section,
    handle_search_paper_text,
    outline_tool,
    read_section_tool,
    search_text_tool,
)
from .read_paper import handle_read_paper, read_tool
from .search import handle_search, search_tool
from .semantic_search import (
    handle_reindex,
    handle_semantic_search,
    reindex_tool,
    semantic_search_tool,
)

__all__ = [
    "abstract_tool",
    "check_alerts_tool",
    "citation_graph_tool",
    "download_tool",
    "export_citations_tool",
    "get_paper_latex_section_tool",
    "get_paper_latex_tool",
    "handle_check_alerts",
    "handle_citation_graph",
    "handle_download",
    "handle_export_citations",
    "handle_get_abstract",
    "handle_get_paper_latex",
    "handle_get_paper_latex_section",
    "handle_get_paper_outline",
    "handle_list_paper_latex_sections",
    "handle_list_papers",
    "handle_list_watches",
    "handle_read_paper",
    "handle_read_paper_section",
    "handle_reindex",
    "handle_search",
    "handle_search_paper_text",
    "handle_semantic_search",
    "handle_unwatch_topic",
    "handle_watch_topic",
    "list_paper_latex_sections_tool",
    "list_tool",
    "list_watches_tool",
    "outline_tool",
    "read_section_tool",
    "read_tool",
    "reindex_tool",
    "search_text_tool",
    "search_tool",
    "semantic_search_tool",
    "unwatch_topic_tool",
    "watch_topic_tool",
]
