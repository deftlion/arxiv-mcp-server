"""Research journey prompt management for the arXiv MCP server."""

from mcp.types import Prompt

from .prompts import PROMPTS

# Global prompt manager instance
_prompt_manager: dict[str, Prompt] | None = None


def get_prompt_manager() -> dict[str, Prompt]:
    """Get or create the global prompt manager dictionary.

    Returns:
        Dict[str, Prompt]: Dictionary of available prompts
    """
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PROMPTS

    return _prompt_manager


def register_prompt(prompt: Prompt) -> None:
    """Register a new prompt in the prompt manager.

    Args:
        prompt (Prompt): The prompt to register
    """
    manager = get_prompt_manager()
    manager[prompt.name] = prompt
