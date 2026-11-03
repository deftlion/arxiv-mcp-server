"""Regression tests for the legacy PaperManager resource listing."""

import importlib
import sys
from unittest.mock import MagicMock, patch


async def test_list_resources_builds_sdk2_resources(tmp_path, mock_paper):
    """SDK 2 ``Resource.uri`` is a plain string; a pydantic URL is rejected."""
    with patch.dict(sys.modules, {"pymupdf4llm": MagicMock()}):
        papers = importlib.import_module("arxiv_mcp_server.resources.papers")

    storage = tmp_path / "my papers"
    storage.mkdir()
    (storage / "2103.12345.md").write_text("cached", encoding="utf-8")

    manager = papers.PaperManager.__new__(papers.PaperManager)
    manager.storage_path = storage
    manager.client = MagicMock()
    manager.client.results.return_value = [mock_paper]

    resources = await manager.list_resources()

    assert len(resources) == 1
    assert resources[0].uri == (storage / "2103.12345.md").as_uri()
    assert "my%20papers" in resources[0].uri
    assert resources[0].mime_type == "text/markdown"
