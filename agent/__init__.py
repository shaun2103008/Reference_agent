"""A small tool-using agent. Built in week 1; hardened in week 2."""

from .agent import Budget, Trace, run_agent
from .llm import LLMError, ask, ask_json, chat
from .tools import TOOLS, ToolError, run_tool, tool_specs

__all__ = ["Budget", "Trace", "run_agent", "LLMError", "ask", "ask_json",
           "chat", "TOOLS", "ToolError", "run_tool", "tool_specs"]
